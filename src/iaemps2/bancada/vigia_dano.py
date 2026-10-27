"""Prova medida S8-01: vigia de escrita no emulador próprio, para achar a vida do inimigo e a munição.

O vigia grava, por instrução do jogo, cada acesso a uma faixa de memória, sem pausar. A caça é por janelas:
uma janela base (ninguém atira) e uma janela do tiro; as instruções que só aparecem na janela do tiro são as
candidatas, e os registradores gravados no primeiro acesso dão a base da estrutura.

Comandos:
  prova                      vigia a vida do jogador (0x42DA76) por alguns segundos: o inimigo acerta o jogador
                             e a leitura tem de mostrar uma instrução cujo último valor é a vida lida pelo canal.
  janela <rotulo>            vigia a faixa por --segundos e grava a tabela em <pasta>/<rotulo>.json.
  comparar <base> <tiro>     instruções presentes em <tiro> e ausentes em <base>, com endereço, valor e base.
  ver <rotulo>               lista a tabela gravada, por contagem.

Uso: python -m iaemps2.bancada.vigia_dano janela base --inicio 0x01794230 --fim 0x01795100 --segundos 3
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import VIGIA_ESCRITA, AcessoVigiado, Cliente

PASTA_PADRAO = Path.home() / "IAEmPS2" / "medicoes" / "s8-01"
VIDA_JOGADOR = 0x0042DA76
NOMES_REG = [
    *("zero", "at", "v0", "v1", "a0", "a1", "a2", "a3"),
    *("t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7"),
    *("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"),
    *("t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"),
]


def _cliente() -> Cliente:
    c = Cliente(porta=28011, tempo_limite_s=20.0)
    c.conectar()
    return c


def _ler16(c: Cliente, endereco: int) -> int:
    corpo = c.pedir(p.comando(p.Codigo.READ16, struct.pack("<I", endereco)))
    return int(struct.unpack_from("<H", corpo, 0)[0])


def _janela(c: Cliente, inicio: int, fim: int, segundos: float) -> tuple[list[AcessoVigiado], dict[str, int]]:
    """Pausa, arma o vigia, retoma, espera, lê com zerar e desarma. Devolve a tabela e o resumo."""
    c.pausar(True)
    time.sleep(0.3)
    c.vigia_definir(inicio, fim, VIGIA_ESCRITA, duracao_ms=int(segundos * 1000) + 5000)
    time.sleep(0.3)
    c.pausar(False)
    t0 = time.monotonic()
    time.sleep(segundos)
    estado, itens = c.vigia_ler(zerar=True)
    c.vigia_limpar()
    duracao = time.monotonic() - t0
    resumo = {
        "acessos_total": estado.acessos_total,
        "descartados": estado.descartados,
        "instrucoes": estado.instrucoes,
        "duracao_ms": int(duracao * 1000),
    }
    return itens, resumo


def _dicionario(a: AcessoVigiado) -> dict[str, Any]:
    return {
        "pc": a.pc,
        "op": a.op,
        "primeiro_endereco": a.primeiro_endereco,
        "ultimo_endereco": a.ultimo_endereco,
        "contagem": a.contagem,
        "bits": a.bits,
        "escrita": a.escrita,
        "ultimo_valor": a.ultimo_valor,
        "registradores": list(a.registradores),
    }


def _linha(a: dict[str, Any]) -> str:
    op = int(a["op"])
    base = (op >> 21) & 0x1F
    regs = a["registradores"]
    acao = "escreve" if a["escrita"] else "lê"
    return (
        f"pc {int(a['pc']):08x} {acao} {int(a['bits']):>3} bits x{int(a['contagem']):<5} "
        f"end {int(a['primeiro_endereco']):08x}..{int(a['ultimo_endereco']):08x} "
        f"valor {int(a['ultimo_valor']):x} base {NOMES_REG[base]}={int(regs[base]):08x}"
    )


def prova(args: argparse.Namespace) -> int:
    c = _cliente()
    antes = _ler16(c, VIDA_JOGADOR)
    print(
        f"vida do jogador antes: {antes}; vigiando escritas em {VIDA_JOGADOR:08x} por {args.segundos:.0f} s "
        "(deixe o inimigo acertar)"
    )
    itens, resumo = _janela(c, VIDA_JOGADOR, VIDA_JOGADOR + 2, args.segundos)
    depois = _ler16(c, VIDA_JOGADOR)
    c.fechar()
    print(f"vida depois: {depois}; {resumo}")
    for a in sorted(itens, key=lambda x: -x.contagem):
        print("  ", _linha(_dicionario(a)))
    bate = [a for a in itens if a.escrita and (a.ultimo_valor & 0xFFFF) == depois]
    print("instruções cujo último valor é a vida lida:", [f"{a.pc:08x}" for a in bate])
    return 0 if bate else 1


def janela(args: argparse.Namespace) -> int:
    args.pasta.mkdir(parents=True, exist_ok=True)
    c = _cliente()
    print(f"vigiando {args.inicio:08x}..{args.fim:08x} por {args.segundos:.0f} s ({args.rotulo})")
    itens, resumo = _janela(c, args.inicio, args.fim, args.segundos)
    c.fechar()
    dados = {
        "inicio": args.inicio,
        "fim": args.fim,
        "resumo": resumo,
        "acessos": [_dicionario(a) for a in itens],
    }
    (args.pasta / f"{args.rotulo}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    print(f"{args.rotulo}: {resumo}")
    return 0


def _carregar(pasta: Path, rotulo: str) -> dict[str, Any]:
    dados = json.loads((pasta / f"{rotulo}.json").read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    return dados


def ver(args: argparse.Namespace) -> int:
    dados = _carregar(args.pasta, args.rotulo)
    print(dados["resumo"])
    for a in sorted(dados["acessos"], key=lambda x: -int(x["contagem"])):
        print("  ", _linha(a))
    return 0


def comparar(args: argparse.Namespace) -> int:
    base = _carregar(args.pasta, args.base)
    tiro = _carregar(args.pasta, args.tiro)
    pcs_base = {int(a["pc"]) for a in base["acessos"]}
    novos = [a for a in tiro["acessos"] if int(a["pc"]) not in pcs_base]
    print(f"base: {len(pcs_base)} instruções; tiro: {len(tiro['acessos'])}; só no tiro: {len(novos)}")
    for a in sorted(novos, key=lambda x: int(x["primeiro_endereco"])):
        print("  ", _linha(a))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("prova")
    s.add_argument("--segundos", type=float, default=8.0)
    s.set_defaults(func=prova)
    s = sub.add_parser("janela")
    s.add_argument("rotulo")
    s.add_argument("--inicio", type=lambda x: int(x, 0), default=0x01794230)
    s.add_argument("--fim", type=lambda x: int(x, 0), default=0x01794230 + 0xED0)
    s.add_argument("--segundos", type=float, default=3.0)
    s.set_defaults(func=janela)
    s = sub.add_parser("ver")
    s.add_argument("rotulo")
    s.set_defaults(func=ver)
    s = sub.add_parser("comparar")
    s.add_argument("base")
    s.add_argument("tiro")
    s.set_defaults(func=comparar)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
