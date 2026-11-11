"""Realocador do formato SNR2 (módulos ``.rel`` da SN Systems) do jogo de abertura, sem o jogo rodando.

Lido no ligador do próprio jogo (0x002A56B8: valida 0x002A4860, realoca 0x002A5108, aplica 0x002A4968). O
objetivo é o mapa completo (S9-01): cada módulo da ISO realocado para um endereço virtual e decompilado com os
nomes que ele mesmo declara, mais os que importa do executável.

Cabeçalho de 16 palavras: 0 "SNR2"; 1 lista de realocações simbólicas e 2 sua contagem (12 bytes cada: endereço,
tipo | índice de seção << 8, adendo); 3 tabela de seções e 4 sua contagem (12 bytes: nome, endereço, dica u16 em +8,
tipo em +10, flag em +11); 6 entrada (roda os construtores); 8 tabela de ponteiros e 9 contagem; 10 alinhamento;
11 tamanho; 13 fluxo comprimido de realocações. Seções tipo 0, 2 e 3 têm endereço dentro do módulo; tipo 1 importa
pelo nome, do executável (tabela de símbolos) ou de outro módulo já ligado.

Fluxo comprimido: um byte por passo; os bits altos (& 0xFC) avançam o cursor em bytes, ou, se zero, os 4 bytes
seguintes são a posição absoluta (0 = fim); os dois bits baixos dizem o tipo: 0 metade baixa de 16 bits, 1 metade
alta (lê adiante a metade baixa para somar com sinal), 2 salto de 26 bits, 3 palavra de 32 bits. Tudo é "somar a
base".
"""

from __future__ import annotations

import csv
import struct
from dataclasses import dataclass, field
from pathlib import Path

MAGIA = b"SNR2"


@dataclass
class Secao:
    indice: int
    nome: str
    endereco: int
    dica: int
    tipo: int
    flag: int


@dataclass
class Modulo:
    base: int
    dados: bytearray
    secoes: list[Secao]
    entrada: int
    nao_resolvidos: list[str] = field(default_factory=list)

    def simbolos(self) -> list[tuple[int, str]]:
        """Nomes definidos pelo módulo (tipos 2 e 3) com endereço realocado, para rotular no Ghidra."""
        return [(s.endereco, s.nome) for s in self.secoes if s.tipo in (2, 3) and s.endereco]


def carregar_simbolos_do_executavel(csv_simbolos: Path) -> dict[str, int]:
    saida: dict[str, int] = {}
    with csv_simbolos.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = int(r["endereco"], 16)
            saida.setdefault(r["decorado"], a)
            saida.setdefault(r["nome"], a)
    return saida


def _u32(d: bytes | bytearray, off: int) -> int:
    return int(struct.unpack_from("<I", d, off)[0])


def _texto(d: bytes | bytearray, off: int) -> str:
    fim = d.index(b"\0", off)
    return d[off:fim].decode("latin-1")


def _aplicar(d: bytearray, pos: int, tipo: int, valor: int) -> bool:
    """FUN_002A4968: grava o valor no formato do tipo; devolve False quando o ligador recusaria."""
    palavra = _u32(d, pos)
    valor &= 0xFFFFFFFF
    if tipo == 0:
        return True
    if tipo == 1:
        struct.pack_into("<H", d, pos, valor & 0xFFFF)
        return True
    if tipo == 2:
        struct.pack_into("<I", d, pos, valor)
        return True
    if tipo == 4:  # salto de 26 bits
        if (palavra & 0xFC00003F) == 0xD:
            return False
        struct.pack_into("<I", d, pos, (palavra & 0xFC000000) | ((valor >> 2) & 0x3FFFFFF))
        return True
    if tipo == 5:  # metade alta, arredondada pela metade baixa com sinal
        if (palavra & 0xFC00003F) == 0xD:
            return False
        struct.pack_into("<H", d, pos, ((valor + 0x8000) >> 16) & 0xFFFF)
        return True
    if tipo == 6:  # metade baixa
        if (palavra & 0xFC00003F) == 0xD:
            return False
        struct.pack_into("<H", d, pos, valor & 0xFFFF)
        return True
    if tipo == 0x77:
        struct.pack_into("<I", d, pos, (palavra & 0xFFE0003F) | ((valor & 0x3FFF8) << 3))
        return True
    if tipo == 0x78:
        struct.pack_into("<I", d, pos, (palavra & 0xFFFFF800) | (((valor - pos) >> 3) & 0x7FF))
        return True
    if tipo == 0x79:
        struct.pack_into("<I", d, pos, (palavra & 0x8000000F) | (valor & 0x7FFFFFF0))
        return True
    if tipo == 0x7A:
        struct.pack_into("<I", d, pos, (palavra & 0xFFFFF800) | ((valor >> 4) & 0x7FF))
        return True
    if tipo == 0x7B:
        struct.pack_into(
            "<I", d, pos, (palavra & 0xFE1FF800) | ((valor >> 3) & 0x7FF) | (((valor >> 3) & 0x7800) << 10)
        )
        return True
    return False


