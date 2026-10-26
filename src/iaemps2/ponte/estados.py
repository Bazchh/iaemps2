"""Slots de estado reservados ao mestre (card S1-03; casos A05 e A06; decisão DC-15).

O emulador salva e recarrega estado de forma assíncrona e reporta erro só na própria tela (LC-11). Por isso
salvar só conta quando o arquivo do slot existe e tem o mesmo tamanho em duas leituras seguidas; recarregar
só conta quando o status volta a "rodando". Os slots do jogador (1 a 10) nunca são tocados: a fila recusa.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

SLOTS_DO_JOGADOR = range(1, 11)


class SlotError(ValueError):
    """Configuração de slot que tocaria no que é do jogador."""


class SalvamentoNaoConfirmadoError(RuntimeError):
    """O arquivo do slot não apareceu ou não estabilizou no tempo limite."""


class RecargaNaoConfirmadaError(RuntimeError):
    """Depois de recarregar, o status não voltou a 'rodando' no tempo limite."""


@dataclass(frozen=True)
class EstadoSalvo:
    slot: int
    arquivo: Path
    bytes: int
    salvo_s: float  # do comando até a confirmação


def nome_do_arquivo(serial: str, crc: str, slot: int) -> str:
    """Como o emulador nomeia: 'SERIAL (CRC maiúsculo com 8 dígitos).NN.p2s'."""
    return f"{serial} ({int(crc, 16):08X}).{slot:02d}.p2s"


class FilaDeSlots:
    """Os slots reservados de um jogo, usados em rodízio: o próximo é sempre o mais antigo."""

    def __init__(
        self,
        pasta_estados: Path,
        serial: str,
        crc: str,
        slots: list[int],
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        invasores = sorted(s for s in slots if s in SLOTS_DO_JOGADOR)
        if invasores:
            raise SlotError(f"slots {invasores} são do jogador (1 a 10) e nunca do mestre (DC-15)")
        if not slots:
            raise SlotError("nenhum slot reservado configurado")
        self.pasta = pasta_estados
        self.serial = serial
        self.crc = crc
        self.slots = list(slots)
        self.relogio = relogio
        self.dormir = dormir

    def arquivo(self, slot: int) -> Path:
        return self.pasta / nome_do_arquivo(self.serial, self.crc, slot)

    def proximo_slot(self) -> int:
        """Slot vazio primeiro; senão o de arquivo mais antigo (a fila avança por cima dele)."""
        vazios = [s for s in self.slots if not self.arquivo(s).exists()]
        if vazios:
            return vazios[0]
        return min(self.slots, key=lambda s: self.arquivo(s).stat().st_mtime)

    def ocupados(self) -> list[int]:
        return [s for s in self.slots if self.arquivo(s).exists()]

    def salvar(
        self, cliente: Cliente, slot: int | None = None, limite_s: float = 10.0, intervalo_s: float = 0.3
    ) -> EstadoSalvo:
        """Manda salvar e confirma pelo arquivo: existe e tem tamanho igual em duas leituras com o intervalo."""
        slot = self.proximo_slot() if slot is None else slot
        if slot not in self.slots:
            raise SlotError(f"slot {slot} não é reservado ao mestre")
        arquivo = self.arquivo(slot)
        tamanho_antes = arquivo.stat().st_size if arquivo.exists() else -1
        mtime_antes = arquivo.stat().st_mtime if arquivo.exists() else -1.0
        inicio = self.relogio()
        cliente.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([slot])))
        ultimo = -1
        while self.relogio() - inicio < limite_s:
            if arquivo.exists():
                st = arquivo.stat()
                novo = st.st_mtime != mtime_antes or st.st_size != tamanho_antes
                if novo and st.st_size > 0 and st.st_size == ultimo:
                    return EstadoSalvo(slot, arquivo, st.st_size, self.relogio() - inicio)
                ultimo = st.st_size if novo else -1
            self.dormir(intervalo_s)
        raise SalvamentoNaoConfirmadoError(
            f"slot {slot}: arquivo não estabilizou em {limite_s:.0f} s ({arquivo.name})"
        )

    def recarregar(
        self, cliente: Cliente, slot: int, limite_s: float = 10.0, intervalo_s: float = 0.3
    ) -> float:
        """Manda recarregar e confirma pelo status 'rodando'. Devolve o tempo até a confirmação."""
        if slot not in self.slots:
            raise SlotError(f"slot {slot} não é reservado ao mestre")
        if not self.arquivo(slot).exists():
            raise RecargaNaoConfirmadaError(f"slot {slot} está vazio ({self.arquivo(slot).name})")
        inicio = self.relogio()
        cliente.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([slot])))
        while self.relogio() - inicio < limite_s:
            if cliente.status() == p.Status.RODANDO:
                return self.relogio() - inicio
            self.dormir(intervalo_s)
        raise RecargaNaoConfirmadaError(f"slot {slot}: status não voltou a rodando em {limite_s:.0f} s")

    def recarregar_com_volta(self, cliente: Cliente, slot: int, **kw: float) -> tuple[EstadoSalvo, float]:
        """A06: salva o estado atual num slot reservado antes, para a própria recarga ser reversível."""
        if slot not in self.slots:
            raise SlotError(f"slot {slot} não é reservado ao mestre")
        candidatos = [s for s in self.slots if s != slot]
        volta_slot = next((s for s in candidatos if not self.arquivo(s).exists()), None)
        if volta_slot is None:
            volta_slot = min(candidatos, key=lambda s: self.arquivo(s).stat().st_mtime)
        volta = self.salvar(cliente, volta_slot, **kw)
        self.recarregar(cliente, slot, **kw)
        return volta, self.relogio()
