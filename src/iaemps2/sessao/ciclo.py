"""A sessão inteira (card S3-06, o esqueleto ambulante): observar, decidir, executar, registrar, mostrar.

Duas threads, paredes rígidas. A do Tk só desenha e capta gestos (overlay). A de trabalho, esta, é dona do
laço, do cliente do canal, do serviço, da captura e da conexão com a sessão viva. O overlay só enfileira;
este laço só lê o painel como dado e escreve nele como dado. Qualquer exceção vira falha visível (RN-10).
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from iaemps2 import log
from iaemps2.catalogo import catalogo as cat
from iaemps2.config import Config
from iaemps2.mestre import memoria, mestre
from iaemps2.mestre.decisao import Veredito
from iaemps2.olho import olho
from iaemps2.olho.captura import Captura, JanelaAusenteError, Retangulo, e_o_emulador
from iaemps2.olho.diferenca import Comparador
from iaemps2.olho.situacao import Situacao, e_marco_de_morte
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.ponte.emulador import JogoEmExecucao
from iaemps2.ponte.estados import FilaDeSlots
from iaemps2.registro import banco
from iaemps2.servicos.base import Servico, ServicoError
from iaemps2.sessao.executor import Executor
from iaemps2.sessao.fila import FilaDeEventos, Laco, Mensagem
from iaemps2.sessao.maquina import Efeito, Estado, Evento, Resultado, TransicaoInvalidaError
from iaemps2.sessao.overlay import Painel
from iaemps2.sessao.relogio import Contador, IntervaloMinimo

Capturar = Callable[[Retangulo | None], Captura]


class PainelDaSessao(Protocol):
    painel: Painel
    area_atual: Retangulo | None

    def atualizar(self, **campos: object) -> None: ...
    def mostrar_acao(self, alavanca: str, motivo: str) -> None: ...
    def mostrar_nada(self, motivo: str) -> None: ...


class PainelSilencioso:
    """O painel sem Tk: mesmos métodos, só dados. Para os testes e para rodar sem monitor."""

    def __init__(self, agora_ms: Callable[[], int] = lambda: int(time.monotonic() * 1000)) -> None:
        self.painel = Painel()
        self.area_atual: Retangulo | None = None
        self.agora_ms = agora_ms

    def atualizar(self, **campos: object) -> None:
        for nome, valor in campos.items():
            if not hasattr(self.painel, nome):
                raise AttributeError(nome)
            setattr(self.painel, nome, valor)

    def mostrar_acao(self, alavanca: str, motivo: str) -> None:
        self.painel.ultima_acao, self.painel.motivo = alavanca.replace("_", " "), motivo
        self.painel.acao_em_ms = self.agora_ms()
        self.painel.historico.append(alavanca)

    def mostrar_nada(self, motivo: str) -> None:
        self.painel.ultima_acao, self.painel.motivo, self.painel.acao_em_ms = (
            "observando",
            motivo,
            self.agora_ms(),
        )


@dataclass
class Pendencia:
    """O que o laço carrega entre estados: a situação decidida e a decisão validada."""

    situacao: Situacao
    situacao_id: int
    status: p.Status
    veredito: Veredito | None = None
    decisao_id: int | None = None


def emulador_vivo() -> bool:
    """O processo do emulador existe? É o que distingue fechado de travado e de canal caído (G03)."""
    import psutil

    return any(e_o_emulador(proc.info["name"]) for proc in psutil.process_iter(["name"]))


@dataclass
class Sessao:
    config: Config
    cliente: Cliente
    jogo: JogoEmExecucao
    con: sqlite3.Connection
    sessao_id: str
    pasta: Path
    servico: Servico
    capturar: Capturar
    painel: PainelDaSessao
    catalogo: cat.Catalogo
    contador: Contador
    dormir: Callable[[float], None] = time.sleep
    tom: cat.Tom = cat.TOM_PADRAO
    intensidade: cat.Intensidade = cat.INTENSIDADE_PADRAO
    encerrar_apos_s: float | None = None
    processo_vivo: Callable[[], bool] = emulador_vivo

    fila: FilaDeEventos = field(default_factory=FilaDeEventos)
    comparador: Comparador = field(init=False)
    intervalo: IntervaloMinimo = field(init=False)
    executor: Executor = field(init=False)
    laco: Laco = field(init=False)
    ciclo_numero: int = 0
    ciclo_id: int | None = None
    situacao_atual: Situacao | None = None
    situacao_id_atual: int | None = None
    pendencia: Pendencia | None = None
    ultima_alavanca: tuple[str, int] | None = None
    ultimo_salvamento_ms: int = 0
    falhas_seguidas_do_servico: int = 0
    proxima_tentativa_ms: int = 0
    origem_do_silencio: str | None = None  # servico | emulador: quem calou o mestre decide como ele volta
    formato_seguidos: int = 0  # resposta fora do contrato: a segunda seguida silencia (contrato 4)
    travado_desde_ms: int | None = None
    encerrada: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.comparador = Comparador(
            self.config.captura.limiar_diferenca, self.config.captura.intervalo_ms / 1000 * 15, self._relogio
        )
        self.intervalo = IntervaloMinimo(self.contador, self.catalogo.regras.intervalo_minimo_s * 1000)
        slots = FilaDeSlots(
            self.config.emulador.caminho_estados(),
            self.jogo.identificacao.serial,
            self.jogo.identificacao.crc,
            self.config.slots_reservados.todos(),
        )
        self.executor = Executor(self.cliente, slots, self.con, self.sessao_id, self.contador, self.catalogo)
        self.laco = Laco(self.fila, self._efeitos, self._invalida)
        self.painel.atualizar(
            jogo=self.jogo.identificacao.titulo, modo=self.jogo.modo, estado=Estado.ABRINDO.value
        )

    def _relogio(self) -> float:
        return self.contador.agora_ms() / 1000

    # ---------- gestos do jogador (chamados pela thread do Tk: só enfileiram) ----------
    def gesto(self, nome: str) -> None:
        if nome == "pausar":
            evento = Evento.JOGADOR_RETOMOU if self.painel.painel.pausado else Evento.JOGADOR_PAUSOU
        elif nome == "reverter":
            evento = Evento.JOGADOR_REVERTEU
        elif nome == "encerrar":
            evento = Evento.JOGADOR_ENCERROU
        else:
            return
        self.fila.enfileirar(evento, origem="jogador")

    # ---------- o laço ----------
    def iniciar(self) -> None:
        self.fila.enfileirar(Evento.PRONTO)

    def rodar(self) -> None:
        """A thread de trabalho inteira. Termina quando a sessão encerra."""
        self.iniciar()
        relogio_de_fim = threading.Thread(target=self.vigiar_fins, name="fim", daemon=True)
        relogio_de_fim.start()
        try:
            while not self.encerrada.is_set():
                self.passo()
                if not self.encerrada.is_set():
                    self.dormir(self.config.captura.intervalo_ms / 1000)
        finally:
            relogio_de_fim.join(timeout=2)

    def vigiar_fins(self, passo_s: float = 0.1) -> None:
        """Encerra as ações com duração no segundo certo, mesmo com o laço parado esperando o serviço.
        Na prova de fogo, pausas de 3 s duraram 9 e 11 s porque o fim só era visto entre ciclos."""
        while not self.encerrada.wait(passo_s):
            try:
                for id_ in self.executor.encerrar_vencidos():
                    log.evento("intervencao.fim", intervencao=id_)
            except Exception as erro:  # RN-10
                self._falha("emulador", type(erro).__name__, str(erro), processar=False)

    def passo(self) -> None:
        """Um ciclo: gestos pendentes, um passo pelo estado, fim das ações com duração, gestos de novo."""
        try:
            self.laco.processar_todos()
            if self.encerrar_apos_s is not None and self.contador.agora_ms() >= self.encerrar_apos_s * 1000:
                self.encerrar_apos_s = None
                self.fila.enfileirar(Evento.JOGADOR_ENCERROU, origem="plataforma")
            estado = self.laco.estado
            if estado in (Estado.OBSERVANDO, Estado.BLOQUEADA):
                self._observar()
            elif estado == Estado.DECIDINDO:
                self._decidir()
            elif estado == Estado.EXECUTANDO:
                self._executar()
            elif estado == Estado.SILENCIADA:
                self._tentar_recuperar()
            for id_ in self.executor.encerrar_vencidos():
                log.evento("intervencao.fim", intervencao=id_)
            self._salvamento_periodico()
            self.laco.processar_todos()
            self.painel.atualizar(
                estado=self.laco.estado.value,
                proxima_janela_ms=self.intervalo.faltam_ms(),
                pausado=self.laco.estado == Estado.PAUSADA_JOGADOR,
            )
        except (
            sqlite3.OperationalError
        ) as erro:  # disco cheio, pasta sem permissão: nada executa sem registro
            self._falha("registro", "sem_escrita", str(erro))
        except Exception as erro:  # RN-10: nada morre em silêncio
            self._falha(
                "emulador" if isinstance(erro, CanalError | ComandoFalhouError) else "servico",
                type(erro).__name__,
                str(erro),
            )

    # ---------- passos por estado ----------
    def _novo_ciclo(self, lacuna: str | None = None) -> int:
        self.ciclo_numero += 1
        self.ciclo_id = banco.gravar_ciclo(
            self.con,
            self.sessao_id,
            self.ciclo_numero,
            self.contador.agora_ms(),
            self._status_texto(),
            self.laco.estado.value,
            lacuna,
        )
        return self.ciclo_id

    def _status_texto(self) -> str:
        try:
            return self.cliente.status().name.lower()
        except (CanalError, ComandoFalhouError):
            return "sem_canal"

    def _observar(self) -> None:
        with log.contexto(sessao=self.sessao_id, ciclo=self.ciclo_numero + 1):
            try:
                self.cliente.status()  # canal morto é visto a cada ciclo, não só quando há ação (G03)
            except (CanalError, ComandoFalhouError) as erro:
                ciclo = self._novo_ciclo(lacuna="sem canal com o emulador")
                banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
                classe = erro.classe if isinstance(erro, CanalError) else "comando_falhou"
                self._falha("emulador", classe, str(erro))
                return
            try:
                captura = self.capturar(self.painel.area_atual)
            except JanelaAusenteError as erro:
                ciclo = self._novo_ciclo(lacuna=str(erro))
                banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
                self.painel.atualizar(enviando=False, situacao="janela do emulador não encontrada")
                self.fila.enfileirar(Evento.CAPTURA_SEM_MUDANCA, origem="captura")
                return
            ciclo = self._novo_ciclo()
            banco.gravar_metrica(
                self.con, {"ciclo_id": ciclo, "etapa": "captura", "latencia_ms": captura.duracao_ms}
            )
            veredito = self.comparador.avaliar(captura)
            arquivo = self._guardar_captura(captura)
            captura_id = banco.gravar_captura(
                self.con,
                {
                    "ciclo_id": ciclo,
                    "arquivo": arquivo,
                    "largura": captura.largura,
                    "altura": captura.altura,
                    "bytes": captura.bytes,
                    "digest": captura.digest,
                    "diferenca": veredito.diferenca,
                    "enviada": 1 if veredito.enviar else 0,
                    "motivo_envio": veredito.motivo,
                },
            )
            if not veredito.enviar:
                banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
                self.fila.enfileirar(Evento.CAPTURA_SEM_MUDANCA, origem="captura")
                return
            self.painel.atualizar(enviando=True)
            status = self.cliente.status()
            try:
                obs = olho.descrever(
                    self.servico,
                    captura,
                    veredito,
                    jogo_titulo=self.jogo.identificacao.titulo,
                    jogo_serial=self.jogo.identificacao.serial,
                    status=status,
                    velocidade=1.0,
                    ultima_alavanca=self.ultima_alavanca[0] if self.ultima_alavanca else None,
                    ultima_alavanca_ha_ms=(self.contador.agora_ms() - self.ultima_alavanca[1])
                    if self.ultima_alavanca
                    else None,
                    anterior=self.situacao_atual,
                )
            except ServicoError as erro:
                banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
                self._falha_do_servico(erro)
                return
            self.falhas_seguidas_do_servico = 0
            if obs.resposta is not None:
                banco.gravar_metrica(
                    self.con,
                    {
                        "ciclo_id": ciclo,
                        "etapa": "descrever",
                        "latencia_ms": obs.resposta.latencia_ms,
                        "tokens_entrada": obs.resposta.tokens_entrada,
                        "tokens_saida": obs.resposta.tokens_saida,
                        "custo_estimado": self._custo(obs.resposta.tokens_entrada, obs.resposta.tokens_saida),
                    },
                )
            if obs.situacao is None:
                banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
                self._fora_do_contrato(obs.invalida_motivo or "resposta fora do contrato")
                return
            self.formato_seguidos = 0
            assert obs.resposta is not None
            situacao_id = banco.gravar_situacao(
                self.con,
                {
                    "captura_id": captura_id,
                    "descricao": obs.situacao.descricao,
                    "fase": obs.situacao.fase.value,
                    "aperto": obs.situacao.aperto,
                    "confianca": obs.situacao.confianca,
                    "suspeita": obs.suspeita,
                    "latencia_ms": obs.resposta.latencia_ms,
                    "resposta_bruta": obs.resposta.texto,
                },
            )
            morte = e_marco_de_morte(self.situacao_atual, obs.situacao)
            anterior_em_jogo = self.situacao_atual is None or self.situacao_atual.em_jogo
            self.situacao_atual, self.situacao_id_atual = obs.situacao, situacao_id
            self.executor.situacao_id_atual = situacao_id
            self.painel.atualizar(
                situacao=f"{obs.situacao.fase.value} · aperto {obs.situacao.aperto} · {obs.situacao.descricao}"
            )
            banco.fechar_ciclo(self.con, ciclo, self.contador.agora_ms())
            log.evento(
                "situacao",
                fase=obs.situacao.fase.value,
                aperto=obs.situacao.aperto,
                latencia_ms=obs.resposta.latencia_ms,
            )
            if obs.suspeita or not obs.situacao.em_jogo:
                self.fila.enfileirar(
                    Evento.SITUACAO_FORA_DE_JOGO, origem="servico", morte=morte, suspeita=obs.suspeita
                )
                return
            if self.laco.estado == Estado.BLOQUEADA or not anterior_em_jogo:
                self.fila.enfileirar(Evento.CENA_VOLTOU, origem="servico")
            self.pendencia = Pendencia(obs.situacao, situacao_id, status)
            self.fila.enfileirar(Evento.SITUACAO_OK, origem="servico")

    def _guardar_captura(self, captura: Captura) -> str:
        pasta = self.pasta / "capturas"
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"capturas/{self.ciclo_numero:06d}.jpg"
        (self.pasta / nome).write_bytes(captura.jpeg)
        return nome

    def _custo(self, entrada: int | None, saida: int | None) -> float | None:
        s = self.config.servico
        if not s.preco_entrada_por_milhao and not s.preco_saida_por_milhao:
            return None
        return (
            (entrada or 0) * s.preco_entrada_por_milhao + (saida or 0) * s.preco_saida_por_milhao
        ) / 1_000_000

    def _decidir(self) -> None:
        pend = self.pendencia
        if pend is None or self.ciclo_id is None:
            self.fila.enfileirar(Evento.DECISAO_NADA, origem="plataforma", motivo="sem situação")
            return
        with log.contexto(sessao=self.sessao_id, ciclo=self.ciclo_numero):
            mem = memoria.reconstruir(self.con, self.sessao_id, self.contador.agora_ms())
            pedido = mestre.montar_pedido(
                catalogo=self.executor.catalogo,
                situacao=pend.situacao,
                status=pend.status.name.lower(),
                velocidade=1.0,
                memoria=mem,
                proxima_janela_ms=self.intervalo.faltam_ms(),
                jogo_titulo=self.jogo.identificacao.titulo,
            )
            try:
                decidido = mestre.decidir(
                    self.servico,
                    pedido,
                    self.executor.catalogo,
                    pend.situacao,
                    self.executor.aperto_dos_slots,
                )
            except ServicoError as erro:
                self._falha_do_servico(erro)
                return
            v = decidido.veredito
            decisao_id = banco.gravar_decisao(
                self.con,
                {
                    "ciclo_id": self.ciclo_id,
                    "situacao_id": pend.situacao_id,
                    "catalogo_versao": self.executor.catalogo.versao,
                    "alavanca": v.alavanca,
                    "parametros_json": json.dumps(v.parametros),
                    "motivo": v.motivo,
                    "motivo_origem": v.motivo_origem,
                    "origem": v.origem,
                    "descarte_motivo": v.descarte_motivo,
                    "pedido_bruto": decidido.pedido_bruto,
                    "resposta_bruta": decidido.resposta.texto if decidido.resposta else None,
                    "latencia_ms": decidido.resposta.latencia_ms if decidido.resposta else None,
                },
            )
            if decidido.resposta is not None:
                banco.gravar_metrica(
                    self.con,
                    {
                        "ciclo_id": self.ciclo_id,
                        "etapa": "decidir",
                        "latencia_ms": decidido.resposta.latencia_ms,
                        "tokens_entrada": decidido.resposta.tokens_entrada,
                        "tokens_saida": decidido.resposta.tokens_saida,
                        "custo_estimado": self._custo(
                            decidido.resposta.tokens_entrada, decidido.resposta.tokens_saida
                        ),
                    },
                )
            log.evento("decisao", alavanca=v.alavanca, origem=v.origem, descarte=v.descarte_motivo)
            if v.origem == "ritmo":
                self.fila.enfileirar(Evento.INTERVALO_NAO_VENCEU, origem="plataforma", motivo=v.motivo)
            elif v.origem in ("descarte", "falha"):
                self.fila.enfileirar(Evento.DECISAO_DESCARTADA, origem="plataforma", motivo=v.descarte_motivo)
            elif v.alavanca == cat.NADA:
                self.fila.enfileirar(Evento.DECISAO_NADA, origem="servico", motivo=v.motivo)
            else:
                pend.veredito, pend.decisao_id = v, decisao_id
                self.fila.enfileirar(Evento.DECISAO_VALIDADA, origem="plataforma")

    def _executar(self) -> None:
        pend = self.pendencia
        if pend is None or pend.veredito is None or pend.decisao_id is None:
            self.fila.enfileirar(Evento.EXECUCAO_FALHOU, origem="plataforma", detalhe="sem decisão")
            return
        with log.contexto(sessao=self.sessao_id, ciclo=self.ciclo_numero):
            inicio = self.contador.agora_ms()
            execucao = self.executor.executar(
                pend.veredito, pend.decisao_id, pend.situacao, pend.status, self.situacao_atual
            )
            if self.ciclo_id is not None:
                banco.gravar_metrica(
                    self.con,
                    {
                        "ciclo_id": self.ciclo_id,
                        "etapa": "executar",
                        "latencia_ms": self.contador.agora_ms() - inicio,
                    },
                )
            log.evento(
                "execucao", alavanca=execucao.alavanca, resultado=execucao.resultado, detalhe=execucao.detalhe
            )
            if execucao.resultado == "confirmada":
                self.ultima_alavanca = (execucao.alavanca, self.contador.agora_ms())
                self.fila.enfileirar(
                    Evento.EXECUCAO_CONFIRMADA,
                    origem="plataforma",
                    alavanca=execucao.alavanca,
                    motivo=pend.veredito.motivo,
                )
            elif execucao.resultado == "descartada":
                self.fila.enfileirar(Evento.SITUACAO_MUDOU, origem="plataforma", detalhe=execucao.detalhe)
            else:
                self.fila.enfileirar(Evento.EXECUCAO_FALHOU, origem="plataforma", detalhe=execucao.detalhe)

    def _salvamento_periodico(self) -> None:
        """A05 de rotina, pela intensidade: fora do catálogo de decisões, para a recarga ter de onde voltar."""
        if self.laco.estado not in (Estado.OBSERVANDO, Estado.DECIDINDO):
            return
        if self.situacao_atual is None or not self.situacao_atual.em_jogo:
            return
        a_cada_ms = self.catalogo.regras.salvar_a_cada_s * 1000
        if self.contador.agora_ms() - self.ultimo_salvamento_ms < a_cada_ms:
            return
        self.ultimo_salvamento_ms = self.contador.agora_ms()
        if self.executor.salvar_periodico(self.situacao_atual) is not None:
            log.evento("estado.salvo", slots=self.executor.slots.ocupados())

    def _tentar_recuperar(self) -> None:
        """Silenciada: quem calou decide a volta. Serviço: espera o intervalo e tenta o ciclo de novo (a contagem
        só zera numa descrição válida, então o intervalo cresce de verdade). Emulador: fechado, travado ou
        canal caído, pelo processo e pelo socket (G03)."""
        agora = self.contador.agora_ms()
        if self.origem_do_silencio == "emulador":
            self._tentar_reconectar(agora)
            return
        if agora < self.proxima_tentativa_ms:
            return
        try:
            self.cliente.status()
        except (CanalError, ComandoFalhouError) as erro:
            self.origem_do_silencio = "emulador"  # o emulador também sumiu enquanto o serviço estava fora
            self._classificar_emulador(erro, agora)
            return
        self.fila.enfileirar(Evento.RECUPEROU, origem="plataforma")

    def _tentar_reconectar(self, agora: int) -> None:
        if not self.processo_vivo():
            self._queda("fechado", "o processo do emulador não existe mais")
            return
        if agora < self.proxima_tentativa_ms:
            return
        try:
            self.cliente.status()
        except (CanalError, ComandoFalhouError) as erro:
            self._classificar_emulador(erro, agora)
            return
        self.travado_desde_ms = None
        self._conferir_emulador_ao_voltar()
        self.fila.enfileirar(Evento.RECUPEROU, origem="plataforma")

    def _classificar_emulador(self, erro: Exception, agora: int) -> None:
        classe = erro.classe if isinstance(erro, CanalError) else "comando_falhou"
        if classe == "travado":
            if self.travado_desde_ms is None:
                self.travado_desde_ms = agora
            parado_ms = agora - self.travado_desde_ms
            if parado_ms >= self.config.emulador.limite_travado_s * 1000:
                self._queda(
                    "fechado", f"travado por {parado_ms // 1000} s, além do limite: tratado como fechado"
                )
                return
            self.painel.atualizar(falha=f"emulador travado há {parado_ms // 1000} s; esperando")
        else:
            self.travado_desde_ms = None
            self.painel.atualizar(falha=f"emulador: {classe}; tentando reconectar")
        self.proxima_tentativa_ms = agora + 2_000

    def _queda(self, classe: str, detalhe: str) -> None:
        """Emulador fechado: a sessão encerra com resumo, marcando que o emulador caiu antes (E04 via G03)."""
        self._falha("emulador", classe, detalhe)

    def _conferir_emulador_ao_voltar(self) -> None:
        """G03, exceção: ao reconectar, o jogo nunca fica alterado. Velocidade fora do normal sem ação em vigor
        volta ao normal e fica registrado. Pausa não é tocada: pode ser do jogador."""
        if self.jogo.modo != "completo":
            return
        try:
            atual = self.cliente.velocidade_atual()
        except (CanalError, ComandoFalhouError):
            return
        em_vigor = {pend.alavanca for pend in self.executor.pendentes}
        if atual.modo != p.ModoVelocidade.NORMAL and not em_vigor & {"camera_lenta", "turbo"}:
            with contextlib.suppress(CanalError, ComandoFalhouError):
                self.cliente.velocidade(p.ModoVelocidade.NORMAL, 1.0, 0)
            with contextlib.suppress(Exception):
                banco.gravar_falha(
                    self.con,
                    {
                        "ciclo_id": self.ciclo_id,
                        "ocorrido_ms": self.contador.agora_ms(),
                        "origem": "emulador",
                        "classe": "velocidade_restaurada",
                        "detalhe": f"ao reconectar, velocidade em {atual.modo.name.lower()} ({atual.alvo}) sem ação em vigor",
                        "visivel": 0,
                    },
                )
            log.evento("velocidade.restaurada", modo=atual.modo.name.lower(), alvo=atual.alvo)

    # ---------- falhas (RN-10, contrato 4) ----------
    def _falha_do_servico(self, erro: ServicoError) -> None:
        """Classifica: recusa segue no ciclo seguinte sem a mesma imagem; formato silencia na segunda seguida;
        fora do ar e limite silenciam com intervalo crescente (ou o informado)."""
        if erro.classe == "recusa":
            self.comparador.esquecer()  # a próxima captura vai inteira; nunca a mesma imagem de novo
            self._falha("servico", "recusa", erro.detalhe, silenciar=False)
            return
        if erro.classe == "formato":
            self._fora_do_contrato(erro.detalhe)
            return
        self._silenciar_servico(erro.classe, erro.detalhe, erro.espera_s)

    def _fora_do_contrato(self, motivo: str) -> None:
        self.formato_seguidos += 1
        if self.formato_seguidos < 2:
            self.fila.enfileirar(Evento.SITUACAO_INVALIDA, origem="servico", motivo=motivo)
            return
        self._silenciar_servico("formato", motivo, None)

    def _silenciar_servico(self, classe: str, detalhe: str, espera_s: float | None) -> None:
        self.falhas_seguidas_do_servico += 1
        espera_ms = (
            int(espera_s * 1000) if espera_s else min(30_000, 2_000 * (2**self.falhas_seguidas_do_servico))
        )
        self.proxima_tentativa_ms = self.contador.agora_ms() + espera_ms
        self._falha("servico", classe, detalhe)
        if self.falhas_seguidas_do_servico >= self.config.servico.limite_falhas_seguidas:
            self.fila.enfileirar(Evento.FALHA_PROLONGADA, origem="plataforma", classe=classe)
            self.laco.processar_todos()

    def _falha(
        self, origem: str, classe: str, detalhe: str, *, silenciar: bool = True, processar: bool = True
    ) -> None:
        with contextlib.suppress(Exception):
            banco.gravar_falha(
                self.con,
                {
                    "ciclo_id": self.ciclo_id,
                    "ocorrido_ms": self.contador.agora_ms(),
                    "origem": origem,
                    "classe": classe,
                    "detalhe": detalhe[:500],
                    "visivel": 1,
                },
            )
        self.painel.atualizar(falha=f"{classe}: {detalhe[:80]}", enviando=False)
        log.falha("falha", origem=origem, classe=classe, detalhe=detalhe[:200])
        if not silenciar:
            return
        evento = {"emulador": Evento.FALHA_EMULADOR, "registro": Evento.FALHA_REGISTRO}.get(
            origem, Evento.FALHA_SERVICO
        )
        if origem in ("emulador", "servico") and self.origem_do_silencio is None:
            self.origem_do_silencio = origem
        try:
            self.laco.fila.enfileirar(evento, origem="plataforma", classe=classe)
            if processar:
                self.laco.processar_todos()
        except Exception:
            pass

    # ---------- efeitos da máquina ----------
    def _efeitos(self, resultado: Resultado, mensagem: Mensagem, anterior: Estado) -> None:
        for efeito in resultado.efeitos:
            self._efeito(efeito, mensagem, anterior)

    def _efeito(self, efeito: Efeito, m: Mensagem, anterior: Estado) -> None:
        d = m.dados
        if efeito == Efeito.GRAVAR_SESSAO_E_CATALOGO:
            banco.inserir(
                self.con,
                "catalogo_versoes",
                {
                    "sessao_id": self.sessao_id,
                    "versao": self.catalogo.versao,
                    "criado_ms": self.contador.agora_ms(),
                    "motivo": self.catalogo.motivo_da_versao,
                    "catalogo_json": self.catalogo.como_json(),
                },
            )
        elif efeito == Efeito.GRAVAR_MARCO_SE_MORTE and d.get("morte") and self.ciclo_id is not None:
            banco.gravar_marco(self.con, self.ciclo_id, "morte")
        elif efeito == Efeito.CONGELAR_INTERVALO:
            self.contador.congelar()
        elif efeito == Efeito.DESCONGELAR_INTERVALO:
            self.contador.descongelar()
        elif efeito == Efeito.GRAVAR_MARCO_MUDANCA_FASE and self.ciclo_id is not None:
            banco.gravar_marco(self.con, self.ciclo_id, "mudanca_fase")
        elif efeito == Efeito.OVERLAY_DISCRETO:
            self.painel.mostrar_nada(str(d.get("motivo") or ""))
        elif efeito == Efeito.MOSTRAR_ACAO_E_MOTIVO:
            self.painel.mostrar_acao(str(d.get("alavanca")), str(d.get("motivo") or ""))
        elif efeito == Efeito.ZERAR_INTERVALO:
            self.intervalo.zerar()
        elif efeito == Efeito.ENCERRAR_ACOES_COM_DURACAO:
            self.executor.encerrar_todas()
        elif efeito == Efeito.CANCELAR_EXECUCAO:
            self.pendencia = None
        elif efeito == Efeito.GRAVAR_MARCO and self.ciclo_id is not None:
            tipos = {Evento.JOGADOR_PAUSOU: "pausa_mestre", Evento.FALHA_PROLONGADA: "pausa_por_falhas"}
            banco.gravar_marco(self.con, self.ciclo_id, tipos.get(m.evento, "retomada"))
        elif efeito == Efeito.OVERLAY_MESTRE_PAUSADO:
            self.painel.atualizar(pausado=True, enviando=False)
            if m.evento == Evento.FALHA_PROLONGADA:
                self.painel.mostrar_nada(
                    f"Mestre pausado: {self.falhas_seguidas_do_servico} falhas seguidas do serviço. Ctrl+Alt+P retoma."
                )
            else:
                self.painel.mostrar_nada("Mestre pausado. Ctrl+Alt+P retoma.")
        elif efeito == Efeito.REINICIAR_INTERVALO or efeito == Efeito.INTERVALO_COMO_VENCIDO:
            self.intervalo.tratar_como_vencido()
            self.painel.atualizar(pausado=False, falha=None)
            if m.evento == Evento.JOGADOR_RETOMOU:  # o jogador retomou: a contagem de falhas recomeça do zero
                self.falhas_seguidas_do_servico = 0
                self.formato_seguidos = 0
                self.origem_do_silencio = None
        elif efeito == Efeito.MARCAR_QUEDA_DO_EMULADOR and self.ciclo_id is not None:
            with contextlib.suppress(Exception):
                banco.gravar_marco(self.con, self.ciclo_id, "queda_emulador", str(d.get("classe")))
        elif efeito == Efeito.AVISAR_SEM_REGISTRO:
            self.painel.atualizar(falha="registro sem escrita: nada executa sem registro")
        elif efeito == Efeito.EXECUTAR_REVERSAO and self.ciclo_id is not None:
            r = self.executor.reverter(self.ciclo_id)
            if r is None:
                self.painel.mostrar_nada("Nada a desfazer.")
            else:
                self.painel.mostrar_acao(
                    "desfeito",
                    f"{r.alavanca.replace('_', ' ')}: {'desfeito' if r.resultado == 'confirmada' else 'não consegui: ' + str(r.detalhe)}",
                )
                self.intervalo.zerar()
        elif efeito == Efeito.GRAVAR_VOLTA:
            # a contagem de falhas do serviço NÃO zera aqui: só uma descrição válida zera, senão o intervalo
            # crescente recomeçava em 4 s a cada volta (defeito achado no S5-01)
            self.origem_do_silencio = None
            log.evento("recuperou")
        elif efeito == Efeito.ESTADO_FINAL_EM_SLOT:
            self.executor.salvar_periodico(self.situacao_atual)
        elif efeito == Efeito.FECHAR_ARQUIVO:
            banco.fechar_sessao(self.con, self.sessao_id)
            self.painel.atualizar(estado=Estado.ENCERRADA.value, enviando=False)
            self.encerrada.set()
        # os demais efeitos são gravações que os passos já fizeram com o dado na mão, ou só nomeiam o que o
        # painel mostra pelo estado (ABRIR_OVERLAY, INICIAR_CICLO, OVERLAY_DESTAQUE, TENTAR_RECONECTAR...)

    def _invalida(self, erro: TransicaoInvalidaError, m: Mensagem) -> None:
        log.evento(
            "transicao.recusada", nivel=30, estado=erro.atual.value, evento=erro.evento.value, origem=m.origem
        )

    # ---------- resumo (E04), só do registro ----------
    def resumo(self) -> dict[str, Any]:
        con = self.con

        def q(sql: str, *a: object) -> int:
            return int(con.execute(sql, a).fetchone()[0])

        sid = self.sessao_id
        por_alavanca = [
            {"alavanca": r[0], "n": r[1]}
            for r in con.execute(
                "select i.alavanca, count(*) from intervencoes i join decisoes d on d.id = i.decisao_id join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and i.origem = 'mestre' and i.resultado = 'confirmada' group by i.alavanca",
                (sid,),
            )
        ]
        intervencoes = [
            {"ciclo": r[0], "alavanca": r[1], "motivo": r[2], "resultado": r[3]}
            for r in con.execute(
                "select c.numero, i.alavanca, d.motivo, i.resultado from intervencoes i join decisoes d on d.id = i.decisao_id join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and i.origem = 'mestre' order by i.id",
                (sid,),
            )
        ]
        latencias: dict[str, dict[str, int]] = {}
        for etapa in ("captura", "descrever", "decidir", "executar"):
            valores = [
                int(r[0])
                for r in con.execute(
                    "select m.latencia_ms from metricas m join ciclos c on c.id = m.ciclo_id where c.sessao_id = ? and m.etapa = ?",
                    (sid, etapa),
                )
            ]
            if valores:
                latencias[etapa] = {
                    "mediana_ms": int(statistics.median(valores)),
                    "max_ms": max(valores),
                    "n": len(valores),
                }
        custo = con.execute(
            "select sum(m.custo_estimado), sum(m.tokens_entrada), sum(m.tokens_saida) from metricas m join ciclos c on c.id = m.ciclo_id where c.sessao_id = ?",
            (sid,),
        ).fetchone()
        return {
            "sessao": sid,
            "jogo": self.jogo.identificacao.titulo,
            "modo": self.jogo.modo,
            "ciclos": q("select count(*) from ciclos where sessao_id = ?", sid),
            "lacunas": q("select count(*) from ciclos where sessao_id = ? and lacuna is not null", sid),
            "capturas_enviadas": q(
                "select count(*) from capturas cap join ciclos c on c.id = cap.ciclo_id where c.sessao_id = ? and cap.enviada = 1",
                sid,
            ),
            "capturas_poupadas": q(
                "select count(*) from capturas cap join ciclos c on c.id = cap.ciclo_id where c.sessao_id = ? and cap.enviada = 0",
                sid,
            ),
            "decisoes_nada": q(
                "select count(*) from decisoes d join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and d.alavanca = 'nada'",
                sid,
            ),
            "decisoes_descartadas": q(
                "select count(*) from decisoes d join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and d.origem in ('descarte','falha')",
                sid,
            ),
            "intervencoes_por_alavanca": por_alavanca,
            "intervencoes": intervencoes,
            "reversoes": q(
                "select count(*) from intervencoes i join decisoes d on d.id = i.decisao_id join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and i.origem = 'reversao_jogador'",
                sid,
            ),
            "falhas": q(
                "select count(*) from falhas f left join ciclos c on c.id = f.ciclo_id where c.sessao_id = ? or f.ciclo_id is null",
                sid,
            ),
            "estados_salvos": q("select count(*) from estados_reservados where sessao_id = ?", sid),
            "latencias": latencias,
            "tokens_entrada": int(custo[1] or 0),
            "tokens_saida": int(custo[2] or 0),
            "custo_estimado": round(float(custo[0]), 4) if custo[0] is not None else None,
            "duracao_s": self.contador.agora_ms() // 1000,
        }


def texto_do_resumo(r: dict[str, Any]) -> str:
    linhas = [
        f"Sessão {r['sessao']} · {r['jogo']} · modo {r['modo']} · {r['duracao_s']} s",
        f"ciclos {r['ciclos']} (lacunas {r['lacunas']}) · capturas enviadas {r['capturas_enviadas']}, poupadas {r['capturas_poupadas']}",
        f"decisões: nada {r['decisoes_nada']} · descartadas {r['decisoes_descartadas']} · intervenções confirmadas: "
        + (", ".join(f"{x['alavanca']} x{x['n']}" for x in r["intervencoes_por_alavanca"]) or "nenhuma"),
        f"reversões {r['reversoes']} · falhas {r['falhas']} · estados salvos {r['estados_salvos']}",
    ]
    for etapa, v in r["latencias"].items():
        linhas.append(f"latência {etapa}: mediana {v['mediana_ms']} ms, máximo {v['max_ms']} ms (n={v['n']})")
    custo = f"{r['custo_estimado']}" if r["custo_estimado"] is not None else "não estimado"
    linhas.append(f"tokens entrada {r['tokens_entrada']}, saída {r['tokens_saida']} · custo estimado {custo}")
    for i in r["intervencoes"]:
        linhas.append(f"  ciclo {i['ciclo']}: {i['alavanca']} ({i['resultado']}) · {i['motivo']}")
    return "\n".join(linhas)