class LigacaoError(ValueError):
    pass


def _proximo_cursor(d: bytearray, p: int, cursor: int, base: int) -> tuple[int, int, int, bool]:
    """Um passo do fluxo: devolve (cursor novo, posição seguinte no fluxo, tipo, fim?)."""
    b = d[p]
    tipo = b & 3
    if (b & 0xFC) == 0:
        absoluto = _u32(d, p + 1)
        if absoluto == 0:
            return cursor, p + 5, tipo, True
        return absoluto + base, p + 5, tipo, False
    return cursor + (b & 0xFC), p + 1, tipo, False


def realocar(
    rel: bytes, base: int, exportados: dict[str, int], outros: dict[str, int] | None = None
) -> Modulo:
    """Realoca o módulo como se carregado em ``base`` (alinhado ao cabeçalho). Os endereços gravados são absolutos
    (base + deslocamento no arquivo). Importações sem resolução ficam em zero e na lista ``nao_resolvidos``."""
    if rel[:4] != MAGIA:
        raise LigacaoError("não é um módulo SNR2")
    d = bytearray(rel)
    alinhamento = _u32(d, 0x28)
    if alinhamento and base % alinhamento:
        raise LigacaoError(f"base {base:#x} não alinhada a {alinhamento:#x}")
    # cabeçalho: ponteiros que o ligador soma à base
    for off in (0x04, 0x0C, 0x14, 0x18, 0x1C, 0x20, 0x34, 0x38):
        if _u32(d, off):
            struct.pack_into("<I", d, off, _u32(d, off) + base)
    tab_secoes, n_secoes = _u32(d, 0x0C) - base, _u32(d, 0x10)
    secoes: list[Secao] = []
    nao_resolvidos: list[str] = []
    tabela = dict(outros or {})
    for i in range(n_secoes):
        e = tab_secoes + i * 12
        nome_off, endereco = _u32(d, e), _u32(d, e + 4)
        dica, tipo, flag = struct.unpack_from("<H", d, e + 8)[0], d[e + 10], d[e + 11]
        nome = _texto(d, nome_off) if nome_off < len(rel) else ""
        struct.pack_into("<I", d, e, nome_off + base)
        if tipo == 1:
            endereco = tabela.get(nome, exportados.get(nome, 0))
            if endereco == 0:
                nao_resolvidos.append(nome)
        elif tipo in (0, 2, 3):
            endereco += base
        struct.pack_into("<I", d, e + 4, endereco)
        secoes.append(Secao(i, nome, endereco, int(dica), tipo, flag))

    # fluxo comprimido
    fluxo = _u32(d, 0x34) - base if _u32(d, 0x34) else 0
    if fluxo:
        p, cursor = fluxo, 0
        while True:
            cursor, p, tipo, fim = _proximo_cursor(d, p, cursor, base)
            if fim:
                break
            pos = cursor - base
            if tipo == 1:  # metade alta: lê adiante a metade baixa correspondente, sem consumir o fluxo
                q, c2 = p, cursor
                while True:
                    c2, q, t2, fim2 = _proximo_cursor(d, q, c2, base)
                    if fim2:
                        raise LigacaoError("metade alta sem metade baixa")
                    if t2 == 0:
                        break
                baixa = struct.unpack_from("<h", d, c2 - base)[0]
                alta = struct.unpack_from("<H", d, pos)[0]
                _aplicar(d, pos, 5, base + (alta << 16) + baixa)
            elif tipo == 0:
                _aplicar(d, pos, 6, base + struct.unpack_from("<H", d, pos)[0])
            elif tipo == 2:
                _aplicar(d, pos, 4, base + ((_u32(d, pos) & 0x3FFFFFF) << 2))
            else:
                _aplicar(d, pos, 2, base + _u32(d, pos))

    # realocações simbólicas (seção + adendo)
    lista, n = _u32(d, 0x04) - base if _u32(d, 0x04) else 0, _u32(d, 0x08)
    for i in range(n):
        e = lista + i * 12
        pos = _u32(d, e) + base
        struct.pack_into("<I", d, e, pos)
        tipo_sec = _u32(d, e + 4)
        tipo, indice = tipo_sec & 0xFF, tipo_sec >> 8
        adendo = struct.unpack_from("<i", d, e + 8)[0]
        if indice >= len(secoes):
            raise LigacaoError(f"seção {indice} fora da tabela")
        if not _aplicar(d, pos - base, tipo, secoes[indice].endereco + adendo):
            raise LigacaoError(f"realocação simbólica {i} recusada (tipo {tipo:#x} em {pos:#x})")

    # tabela de ponteiros
    tab_ptr, n_ptr = _u32(d, 0x20) - base if _u32(d, 0x20) else 0, _u32(d, 0x24)
    for i in range(n_ptr):
        e = tab_ptr + i * 4
        if _u32(d, e):
            struct.pack_into("<I", d, e, _u32(d, e) + base)
    return Modulo(base, d, secoes, _u32(d, 0x18), nao_resolvidos)


