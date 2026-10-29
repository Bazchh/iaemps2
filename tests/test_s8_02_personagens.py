"""Card S8-02: criar um personagem pela chamada remota, com a struct que o jogo monta num evento.

Critério (parte automática): a struct de 32 bytes tem o formato lido no código (tipo em +1, +4 = 1, vida em +8,
posição em centímetros em +0xC, sala em +0x18, +0x1A = 1); o ponto à frente segue a direção da câmera; contra o
simulador, o comando grava a struct na página do mestre e pede a chamada de EmSetEvent com o ponteiro para ela.
"""

from __future__ import annotations

import struct
from pathlib import Path

from iaemps2.bancada import personagens as pz
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente
from iaemps2.simulador.servidor import Simulador


def test_struct_como_o_evento_do_jogo() -> None:
    dados = pz.montar_struct(0x12, 0, 1000, (-77630.0, 860.0, -36500.0), 0x0100)
    assert len(dados) == 32
    assert dados[0:4] == bytes([0, 0x12, 0, 0]) and struct.unpack_from("<I", dados, 4)[0] == 1
    assert struct.unpack_from("<H", dados, 8)[0] == 1000
    assert struct.unpack_from("<hhh", dados, 0xC) == (-7763, 86, -3650)
    assert struct.unpack_from("<hhh", dados, 0x12) == (0, 0, 0)
    assert struct.unpack_from("<Hh", dados, 0x18) == (0x0100, 1)


def test_ponto_a_frente_segue_a_camera() -> None:
    jogador = (1000.0, 0.0, 1000.0)
    ponto = pz.a_frente(
        jogador, olho=(1000.0, 1500.0, -2000.0), alvo=(1000.0, 900.0, 1000.0), distancia_mm=2000.0
    )
    assert ponto == (1000.0, 0.0, 3000.0)
    ponto = pz.a_frente(jogador, olho=(4000.0, 0.0, 1000.0), alvo=(1000.0, 0.0, 1000.0), distancia_mm=500.0)
    assert ponto == (500.0, 0.0, 1000.0)


def test_criar_contra_o_simulador(tmp_path: Path) -> None:
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        mem = sim.jogo.memoria
        struct.pack_into("<fff", mem, pz.VETOR + 0xC0, 100.0, 0.0, 200.0)
        struct.pack_into("<fff", mem, pz.CAMERA_OLHO, 100.0, 1000.0, -1000.0)
        struct.pack_into("<fff", mem, pz.CAMERA_ALVO, 100.0, 800.0, 200.0)
        struct.pack_into("<H", mem, pz.BLOCO_G + 0x7EB8, 0x0100)
        slot = 17
        base = pz.VETOR + slot * pz.PASSO
        struct.pack_into("<I", mem, base, 0x02002077)
        mem[base + 0x11C] = 0x12
        mem[base + 0x4C0] = 0xFF
        struct.pack_into("<hh", mem, base + 0x4B0, 1000, 1000)
        sim.resposta_chamada = (0, base, 0)

        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        r, q = pz.criar_personagem(c, 0x12, vida=1000, distancia_mm=2000.0)
        assert r.ok and q is not None and (q.slot, q.tipo, q.origem, q.vida) == (slot, 0x12, 0xFF, 1000)
        assert sim.chamadas == [(pz.EM_SET_EVENT, (AREA_DO_MESTRE,), 5000, 0)]
        gravada = bytes(mem[AREA_DO_MESTRE : AREA_DO_MESTRE + 32])
        assert gravada == pz.montar_struct(0x12, 0, 1000, (100.0, 0.0, 2200.0), 0x0100)

        sim.resposta_chamada = (0, 0, 0)  # errEm
        r, q = pz.criar_personagem(c, 0x03)
        assert r.ok and q is None
        c.fechar()
