"""Executar e reverter pelo caso de uso de cada alavanca (card S3-04; casos D02 e D03; A03 a A06).

Nenhuma ação chega ao emulador sem passar pelo catálogo, pelo intervalo e pelo registro, e toda ação tem
volta. O executor recebe um veredito já conferido (S3-03), relê o emulador (validação 2), grava o estado
antes, despacha para a ponte pelo caso de uso da alavanca, confirma, grava o estado depois e marca a
intervenção como reversível. Reverter usa o caminho próprio de cada alavanca. Falha de execução não é
repetida no ciclo; três seguidas tiram a alavanca do catálogo.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from iaemps2.catalogo import catalogo as cat
from iaemps2.catalogo.mundo import AcaoDeMundo
from iaemps2.mestre.decisao import Veredito, situacao_mudou
from iaemps2.olho.situacao import Situacao
from iaemps2.ponte import memoria
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.ponte.estados import FilaDeSlots, RecargaNaoConfirmadaError, SalvamentoNaoConfirmadoError
from iaemps2.registro import banco
from iaemps2.sessao.relogio import Contador


def _sincronizado[**P, R](metodo: Callable[P, R]) -> Callable[P, R]:
    """O laço e o relógio de fim chamam o executor de threads diferentes; um de cada vez."""

    @functools.wraps(metodo)
    def envolto(*args: P.args, **kwargs: P.kwargs) -> R:
        executor: Any = args[0]
        with executor._trava:
            return metodo(*args, **kwargs)

    return envolto


COM_DURACAO = {"pausa", "camera_lenta", "turbo"}
# O emulador aplica pausa e velocidade na thread da CPU dele, depois de responder ao canal; a confirmação
# relê até ver o efeito, dentro deste limite.
CONFIRMACAO_TENTATIVAS = 20
CONFIRMACAO_PASSO_S = 0.05
MODO_POR_ALAVANCA = {"camera_lenta": p.ModoVelocidade.LENTA, "turbo": p.ModoVelocidade.TURBO}


@dataclass(frozen=True)
class Execucao:
    intervencao_id: int
    alavanca: str
    resultado: str  # confirmada | falhou | descartada
    detalhe: str | None = None
    fim_programado_ms: int | None = None
    caminho_volta: dict[str, float] | None = None
    reversivel: bool = False


class AcaoDescartadaError(RuntimeError):
    """Proibição batida na hora (H07): a ação não escreve e fica registrada como descartada."""


class EscritaNaoConfirmadaError(ComandoFalhouError):
    """A releitura não bateu com o escrito: a escrita aconteceu, então a volta vai para o registro."""

    def __init__(self, detalhe: str, volta: dict[str, float]) -> None:
        super().__init__(detalhe)
        self.volta = volta


VOLTA_TENTATIVAS = 10  # ciclos em que a volta de uma ação de mundo é tentada de novo com o canal caído


@dataclass
class Pendente:
    intervencao_id: int
    alavanca: str
    fim_ms: int
    decisao_id: int = 0
    volta: dict[str, float] | None = None  # ação de mundo: o que devolver no prazo
    tentativas: int = 0


def _mundo(catalogo: cat.Catalogo, nome: str) -> AcaoDeMundo | None:
    alavanca = catalogo.alavanca(nome)
    return alavanca.mundo if alavanca is not None else None


@dataclass
class Executor:
    cliente: Cliente
    slots: FilaDeSlots
    con: sqlite3.Connection
    sessao_id: str
    contador: Contador
    catalogo: cat.Catalogo
    pendentes: list[Pendente] = field(default_factory=list)
    ultima_reversivel: Execucao | None = None
    aperto_dos_slots: dict[int, int] = field(default_factory=dict)
    situacao_id_atual: int | None = None  # a sessão informa a cada ciclo; vira contexto do slot salvo
    dormir: Callable[[float], None] = time.sleep  # entre releituras de confirmação
    _trava: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ---------- estado do emulador para o registro ----------
    @_sincronizado
    def estado_atual(self, situacao: Situacao | None) -> dict[str, object]:
        status = self.cliente.status()
        velocidade = 1.0
        if self.catalogo.modo == "completo":  # o emulador original não tem a consulta
            try:
                velocidade = self.cliente.velocidade_atual().alvo
            except ComandoFalhouError:
                velocidade = 1.0
        return {
            "status": status.name.lower(),
            "velocidade": velocidade,
            "slots": self.slots.ocupados(),
            "situacao": situacao.model_dump(mode="json") if situacao else None,
        }

    # ---------- D02 ----------
    @_sincronizado
    def executar(
        self,
        veredito: Veredito,
        decisao_id: int,
        situacao: Situacao,
        status_decidido: p.Status,
        situacao_agora: Situacao | None = None,
    ) -> Execucao:
        """Despacha a alavanca validada. A releitura (validação 2) acontece aqui, com o emulador na mão."""
        assert veredito.executa, "só vereditos executáveis chegam ao executor"
        status_agora = self.cliente.status()
        mudou = situacao_mudou(situacao, status_decidido, situacao_agora, status_agora)
        antes = self.estado_atual(situacao_agora or situacao)
        intervencao_id = banco.gravar_intervencao(
            self.con,
            {
                "decisao_id": decisao_id,
                "alavanca": veredito.alavanca,
                "parametros_json": json.dumps(veredito.parametros),
                "origem": "mestre",
                "estado_antes_json": json.dumps(antes, ensure_ascii=False),
                "comando_ms": self.contador.agora_ms(),
                "reversivel": 1 if veredito.alavanca != "salvar_estado" else 0,
            },
        )
        if mudou is not None:
            banco.preencher_uma_vez(
                self.con,
                "intervencoes",
                intervencao_id,
                {"resultado": "descartada", "estado_depois_json": json.dumps(antes, ensure_ascii=False)},
            )
            return Execucao(intervencao_id, veredito.alavanca, "descartada", f"situação velha: {mudou}")
        try:
            fim, volta = self._despachar(veredito, situacao, intervencao_id)
        except AcaoDescartadaError as erro:
            depois = self._estado_seguro(situacao)
            banco.preencher_uma_vez(
                self.con,
                "intervencoes",
                intervencao_id,
                {"resultado": "descartada", "estado_depois_json": json.dumps(depois, ensure_ascii=False)},
            )
            return Execucao(intervencao_id, veredito.alavanca, "descartada", str(erro))
        except (
            CanalError,
            ComandoFalhouError,
            SalvamentoNaoConfirmadoError,
            RecargaNaoConfirmadaError,
            memoria.AlvoNaoResolvidoError,
        ) as erro:
            depois = self._estado_seguro(situacao)
            falha: dict[str, object] = {
                "resultado": "falhou",
                "estado_depois_json": json.dumps(depois, ensure_ascii=False),
            }
            if isinstance(erro, EscritaNaoConfirmadaError):
                falha["caminho_volta_json"] = json.dumps(erro.volta)
            banco.preencher_uma_vez(self.con, "intervencoes", intervencao_id, falha)
            self.catalogo, _ = cat.registrar_falha(self.catalogo, veredito.alavanca)
            return Execucao(intervencao_id, veredito.alavanca, "falhou", str(erro))
        depois = self._estado_seguro(situacao)
        campos: dict[str, object] = {
            "resultado": "confirmada",
            "confirmado_ms": self.contador.agora_ms(),
            "estado_depois_json": json.dumps(depois, ensure_ascii=False),
        }
        if volta is not None:
            campos["caminho_volta_json"] = json.dumps(volta)
        banco.preencher_uma_vez(self.con, "intervencoes", intervencao_id, campos)
        self.catalogo = cat.registrar_sucesso(self.catalogo, veredito.alavanca)
        execucao = Execucao(
            intervencao_id,
            veredito.alavanca,
            "confirmada",
            None,
            fim,
            volta,
            veredito.alavanca != "salvar_estado",
        )
        if execucao.reversivel:
            self.ultima_reversivel = execucao
        if fim is not None:
            mundo = volta if _mundo(self.catalogo, veredito.alavanca) is not None else None
            self.pendentes.append(Pendente(intervencao_id, veredito.alavanca, fim, decisao_id, mundo))
        return execucao

    def _estado_seguro(self, situacao: Situacao | None) -> dict[str, object]:
        try:
            return self.estado_atual(situacao)
        except (CanalError, ComandoFalhouError):
            return {"status": "sem_canal", "velocidade": None, "slots": [], "situacao": None}

    def _despachar(
        self, v: Veredito, situacao: Situacao, intervencao_id: int
    ) -> tuple[int | None, dict[str, float] | None]:
        agora = self.contador.agora_ms()
        if v.alavanca == "pausa":
            self.cliente.pausar(True)
            if not self._confirmar(lambda: self.cliente.status() == p.Status.PAUSADO):
                raise ComandoFalhouError("status não virou pausado")
            return agora + int(v.parametros["duracao_s"] * 1000), None
        if v.alavanca in MODO_POR_ALAVANCA:
            modo = MODO_POR_ALAVANCA[v.alavanca]
            duracao_ms = int(v.parametros["duracao_s"] * 1000)
            self.cliente.velocidade(modo, v.parametros["escalar"], duracao_ms)
            if not self._confirmar(lambda: self.cliente.velocidade_atual().modo == modo):
                atual = self.cliente.velocidade_atual()
                raise ComandoFalhouError(
                    f"velocidade em vigor é {atual.modo.name.lower()}, não {modo.name.lower()}"
                )
            return agora + duracao_ms, None
        if v.alavanca == "salvar_estado":
            self._salvar(situacao, "periodico")
            return None, None
        if v.alavanca == "recarregar":
            slot = int(v.parametros["slot"])
            volta_slot = self._slot_de_volta(slot)
            self._cancelar_mundo("recarga: o estado recarregado não carrega a ação")
            self._salvar(situacao, "antes_recarga", slot=volta_slot)
            self.slots.recarregar(self.cliente, slot)
            return None, {"slot": float(volta_slot)}
        acao = _mundo(self.catalogo, v.alavanca)
        if acao is not None:
            return self._despachar_mundo(v, situacao, acao)
        raise ComandoFalhouError(f"alavanca sem executor: {v.alavanca}")

    # ---------- H07: ação de mundo ----------
    def _despachar_mundo(
        self, v: Veredito, situacao: Situacao, acao: AcaoDeMundo
    ) -> tuple[int, dict[str, float]]:
        """Lê antes, confere as proibições na hora, escreve dentro da faixa, relê e confirma. A volta é
        'devolver o tirado': sobrevive a dano no meio do prazo, que 'valor anterior' não sobrevive."""
        if acao.proibicoes.so_em_jogo and not situacao.em_jogo:
            raise AcaoDescartadaError(f"fora de jogo ({situacao.fase})")
        if any(x.volta is not None and x.alavanca == v.alavanca for x in self.pendentes):
            raise AcaoDescartadaError(f"{v.alavanca} já em vigor")
        alvo = memoria.resolver(self.cliente, acao.alvo)
        atual = memoria.ler(self.cliente, acao.alvo, alvo.endereco)
        maxima = self._ler_maxima(acao, alvo)
        base = maxima if acao.operacao == "fixar_fracao_da_maxima" else atual
        piso = acao.proibicoes.piso
        if atual <= piso:
            raise AcaoDescartadaError(f"{v.alavanca}: valor atual {atual} já no piso {piso}")
        desejado = max(piso, int(base * v.parametros["fracao"]))
        if desejado >= atual:
            raise AcaoDescartadaError(f"{v.alavanca}: alvo {desejado} não está abaixo do atual {atual}")
        memoria.escrever(self.cliente, acao.alvo, alvo.endereco, desejado)
        relido = memoria.ler(self.cliente, acao.alvo, alvo.endereco)
        volta = {
            "endereco": float(alvo.endereco),
            "valor_antes": float(atual),
            "valor_escrito": float(desejado),
            "tirado": float(atual - relido),
            "maxima": float(maxima),
            **alvo.chaves(),
        }
        if relido != desejado:
            # a escrita aconteceu: devolve agora o que tirou, guarda a volta e conta como falha
            self._devolver_valor(acao, volta)
            raise EscritaNaoConfirmadaError(
                f"{v.alavanca}: escrito {desejado}, relido {relido}; devolvido", volta
            )
        return self.contador.agora_ms() + int(v.parametros["duracao_s"] * 1000), volta

    def _ler_maxima(self, acao: AcaoDeMundo, alvo: memoria.Resolvido) -> int:
        """A máxima declarada, lida na hora; numa entidade, na mesma vaga do alvo. −1 quando não há."""
        if acao.maxima is None:
            return -1
        if acao.maxima.modo == "entidade":
            endereco = alvo.endereco - acao.alvo.deslocamento + acao.maxima.deslocamento
        else:
            endereco = memoria.resolver(self.cliente, acao.maxima).endereco
        return memoria.ler(self.cliente, acao.maxima, endereco)

    def _devolver_valor(self, acao: AcaoDeMundo, volta: dict[str, float]) -> dict[str, float]:
        """Devolve o que tirou, sem passar do teto (a máxima lida na ida, ou o valor de antes) e sem baixar o
        atual; sem escrita quando o valor está em zero (morte) ou quando o alvo já não é o mesmo."""
        endereco = memoria.conferir_alvo(self.cliente, acao.alvo, volta)
        if endereco is None:
            return {"valor_no_fim": -1.0, "devolvido": 0.0, "valor_final": -1.0, "alvo_mudou": 1.0}
        atual = memoria.ler(self.cliente, acao.alvo, endereco)
        if atual <= 0:
            return {"valor_no_fim": float(atual), "devolvido": 0.0, "valor_final": float(atual)}
        teto = int(volta["maxima"]) if volta["maxima"] >= 0 else int(volta["valor_antes"])
        novo = max(atual, min(atual + int(volta["tirado"]), teto))
        if novo != atual:
            memoria.escrever(self.cliente, acao.alvo, endereco, novo)
        relido = memoria.ler(self.cliente, acao.alvo, endereco)
        return {"valor_no_fim": float(atual), "devolvido": float(novo - atual), "valor_final": float(relido)}

    def _mundo_em_vigor(self) -> bool:
        return any(x.volta is not None for x in self.pendentes)

    def _cancelar_mundo(self, motivo: str) -> None:
        """Recarga de estado: as ações de mundo em vigor saem sem escrever (o estado recarregado não as tem)."""
        for pendente in [x for x in self.pendentes if x.volta is not None]:
            self._registrar_fim(pendente, "descartada", {"motivo": motivo})
            self.pendentes.remove(pendente)

    def _registrar_fim(self, pendente: Pendente, resultado: str, parametros: dict[str, object]) -> None:
        """O fim de uma ação de mundo é uma intervenção própria (origem 'encerramento') ligada à mesma decisão,
        com o que foi devolvido; a original ganha fim_ms."""
        antes = self._estado_seguro(None)
        agora = self.contador.agora_ms()
        id_fim = banco.gravar_intervencao(
            self.con,
            {
                "decisao_id": pendente.decisao_id,
                "alavanca": pendente.alavanca,
                "parametros_json": json.dumps(parametros, ensure_ascii=False),
                "origem": "encerramento",
                "estado_antes_json": json.dumps(antes, ensure_ascii=False),
                "comando_ms": agora,
                "reversivel": 0,
            },
        )
        campos: dict[str, object] = {
            "resultado": resultado,
            "estado_depois_json": json.dumps(self._estado_seguro(None), ensure_ascii=False),
        }
        if resultado == "confirmada":
            campos["confirmado_ms"] = self.contador.agora_ms()
        banco.preencher_uma_vez(self.con, "intervencoes", id_fim, campos)
        banco.preencher_uma_vez(self.con, "intervencoes", pendente.intervencao_id, {"fim_ms": agora})

    def _confirmar(self, efeito_visto: Callable[[], bool]) -> bool:
        """Relê o emulador até ver o efeito ou esgotar as tentativas. A primeira leitura é imediata."""
        for tentativa in range(CONFIRMACAO_TENTATIVAS):
            if efeito_visto():
                return True
            if tentativa < CONFIRMACAO_TENTATIVAS - 1:
                self.dormir(CONFIRMACAO_PASSO_S)
        return False

    def _slot_de_volta(self, destino: int) -> int:
        candidatos = [s for s in self.slots.slots if s != destino]
        vazios = [s for s in candidatos if not self.slots.arquivo(s).exists()]
        if vazios:
            return vazios[0]
        return min(candidatos, key=lambda s: self.slots.arquivo(s).stat().st_mtime)

    def _salvar(self, situacao: Situacao | None, motivo: str, slot: int | None = None) -> int:
        """A05: salva, confirma pelo arquivo e grava em estados_reservados com a situação como contexto."""
        salvo = self.slots.salvar(self.cliente, slot)
        situacao_id = self.situacao_id_atual if situacao is not None else None
        registro_id = banco.inserir(
            self.con,
            "estados_reservados",
            {
                "sessao_id": self.sessao_id,
                "slot": salvo.slot,
                "salvo_ms": self.contador.agora_ms() - int(salvo.salvo_s * 1000),
                "confirmado_ms": self.contador.agora_ms(),
                "arquivo": str(salvo.arquivo),
                "bytes": salvo.bytes,
                "situacao_id": situacao_id,
                "motivo": motivo,
            },
        )
        self.aperto_dos_slots[salvo.slot] = situacao.aperto if situacao else 0
        self.catalogo = cat.com_slots(self.catalogo, tuple(sorted(self.aperto_dos_slots)))
        return registro_id

    @_sincronizado
    def salvar_periodico(self, situacao: Situacao | None) -> int | None:
        """O salvamento de rotina da intensidade (A05), fora do catálogo de decisões. Com ação de mundo em
        vigor não salva: o estado guardaria o mundo alterado e uma recarga o traria de volta sem volta."""
        if self._mundo_em_vigor():
            return None
        try:
            return self._salvar(situacao, "periodico")
        except (CanalError, ComandoFalhouError, SalvamentoNaoConfirmadoError):
            return None

    # ---------- fim das ações com duração ----------
    @_sincronizado
    def encerrar_vencidos(self, agora_ms: int | None = None) -> list[int]:
        """Pausa termina pela plataforma; velocidade termina pelo vigia do emulador. Grava o fim de ambas."""
        agora = self.contador.agora_ms() if agora_ms is None else agora_ms
        encerradas: list[int] = []
        for pendente in list(self.pendentes):
            if agora < pendente.fim_ms:
                continue
            self._encerrar(pendente)
            if pendente not in self.pendentes:  # a volta de uma ação de mundo pode ficar para o próximo ciclo
                encerradas.append(pendente.intervencao_id)
        return encerradas

    @_sincronizado
    def encerrar_todas(self) -> list[int]:
        """D05 e E04: tudo que tem duração volta ao normal agora."""
        encerradas = [pendente.intervencao_id for pendente in self.pendentes]
        for pendente in list(self.pendentes):
            self._encerrar(pendente, ultima_tentativa=True)
        return encerradas

    def _encerrar(self, pendente: Pendente, ultima_tentativa: bool = False) -> None:
        if pendente.volta is not None:
            self._encerrar_mundo(pendente, ultima_tentativa)
            return
        try:
            if pendente.alavanca == "pausa":
                self.cliente.pausar(False)
            elif pendente.alavanca in MODO_POR_ALAVANCA:
                self.cliente.velocidade(p.ModoVelocidade.NORMAL, 1.0, 0)
        except (CanalError, ComandoFalhouError):
            pass
        banco.preencher_uma_vez(
            self.con, "intervencoes", pendente.intervencao_id, {"fim_ms": self.contador.agora_ms()}
        )
        self.pendentes.remove(pendente)

    def _encerrar_mundo(self, pendente: Pendente, ultima_tentativa: bool = False) -> None:
        """No prazo: devolve o que tirou e registra o fim como intervenção de encerramento. Canal caído na hora
        da volta não perde a volta: a pendente fica e o próximo ciclo tenta de novo, até o limite ou o fim da
        sessão."""
        acao = _mundo(self.catalogo, pendente.alavanca)
        assert acao is not None and pendente.volta is not None
        try:
            feito = self._devolver_valor(acao, pendente.volta)
        except (CanalError, ComandoFalhouError, memoria.AlvoNaoResolvidoError) as erro:
            pendente.tentativas += 1
            if not ultima_tentativa and pendente.tentativas < VOLTA_TENTATIVAS:
                return  # tenta de novo no próximo ciclo
            self._registrar_fim(pendente, "falhou", {"erro": str(erro), "tentativas": pendente.tentativas})
            self.pendentes.remove(pendente)
            return
        parametros: dict[str, object] = dict(feito)
        if feito.get("alvo_mudou"):
            resultado = "descartada"
            parametros["motivo"] = (
                "o alvo já não é o mesmo (ponteiro, vetor, vaga ou tipo mudou): sem escrita"
            )
        elif feito["valor_no_fim"] <= 0:
            resultado = "descartada"
            parametros["motivo"] = "valor em zero no fim: sem escrita"
        else:
            resultado = "confirmada"
        self._registrar_fim(pendente, resultado, parametros)
        self.pendentes.remove(pendente)

    # ---------- D03 ----------
    @_sincronizado
    def reverter(self, ciclo_id: int) -> Execucao | None:
        """Desfaz a última intervenção reversível pelo caminho próprio dela. None se não há o que reverter."""
        ultima = self.ultima_reversivel
        if ultima is None:
            return None
        antes = self._estado_seguro(None)
        decisao_id = banco.gravar_decisao(
            self.con,
            {
                "ciclo_id": ciclo_id,
                "catalogo_versao": self.catalogo.versao,
                "alavanca": ultima.alavanca,
                "parametros_json": "{}",
                "motivo": "Desfeito pelo jogador.",
                "motivo_origem": "padrao",
                "origem": "servico",
                "pedido_bruto": "",
            },
        )
        reversao_id = banco.gravar_intervencao(
            self.con,
            {
                "decisao_id": decisao_id,
                "alavanca": ultima.alavanca,
                "parametros_json": json.dumps(ultima.caminho_volta or {}),
                "origem": "reversao_jogador",
                "estado_antes_json": json.dumps(antes, ensure_ascii=False),
                "comando_ms": self.contador.agora_ms(),
                "reversivel": 0,
            },
        )
        try:
            self._desfazer(ultima)
            resultado = "confirmada"
            detalhe = None
        except (CanalError, ComandoFalhouError, RecargaNaoConfirmadaError) as erro:
            resultado, detalhe = "falhou", str(erro)
        depois = self._estado_seguro(None)
        campos: dict[str, object] = {
            "resultado": resultado,
            "estado_depois_json": json.dumps(depois, ensure_ascii=False),
        }
        if resultado == "confirmada":
            campos["confirmado_ms"] = self.contador.agora_ms()
        banco.preencher_uma_vez(self.con, "intervencoes", reversao_id, campos)
        banco.preencher_uma_vez(
            self.con, "intervencoes", ultima.intervencao_id, {"revertida_por": reversao_id}
        )
        banco.gravar_marco(self.con, ciclo_id, "reversao", ultima.alavanca)
        self.ultima_reversivel = None
        return Execucao(reversao_id, ultima.alavanca, resultado, detalhe)

    def _desfazer(self, ultima: Execucao) -> None:
        pendente = next((x for x in self.pendentes if x.intervencao_id == ultima.intervencao_id), None)
        if _mundo(self.catalogo, ultima.alavanca) is not None:
            if pendente is not None:
                self._encerrar_mundo(pendente)  # antes do prazo: devolve agora
            return  # já devolvido no prazo: nada a desfazer no jogo
        if ultima.alavanca in COM_DURACAO:
            if pendente is not None:
                self._encerrar(pendente)  # ainda em vigor: encerra agora
            return  # já acabou: nada a desfazer no emulador, só o sinal ao mestre
        if ultima.alavanca == "recarregar" and ultima.caminho_volta:
            self.slots.recarregar(
                self.cliente, int(ultima.caminho_volta["slot"])
            )  # a única recarga sem salvar antes
            return
        # salvar_estado não é reversível; nunca chega aqui