# ---------------------------------------------------------------------------------------------------------------
# Lote para o mapa completo: todos os módulos .rel da ISO realocados para endereços virtuais, com os símbolos de
# cada um e as instruções para o roteiro do Ghidra (``lote:<arquivo>``).
# ---------------------------------------------------------------------------------------------------------------

BASE_VIRTUAL = 0x08000000  # fora da RAM do PlayStation 2; cada módulo ganha uma fatia de 8 MB
PASSO_VIRTUAL = 0x00800000
# 0x10000000..0x20000000 são registradores do console e o Ghidra já os mapeia: os módulos saltam essa faixa
FAIXA_RESERVADA = (0x10000000, 0x20000000)
SALTO_RESERVADO = 0x40000000 - FAIXA_RESERVADA[0]


def base_virtual(indice: int) -> int:
    base = BASE_VIRTUAL + indice * PASSO_VIRTUAL
    return base + SALTO_RESERVADO if base >= FAIXA_RESERVADA[0] else base


def mapear_modulos(
    iso: Path, csv_simbolos: Path, saida: Path, padrao: str = r"^(em|pl)[0-9a-f]{2}\.rel$"
) -> list[tuple[str, int, int]]:
    """Realoca cada módulo que casa com o padrão e grava, em ``saida``: ``<nome>.bin`` (bytes realocados),
    ``<nome>.csv`` (símbolos do módulo) e ``lote.txt`` (linhas ``bloco``, ``simbolos`` e ``codigo`` para o Ghidra).
    Devolve (nome, base, tamanho) por módulo."""
    import re

    from iaemps2.bancada.modulos import Afs

    afs = Afs(iso)
    exportados = carregar_simbolos_do_executavel(csv_simbolos)
    saida.mkdir(parents=True, exist_ok=True)
    feitos: list[tuple[str, int, int]] = []
    linhas: list[str] = []
    vistos: set[str] = set()
    for i, nome in enumerate(afs.nomes):
        if not re.match(padrao, nome) or nome in vistos:
            continue
        rel = afs.ler(i)
        if rel[:4] != MAGIA:
            continue
        vistos.add(nome)
        base = base_virtual(len(feitos))
        mod = realocar(rel, base, exportados)
        raiz = nome[:-4]
        (saida / f"{raiz}.bin").write_bytes(bytes(mod.dados))
        with (saida / f"{raiz}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["endereco", "nome", "decorado", "info"])
            for endereco, simbolo in mod.simbolos():
                w.writerow([f"{endereco:08x}", f"{raiz}__{simbolo}", simbolo, ""])
        linhas.append(f"bloco {raiz} {saida / (raiz + '.bin')} {base:08x}")
        linhas.append(f"simbolos {saida / (raiz + '.csv')}")
        linhas.append(f"codigo {base:08x} {base + len(rel):08x}")
        feitos.append((nome, base, len(rel)))
        if mod.nao_resolvidos:
            linhas.append(
                f"# {nome}: {len(mod.nao_resolvidos)} importações sem resolução: {mod.nao_resolvidos[:5]}"
            )
    (saida / "lote.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    with (saida / "modulos.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["modulo", "base", "tamanho"])
        w.writerows((n, f"{b:08x}", t) for n, b, t in feitos)
    return feitos


def main(argv: list[str] | None = None) -> int:
    import argparse

    from iaemps2.bancada.modulos import ISO_PADRAO

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("saida", type=Path)
    parser.add_argument("--iso", type=Path, default=ISO_PADRAO)
    parser.add_argument("--simbolos", type=Path, default=Path("perfis/memoria/SLUS-21134.simbolos.csv"))
    parser.add_argument("--padrao", default=r"^(em|pl)[0-9a-f]{2}\.rel$")
    args = parser.parse_args(argv)
    feitos = mapear_modulos(args.iso, args.simbolos, args.saida, args.padrao)
    for nome, base, tamanho in feitos:
        print(f"{nome:12s} {base:#010x} {tamanho:8d} bytes")
    print(f"{len(feitos)} módulos; lote em {args.saida / 'lote.txt'}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
