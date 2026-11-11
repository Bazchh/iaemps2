"""Card S8-01: dar um item pelo canal, com a regra da maleta lida no código do jogo.

Critério (parte automática): dada a grade observada ao vivo (pistola 3x2 em (0,0), balas 2x1 em (3,0), erva 1x2
em (3,1)), o lança-foguetes 8x2 cabe em (0,3) e não antes; o item gravado tem a forma que ``cItemMgr::construct``
dá (ocupado, dono, carga do nível 1 vezes 8) e a posição como centro em meias-células; contra o simulador, o
comando grava o slot livre e aponta o gerenciador para ele.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from iaemps2.bancada import inventario as inv
from iaemps2.ponte.cliente import Cliente
from iaemps2.simulador.servidor import Simulador

VETOR = 0x010F6540
PISTOLA, BALAS, ERVA, BAZUCA = 0x23, 0x04, 0x05, 0x35
# os três itens vistos ao vivo em 28/10 (slots 1, 2 e 3) e a faca (slot 0, sem peça)
ITENS_VIVOS = {
    0: bytes.fromhex("7c00010001000000000000000000"),
    1: bytes.fromhex("2300010001000000500002010001"),
    2: bytes.fromhex("0400140001000000000007000001"),
    3: bytes.fromhex("0500010001000000000006030001"),
}


def peca(id_: int, largura: int, altura: int, cx: float, cy: float) -> bytes:
    cabecalho = struct.pack(
        "<HBBBBxxff", id_, 0, 0, largura, altura, cx, cy
    )  # floats em +8 e +0xC, grade em +0x10
    return cabecalho + (b"1" * (largura * altura)).ljust(0x48, b"\0")


def tabela_de_pecas() -> bytes:
    return (
        peca(PISTOLA, 3, 2, 1.0, 0.5)
        + peca(BALAS, 2, 1, 0.5, 0.0)
        + peca(ERVA, 1, 2, 0.0, 0.5)
        + peca(BAZUCA, 8, 2, 3.5, 0.5)
        + b"\xff\xff"
    )


def tabela_de_armas() -> bytes:
    entradas = {PISTOLA: (0x04, 10), BAZUCA: (0xFF, 1)}
    saida = b""
    for id_, (municao, capacidade) in entradas.items():
        saida += struct.pack("<HBBBBH", id_, 0, 0, 0, 0, municao).ljust(8, b"\0") + struct.pack(
            "<H", capacidade
        )
        saida = saida.ljust(len(saida) + (0x16 - len(saida) % 0x16) % 0x16, b"\0")
    return saida.ljust(inv.ARMAS * 0x16, b"\0")


def itens_vivos() -> list[inv.Item]:
    return [inv.Item.dos_bytes(s, b) for s, b in ITENS_VIVOS.items()]


def test_tabelas_lidas_como_no_jogo() -> None:
    pecas = inv.pecas(tabela_de_pecas())
    assert pecas[BAZUCA] == inv.Peca(BAZUCA, 8, 2, 3.5, 0.5) and 0x7C not in pecas
    assert inv.armas(tabela_de_armas()) == {PISTOLA: (0x04, 10), BAZUCA: (0xFF, 1)}


def test_posicao_do_item_e_o_centro_em_meias_celulas() -> None:
    pecas = inv.pecas(tabela_de_pecas())
    cantos = {i.id: i.canto(pecas[i.id]) for i in itens_vivos() if i.id in pecas}
    assert cantos == {PISTOLA: (0, 0), BALAS: (3, 0), ERVA: (3, 1)}


def test_ocupacao_e_encaixe_na_ordem_do_jogo() -> None:
    pecas = inv.pecas(tabela_de_pecas())
    grade = inv.ocupacao(itens_vivos(), pecas, 10, 6)
    assert ["".join("#" if x else "." for x in linha) for linha in grade] == [
        "#####.....",
        "####......",
        "...#......",
        "..........",
        "..........",
        "..........",
    ]
    assert inv.encaixar(grade, 8, 2) == (0, 3)
    assert inv.encaixar(grade, 2, 1) == (5, 0)
    assert inv.encaixar(grade, 8, 4) is None


def test_item_montado_como_construct() -> None:
    pecas = inv.pecas(tabela_de_pecas())
    item = inv.montar_item(6, BAZUCA, 1, 0, pecas[BAZUCA], (0xFF, 1), (0, 4))
    assert item.para_bytes() == bytes.fromhex(
        "3500010001000000080007090001"
    )  # o que apareceu na maleta em 28/10
    balas = inv.montar_item(7, BALAS, 20, 0, pecas[BALAS], None, (4, 0))
    assert (balas.quantidade, balas.carga_x8, balas.x2, balas.y2) == (20, 0, 9, 0)
    assert inv.Item.dos_bytes(6, item.para_bytes()) == item


def test_dar_item_contra_o_simulador(tmp_path: Path) -> None:
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        mem = sim.jogo.memoria
        mem[inv.GERENCIADOR + 0x13] = 0
        struct.pack_into("<I", mem, inv.GERENCIADOR + 0x14, VETOR)
        struct.pack_into("<I", mem, inv.GERENCIADOR + 0x1C, 384)
        for slot, dados in ITENS_VIVOS.items():
            mem[VETOR + slot * 14 : VETOR + slot * 14 + 14] = dados
        tabela = tabela_de_pecas()
        mem[inv.TABELA_PECAS : inv.TABELA_PECAS + len(tabela)] = tabela
        tabela = tabela_de_armas()
        mem[inv.TABELA_ARMAS : inv.TABELA_ARMAS + len(tabela)] = tabela

        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        item = inv.dar_item(c, BAZUCA, 1)
        assert item.slot == 4 and item.canto(inv.pecas(tabela_de_pecas())[BAZUCA]) == (0, 3)
        assert bytes(mem[VETOR + 4 * 14 : VETOR + 5 * 14]) == bytes.fromhex("3500010001000000080007070001")
        assert struct.unpack_from("<I", mem, inv.GERENCIADOR + 0x18)[0] == VETOR + 4 * 14
        with pytest.raises(ValueError, match="não tem dados de peça"):
            inv.dar_item(c, 0x7C, 1)
        c.fechar()
