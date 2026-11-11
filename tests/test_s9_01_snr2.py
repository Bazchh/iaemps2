"""Card S9-01: realocador do formato SNR2, lido no ligador do jogo.

Critério (parte automática): um módulo sintético com uma seção importada, uma definida, um fluxo comprimido com
os quatro tipos (metade baixa, metade alta, salto de 26 bits, palavra) e uma realocação simbólica sai realocado
para a base pedida, com o endereço importado vindo da tabela do executável; a prova de verdade, contra os módulos
vivos na memória do jogo, está em docs/medicoes (em12, em2a e em23: só as palavras de tempo de execução diferem).
"""

from __future__ import annotations

import struct

import pytest

from iaemps2.bancada import snr2


def modulo_sintetico() -> bytes:
    """Cabeçalho + nomes + seções + código + fluxo + lista simbólica, com os deslocamentos de arquivo."""
    nomes = 0x40
    nome_imp, nome_def = b"EmSetEvent\0", b"minha_funcao\0"
    secoes = 0x60  # 2 seções de 12 bytes
    codigo = 0x80
    # lui t0, 0 ; addiu t0, t0, 0x10 ; jal 0x20 ; .word 0x30 ; .word 0 (recebe a simbólica)
    instrs = [0x3C080000, 0x25080010, 0x0C000008, 0x00000030, 0x00000000]
    fluxo = 0x100
    # fluxo: posição absoluta 0x80 tipo 1 (alta), avança 4 tipo 0 (baixa), avança 4 tipo 2 (salto), avança 4 tipo 3 (palavra), fim
    bytes_fluxo = (
        bytes([0x01]) + struct.pack("<I", codigo) + bytes([0x04, 0x06, 0x07, 0x00]) + struct.pack("<I", 0)
    )
    lista = 0x120  # 1 realocação simbólica: palavra em 0x90 = seção 0 (importada) + 8
    entradas = struct.pack("<III", codigo + 16, 2 | (0 << 8), 8)
    cab = [0] * 16
    cab[0] = int.from_bytes(b"SNR2", "little")
    cab[1], cab[2] = lista, 1
    cab[3], cab[4] = secoes, 2
    cab[6] = codigo
    cab[10] = 0x80
    cab[11] = 0x140
    cab[13] = fluxo
    d = bytearray(0x140)
    struct.pack_into("<16I", d, 0, *cab)
    d[nomes : nomes + len(nome_imp)] = nome_imp
    d[nomes + 0x10 : nomes + 0x10 + len(nome_def)] = nome_def
    struct.pack_into("<IIHBB", d, secoes, nomes, 0, 0, 1, 0)  # importada
    struct.pack_into("<IIHBB", d, secoes + 12, nomes + 0x10, codigo, 0, 2, 0)  # definida em 0x80
    struct.pack_into("<5I", d, codigo, *instrs)
    d[fluxo : fluxo + len(bytes_fluxo)] = bytes_fluxo
    d[lista : lista + 12] = entradas
    return bytes(d)


def test_realoca_modulo_sintetico() -> None:
    base = 0x08000000
    mod = snr2.realocar(modulo_sintetico(), base, {"EmSetEvent": 0x001BD800})
    assert mod.nao_resolvidos == []
    assert mod.entrada == base + 0x80
    assert mod.simbolos() == [(base + 0x80, "minha_funcao")]
    assert mod.secoes[0].endereco == 0x001BD800 and mod.secoes[1].endereco == base + 0x80
    lui, addiu, jal, palavra, simbolica = struct.unpack_from("<5I", mod.dados, 0x80)
    assert lui == 0x3C080800 and addiu == 0x25080010  # base + 0x10 = 0x08000010: alta 0x0800, baixa 0x0010
    assert jal == 0x0C000000 | ((base + 0x20) >> 2)
    assert palavra == base + 0x30
    assert simbolica == 0x001BD800 + 8
    assert struct.unpack_from("<I", mod.dados, 0x0C)[0] == base + 0x60  # ponteiro do cabeçalho somado à base


def test_recusa_o_que_nao_e_snr2_e_base_desalinhada() -> None:
    with pytest.raises(snr2.LigacaoError):
        snr2.realocar(b"ELF\0" + bytes(60), 0x08000000, {})
    with pytest.raises(snr2.LigacaoError):
        snr2.realocar(modulo_sintetico(), 0x08000010, {})


def test_importacao_sem_resolucao_fica_zero() -> None:
    mod = snr2.realocar(modulo_sintetico(), 0x08000000, {})
    assert mod.nao_resolvidos == ["EmSetEvent"] and mod.secoes[0].endereco == 0
    assert struct.unpack_from("<I", mod.dados, 0x90)[0] == 8
