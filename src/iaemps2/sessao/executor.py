"""Executar e reverter pelo caso de uso de cada alavanca (card S3-04; casos D02 e D03; A03 a A06).

Nenhuma ação chega ao emulador sem passar pelo catálogo, pelo intervalo e pelo registro, e toda ação tem
volta. O executor recebe um veredito já conferido (S3-03), relê o emulador (validação 2), grava o estado
antes, despacha para a ponte pelo caso de uso da alavanca, confirma, grava o estado depois e marca a
intervenção como reversível. Reverter usa o caminho próprio de cada alavanca. Falha de execução não é
repetida no ciclo; três seguidas tiram a alavanca do catálogo.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from iaemps2.catalogo import catalogo as cat
from iaemps2.mestre.decisao import Veredito, situacao_mudou
from iaemps2.olho.situacao import Situacao
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.ponte.estados import FilaDeSlots, RecargaNaoConfirmadaError, SalvamentoNaoConfirmadoError
from iaemps2.registro import banco
from iaemps2.sessao.relogio import Contador

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


@dataclass
class Pendente:
    intervencao_id: int
    alavanca: str
    fim_ms: int


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

    # ---------- estado do emulador para o registro ----------
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
        except (
            CanalError,
            ComandoFalhouError,
            SalvamentoNaoConfirmadoError,
            RecargaNaoConfirmadaError,
        ) as erro:
            depois = self._estado_seguro(situacao)
            banco.preencher_uma_vez(
                self.con,
                "intervencoes",
                intervencao_id,
                {"resultado": "falhou", "estado_depois_json": json.dumps(depois, ensure_ascii=False)},
            )
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
            self.pendentes.append(Pendente(intervencao_id, veredito.alavanca, fim))
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
            self._salvar(situacao, "antes_recarga", slot=volta_slot)
            self.slots.recarregar(self.cliente, slot)
            return None, {"slot": float(volta_slot)}
        raise ComandoFalhouError(f"alavanca sem executor: {v.alavanca}")

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

    def salvar_periodico(self, situacao: Situacao | None) -> int | None:
        """O salvamento de rotina da intensidade (A05), fora do catálogo de decisões."""
        try:
            return self._salvar(situacao, "periodico")
        except (CanalError, ComandoFalhouError, SalvamentoNaoConfirmadoError):
            return None

    # ---------- fim das ações com duração ----------
    def encerrar_vencidos(self, agora_ms: int | None = None) -> list[int]:
        """Pausa termina pela plataforma; velocidade termina pelo vigia do emulador. Grava o fim de ambas."""
        agora = self.contador.agora_ms() if agora_ms is None else agora_ms
        encerradas: list[int] = []
        for pendente in list(self.pendentes):
            if agora < pendente.fim_ms:
                continue
            self._encerrar(pendente)
            encerradas.append(pendente.intervencao_id)
        return encerradas

    def encerrar_todas(self) -> list[int]:
        """D05 e E04: tudo que tem duração volta ao normal agora."""
        encerradas = [pendente.intervencao_id for pendente in self.pendentes]
        for pendente in list(self.pendentes):
            self._encerrar(pendente)
        return encerradas

    def _encerrar(self, pendente: Pendente) -> None:
        try:
            if pendente.alavanca == "pausa":
                self.cliente.pausar(False)
            else:
                self.cliente.velocidade(p.ModoVelocidade.NORMAL, 1.0, 0)
        except (CanalError, ComandoFalhouError):
            pass
        banco.preencher_uma_vez(
            self.con, "intervencoes", pendente.intervencao_id, {"fim_ms": self.contador.agora_ms()}
        )
        self.pendentes.remove(pendente)

    # ---------- D03 ----------
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
