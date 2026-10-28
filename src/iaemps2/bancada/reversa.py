"""Ferramentas de engenharia reversa do código do jogo, a partir de uma foto da memória do emulador.

Trabalham sobre a foto de 32 MB gravada pela bancada (``prova_memoria foto`` ou ``varrer_memoria.fotografar``),
sem o emulador aberto. Complementam o projeto do Ghidra (``reversa/ghidra/``), que faz a análise e a decompilação.

Comandos:
  simbolos <foto> [--saida csv]   extrai a tabela de símbolos que o executável carrega (nome C++ e endereço).
  codigo <foto>                   lista as faixas da memória que parecem código (densidade de prólogos de função),
                                  para marcar como executáveis no Ghidra.
  cadeia <foto> <endereco>        início da função que contém o endereço e quem a chama por ``jal``.
  desmontar <foto> <inicio> <fim> desmonta a faixa (precisa do capstone).
  elf <iso> <pasta>               extrai o executável e o SYSTEM.CNF da ISO (precisa do pycdlib).

Os endereços são os do jogo (a foto começa em 0). Formato da tabela de símbolos (vale para o SLUS-21134 e, pelo
que se sabe, para outros jogos da mesma geração de ferramentas): entradas de 12 bytes (info, ponteiro para o nome,
endereço), com os nomes numa seção de texto do executável; a tabela é achada procurando entradas válidas em volta
de um ponteiro para um nome decorado.
"""

from __future__ import annotations

import argparse
import csv
import re
import struct
import sys
from collections.abc import Iterator
from pathlib import Path

MEMORIA_EE = 32 * 1024 * 1024
CODIGO_INICIO = 0x00100000
PROLOGO_MASCARA, PROLOGO_VALOR = 0xFFFF8000, 0x27BD8000  # addiu sp, sp, -N
JR_RA = 0x03E00008
DECORADO = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*__[0-9A-Za-z_]+")


def ler32(mem: bytes, endereco: int) -> int:
    return int(struct.unpack_from("<I", mem, endereco)[0])


def nome_legivel(decorado: str) -> str:
    """Desfaz a decoração do GNU C++ antigo: ``metodo__7cClasse...`` vira ``cClasse::metodo``; ``__F`` é função livre."""
    casado = re.match(r"^(.*?)__(?:F|(\d+)([A-Za-z_][A-Za-z0-9_]*))", decorado)
    if not casado:
        return decorado
    metodo, tamanho, resto = casado.group(1), casado.group(2), casado.group(3)
    if tamanho:
        classe = resto[: int(tamanho)]
        return f"{classe}::{metodo or classe}"
    return metodo


def _texto_em(mem: bytes, endereco: int) -> str:
    fim = mem.index(b"\0", endereco)
    return mem[endereco:fim].decode("latin-1")


def simbolos(mem: bytes) -> list[tuple[int, str, str, int]]:
    """Devolve (endereço, nome legível, nome decorado, info) para cada entrada da tabela de símbolos do jogo."""
    nomes = {m.start() for m in DECORADO.finditer(mem, CODIGO_INICIO, 0x00400000)}
    if not nomes:
        return []
    faixa = (min(nomes), max(nomes) + 1)

    def valida(entrada: int) -> bool:
        if entrada < 0 or entrada + 12 > len(mem):
            return False
        ptr_nome, endereco = ler32(mem, entrada + 4), ler32(mem, entrada + 8)
        return faixa[0] <= ptr_nome < faixa[1] and CODIGO_INICIO <= endereco < MEMORIA_EE

    # acha uma entrada pela referência a um nome e expande para os dois lados
    semente = next(
        (e for n in sorted(nomes) for e in _referencias(mem, n, CODIGO_INICIO, 0x00400000) if valida(e - 4)),
        None,
    )
    if semente is None:
        return []
    inicio = fim = semente - 4
    while valida(inicio - 12):
        inicio -= 12
    while valida(fim):
        fim += 12
    saida = []
    for e in range(inicio, fim, 12):
        decorado = _texto_em(mem, ler32(mem, e + 4))
        saida.append((ler32(mem, e + 8), nome_legivel(decorado), decorado, ler32(mem, e)))
    return saida


def _referencias(mem: bytes, valor: int, inicio: int, fim: int) -> Iterator[int]:
    alvo = struct.pack("<I", valor)
    pos = mem.find(alvo, inicio, fim)
    while pos != -1:
        if pos % 4 == 0:
            yield pos
        pos = mem.find(alvo, pos + 1, fim)


def faixas_de_codigo(mem: bytes, bloco: int = 0x10000, minimo: int = 20) -> list[tuple[int, int, int, int]]:
    """Blocos com pelo menos ``minimo`` prólogos e ``minimo`` retornos: (início, fim, prólogos, retornos)."""
    saida = []
    for inicio in range(CODIGO_INICIO, len(mem), bloco):
        prologos = retornos = 0
        for e in range(inicio, min(inicio + bloco, len(mem) - 4), 4):
            palavra = ler32(mem, e)
            if palavra & PROLOGO_MASCARA == PROLOGO_VALOR:
                prologos += 1
            elif palavra == JR_RA:
                retornos += 1
        if prologos >= minimo and retornos >= minimo:
            saida.append((inicio, inicio + bloco, prologos, retornos))
    return saida


