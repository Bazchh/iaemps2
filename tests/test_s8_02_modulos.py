"""Card S8-02: carregar um módulo de personagem pela memória, com o jogo realocando e inicializando.

Critério (parte automática): o leitor do AFS acha nome, deslocamento e tamanho de cada arquivo (cabeçalho, pares
e tabela de nomes de 48 bytes); contra o simulador, ``carregar`` escreve o .dat e o .rel na área livre, preenche a
entrada livre da tabela de módulos com os tamanhos arredondados a 0x800 e pede ao jogo a inicialização e a busca.
A prova de que o jogo aceita o módulo é só no emulador real (feita em 29/10 com o tipo 3).
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from iaemps2.bancada import modulos as md
from iaemps2.ponte.cliente import Cliente
from iaemps2.simulador.servidor import Simulador


def afs_sintetico(caminho: Path, arquivos: list[tuple[str, bytes]]) -> None:
    """Grava um AFS com os arquivos dados, começando no setor que o módulo espera."""
    n = len(arquivos)
    cabecalho = 8 + 8 * (n + 1)
    corpo, tabela, off = b"", b"", (cabecalho + 0x7FF) & ~0x7FF
    for _nome, dados in arquivos:
        tabela += struct.pack("<II", off + len(corpo), len(dados))
        corpo += dados.ljust((len(dados) + 0x7FF) & ~0x7FF, b"\0")
    nomes = b"".join(nome.encode().ljust(32, b"\0") + bytes(16) for nome, _ in arquivos)
    tabela += struct.pack("<II", off + len(corpo), len(nomes))
    conteudo = (b"AFS\0" + struct.pack("<I", n) + tabela).ljust(off, b"\0") + corpo + nomes
    with caminho.open("wb") as f:
        f.seek(md.AFS_SETOR * 2048)
        f.write(conteudo)


def test_leitor_do_afs(tmp_path: Path) -> None:
    iso = tmp_path / "jogo.iso"
    afs_sintetico(
        iso,
        [
            ("datinfo.dat", b"x" * 10),
            ("pl11.dat", b"D" * 2000),
            ("", b""),
            ("pl11.rel", b"SNR2" + b"R" * 100),
        ],
    )
    afs = md.Afs(iso)
    assert afs.n == 4 and afs.nomes[1] == "pl11.dat" and afs.nomes[3] == "pl11.rel"
    assert afs.arquivo(1).tamanho == 2000 and afs.ler(1) == b"D" * 2000
    assert afs.ler(3)[:4] == b"SNR2" and len(afs.ler(3)) == 104
    assert md.arredondar(2000) == 0x800 and md.arredondar(0x800) == 0x800 and md.arredondar(0x801) == 0x1000


def test_carregar_contra_o_simulador(tmp_path: Path) -> None:
    iso = tmp_path / "jogo.iso"
    dat, rel = b"D" * 3000, b"SNR2" + b"R" * 500
    afs_sintetico(iso, [("datinfo.dat", b"x"), ("pl11.dat", dat), ("", b""), ("pl11.rel", rel)])
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        mem = sim.jogo.memoria
        mem[md.PERSONAGEM] = 0
        struct.pack_into("<HHHH", mem, md.TABELA_ARQUIVOS[0] + 3 * 8, 1, 3, 0, 1)
        e0 = md.TABELA_MODULOS
        struct.pack_into(
            "<HHIIIII", mem, e0 + 0x80, 0x12, 7, 0x1882280, 0x1BAD300, 0x32B000, 0x6D000, 0x1BF8528
        )
        e1 = md.TABELA_MODULOS + md.TAMANHO_ENTRADA
        # duas alocações pelo jogo, a inicialização e a busca do módulo (que devolve a entrada usada)
        sim.respostas_chamada = [(0, 0x1500000, 0), (0, 0x1600000, 0), (0, 0, 0), (0, e1, 0)]

        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        entrada = md.carregar(c, 3, md.Afs(iso))
        assert entrada.indice == 1  # a primeira livre
        campos = struct.unpack_from("<HHIIIII", mem, e1 + 0x80)
        assert campos == (3, md.FLAGS_ALOCADO, 0x1500000, 0x1600000, 0x1000, 0x800, 0)
        assert (
            bytes(mem[0x1500000 : 0x1500000 + 3000]) == dat and bytes(mem[0x1600000 : 0x1600000 + 504]) == rel
        )
        assert [ch[0] for ch in sim.chamadas] == [
            md.TRAMPOLIM_ALOCAR,
            md.TRAMPOLIM_ALOCAR,
            md.REGISTRAR_MODULO,
            md.SEARCH_EM_MODULE,
        ]
        assert [ch[1] for ch in sim.chamadas] == [(0x1000,), (0x800,), (e1,), (3,)]
        assert struct.unpack_from("<7I", mem, md.TRAMPOLIM_ALOCAR) == tuple(md.CODIGO_ALOCAR)
        c.fechar()


def test_carregar_exige_entrada_livre(tmp_path: Path) -> None:
    iso = tmp_path / "jogo.iso"
    afs_sintetico(iso, [("a", b"1"), ("b", b"SNR2")])
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        mem = sim.jogo.memoria
        for i in range(4):
            struct.pack_into(
                "<HHI", mem, md.TABELA_MODULOS + i * md.TAMANHO_ENTRADA + 0x80, 0x10 + i, 7, 0x1000000
            )
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        with pytest.raises(ValueError, match="em uso"):
            md.carregar(c, 3, md.Afs(iso))
        c.fechar()
