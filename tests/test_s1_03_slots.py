"""Card S1-03: slots reservados com confirmação pelo arquivo.

Critério de aceite: dado o jogo rodando, quando a ponte salva no slot da fila e recarrega, então o arquivo é
confirmado em menos de 3 s, o status volta a "rodando", e os slots 1 a 10 continuam intocados.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from iaemps2.ponte import estados
from iaemps2.ponte.cliente import Cliente
from iaemps2.simulador.servidor import Simulador

SLOTS = list(range(90, 100))


def test_nome_do_arquivo_como_o_emulador() -> None:
    assert estados.nome_do_arquivo("SLUS-21134", "013e349d", 90) == "SLUS-21134 (013E349D).90.p2s"


def test_fila_recusa_slots_do_jogador(tmp_path: Path) -> None:
    with pytest.raises(estados.SlotError, match="DC-15"):
        estados.FilaDeSlots(tmp_path, "S", "0", [5, 12])
    with pytest.raises(estados.SlotError):
        estados.FilaDeSlots(tmp_path, "S", "0", [])


def test_salva_confirma_e_recarrega(tmp_path: Path) -> None:
    with (
        Simulador(pasta_estados=tmp_path, atraso_salvamento_s=0.3) as sim,
        Cliente(porta=sim.porta or 0) as c,
    ):
        fila = estados.FilaDeSlots(tmp_path, "SLUS-21134", "013e349d", SLOTS)
        assert fila.proximo_slot() == 90
        salvo = fila.salvar(c)
        assert salvo.slot == 90 and salvo.arquivo.name == "SLUS-21134 (013E349D).90.p2s"
        assert salvo.bytes == 16 * 4000 and salvo.salvo_s < 3
        assert fila.proximo_slot() == 91
        assert fila.recarregar(c, 90, intervalo_s=0.05) < 3
        assert not any(
            (tmp_path / estados.nome_do_arquivo("SLUS-21134", "013e349d", s)).exists() for s in range(1, 11)
        )


def test_fila_avanca_por_cima_do_mais_antigo(tmp_path: Path) -> None:
    fila = estados.FilaDeSlots(tmp_path, "S", "1", [90, 91, 92])
    for s, idade in ((90, 300), (91, 100), (92, 200)):
        arq = fila.arquivo(s)
        arq.write_bytes(b"x")
        os.utime(arq, (time.time() - idade, time.time() - idade))
    assert fila.ocupados() == [90, 91, 92]
    assert fila.proximo_slot() == 90  # o mais antigo


def test_salvamento_que_nunca_aparece_nao_conta(tmp_path: Path) -> None:
    agora = [0.0]

    def dormir(s: float) -> None:
        agora[0] += s

    with (
        Simulador(pasta_estados=tmp_path, cenarios={"salvamento_nunca_aparece": 1}) as sim,
        Cliente(porta=sim.porta or 0) as c,
    ):
        fila = estados.FilaDeSlots(
            tmp_path, "SLUS-21134", "013e349d", SLOTS, relogio=lambda: agora[0], dormir=dormir
        )
        with pytest.raises(estados.SalvamentoNaoConfirmadoError):
            fila.salvar(c, limite_s=10)
        assert agora[0] >= 10


def test_existe_nao_e_pronto(tmp_path: Path) -> None:
    """O arquivo aparece parcial e cresce: a confirmação espera o tamanho estabilizar (LC-11)."""
    with (
        Simulador(pasta_estados=tmp_path, atraso_salvamento_s=0.6) as sim,
        Cliente(porta=sim.porta or 0) as c,
    ):
        fila = estados.FilaDeSlots(tmp_path, "SLUS-21134", "013e349d", SLOTS)
        salvo = fila.salvar(c)
        assert salvo.bytes == 16 * 4000  # o tamanho final, não um parcial


def test_recarregar_slot_vazio_e_recusado(tmp_path: Path) -> None:
    with Simulador(pasta_estados=tmp_path) as sim, Cliente(porta=sim.porta or 0) as c:
        fila = estados.FilaDeSlots(tmp_path, "SLUS-21134", "013e349d", SLOTS)
        with pytest.raises(estados.RecargaNaoConfirmadaError, match="vazio"):
            fila.recarregar(c, 95)


def test_recarga_com_volta_salva_antes(tmp_path: Path) -> None:
    with (
        Simulador(pasta_estados=tmp_path, atraso_salvamento_s=0.2) as sim,
        Cliente(porta=sim.porta or 0) as c,
    ):
        fila = estados.FilaDeSlots(tmp_path, "SLUS-21134", "013e349d", SLOTS)
        destino = fila.salvar(c, 93)
        volta, _ = fila.recarregar_com_volta(c, destino.slot)
        assert volta.slot != destino.slot and volta.arquivo.exists()
        assert sorted(fila.ocupados()) == sorted([destino.slot, volta.slot])


@pytest.mark.emulador
def test_emulador_real_salva_e_recarrega_no_slot_reservado() -> None:
    pasta = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PCSX2" / "sstates"
    with Cliente() as c:
        fila = estados.FilaDeSlots(pasta, "SLUS-21134", "013e349d", [91])
        salvo = fila.salvar(c)
        assert salvo.bytes > 1_000_000 and salvo.salvo_s < 3
        assert fila.recarregar(c, 91) < 3
        assert not any(
            (pasta / estados.nome_do_arquivo("SLUS-21134", "013e349d", s)).exists() for s in range(1, 11)
        )
