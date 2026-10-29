"""Card S8-02: chamada remota de função do jogo pelo canal, contra o simulador.

Critério (parte automática): dado o canal em modo próprio, quando a ponte pede uma chamada com função e
argumentos, então o pedido chega inteiro ao emulador e a resposta traz estado, v0 e v1; com o jogo parado a chamada
é recusada; o emulador original não anuncia a capacidade. A execução de verdade só se prova no emulador real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente, ComandoFalhouError
from iaemps2.ponte.emulador import identificar
from iaemps2.simulador.servidor import Simulador


def test_chamada_chega_inteira_e_volta_v0_v1(tmp_path: Path) -> None:
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        assert identificar(c).capacidades.chamada

        sim.resposta_chamada = (0, 0x01794230, 7)
        r = c.chamar(0x001BD800, (AREA_DO_MESTRE, 2), tempo_limite_ms=500)
        assert r.ok and (r.v0, r.v1) == (0x01794230, 7)
        assert sim.chamadas == [(0x001BD800, (AREA_DO_MESTRE, 2), 500, 0)]

        sim.resposta_chamada = (1, 0, 0)
        r = c.chamar(0x00100000)
        assert r.estado == "prazo" and not r.ok

        sim.resposta_chamada = (3, 0, 0)
        r = c.chamar(0x00100000, (), 500, ancora_endereco=0x004327C0)
        assert r.estado == "perdida" and sim.chamadas[-1] == (0x00100000, (), 500, 0x004327C0)

        with pytest.raises(ValueError):
            c.chamar(0x00100000, (1, 2, 3, 4, 5))


def test_chamada_recusada_com_o_jogo_parado(tmp_path: Path) -> None:
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        c.pausar(True)
        r = c.chamar(0x001BD800, (AREA_DO_MESTRE,))
        assert r.estado == "recusada" and sim.chamadas == []
        c.pausar(False)


def test_chamada_nao_existe_no_emulador_original(tmp_path: Path) -> None:
    with Simulador("original", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        assert not identificar(c).capacidades.chamada
        with pytest.raises(ComandoFalhouError):
            c.chamar(0x001BD800)