def inicio_da_funcao(mem: bytes, pc: int) -> int:
    """Anda para trás até o prólogo; se cruzar o ``jr ra`` da função anterior, a função não tem prólogo."""
    e = pc
    while e > CODIGO_INICIO:
        palavra = ler32(mem, e)
        if palavra & PROLOGO_MASCARA == PROLOGO_VALOR:
            return e
        if palavra == JR_RA:
            return e + 8
        e -= 4
    return e


def fim_da_funcao(mem: bytes, inicio: int) -> int:
    e = inicio
    while e < len(mem) - 4 and ler32(mem, e) != JR_RA:
        e += 4
    return e + 8


def chamadores(mem: bytes, inicio: int) -> list[int]:
    """Endereços de ``jal`` para a função (o alvo do ``jal`` fica nos 26 bits baixos, vezes 4)."""
    return [
        e
        for e in range(CODIGO_INICIO, len(mem) - 4, 4)
        if (ler32(mem, e) >> 26) == 3 and ((ler32(mem, e) & 0x3FFFFFF) << 2) == inicio
    ]


def desmontar(mem: bytes, inicio: int, fim: int) -> Iterator[str]:
    from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS64, Cs

    motor = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)
    motor.skipdata = True
    for instrucao in motor.disasm(bytes(mem[inicio:fim]), inicio):
        yield f"{instrucao.address:08x}  {ler32(mem, instrucao.address):08x}  {instrucao.mnemonic:9s} {instrucao.op_str}"


def extrair_elf(iso: Path, pasta: Path) -> list[Path]:
    import pycdlib

    pasta.mkdir(parents=True, exist_ok=True)
    disco = pycdlib.PyCdlib()
    disco.open(str(iso))
    gravados = []
    try:
        cnf = pasta / "SYSTEM.CNF"
        disco.get_file_from_iso(str(cnf), iso_path="/SYSTEM.CNF;1")
        gravados.append(cnf)
        boot = re.search(r"BOOT2\s*=\s*cdrom0:\\([^;]+)", cnf.read_text(encoding="latin-1"))
        if boot:
            exe = pasta / boot.group(1)
            disco.get_file_from_iso(str(exe), iso_path=f"/{boot.group(1)};1")
            gravados.append(exe)
    finally:
        disco.close()
    return gravados


def _endereco(texto: str) -> int:
    return int(texto, 16)  # aceita com ou sem "0x"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("simbolos")
    s.add_argument("foto", type=Path)
    s.add_argument("--saida", type=Path, default=None)
    s = sub.add_parser("codigo")
    s.add_argument("foto", type=Path)
    s = sub.add_parser("cadeia")
    s.add_argument("foto", type=Path)
    s.add_argument("endereco", type=_endereco)
    s = sub.add_parser("desmontar")
    s.add_argument("foto", type=Path)
    s.add_argument("inicio", type=_endereco)
    s.add_argument("fim", type=_endereco)
    s = sub.add_parser("elf")
    s.add_argument("iso", type=Path)
    s.add_argument("pasta", type=Path)
    args = parser.parse_args(argv)

    if args.comando == "elf":
        for arquivo in extrair_elf(args.iso, args.pasta):
            print(arquivo, arquivo.stat().st_size, "bytes")
        return 0

    mem = args.foto.read_bytes()
    if args.comando == "simbolos":
        linhas = simbolos(mem)
        if args.saida:
            with args.saida.open("w", newline="", encoding="utf-8") as f:
                escritor = csv.writer(f)
                escritor.writerow(["endereco", "nome", "decorado", "info"])
                escritor.writerows((f"{a:08x}", n, d, f"{i:08x}") for a, n, d, i in linhas)
        else:
            for a, n, _d, _i in linhas:
                print(f"{a:08x} {n}")
        print(f"{len(linhas)} símbolos", file=sys.stderr)
        return 0 if linhas else 1
    if args.comando == "codigo":
        for inicio, fim, prologos, retornos in faixas_de_codigo(mem):
            print(f"{inicio:08x}..{fim:08x} prólogos {prologos:4d} retornos {retornos:4d}")
        return 0
    if args.comando == "cadeia":
        inicio = inicio_da_funcao(mem, args.endereco)
        fim = fim_da_funcao(mem, inicio)
        print(f"função de {args.endereco:08x}: {inicio:08x}..{fim:08x} ({(fim - inicio) // 4} instruções)")
        print("chamadores:", [f"{e:08x}" for e in chamadores(mem, inicio)])
        return 0
    for linha in desmontar(mem, args.inicio, args.fim):
        print(linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
