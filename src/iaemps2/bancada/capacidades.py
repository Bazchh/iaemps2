"""Capacidades provadas do jogo de abertura que não tinham ferramenta própria (card S9-03): consultas pela chamada
remota, vida e teleporte por escrita de memória, esconder cenário pela camada de cena.

Cada comando é uma linha do catálogo (bloco ``capacidades`` do perfil, docs/Capacidades-SLUS-21134.md): o que ele
faz, as pré-condições e a volta estão lá. Nada aqui dorme pelo escalonador do jogo.

Comandos:
  lista-viva <i>                 EmListIsAlive(i): a entrada i da lista da sala está viva?
  contar-item <id>               cItemMgr::num(id): quantos do item no inventário.
  vida <valor>                   escreve a vida do jogador (0..máxima) e relê.
  teleporte <x> <y> <z> [--relativo]
                                 escreve a posição do jogador (mm) na entidade, na posição anterior e nas partes do
                                 modelo; relê. Só para pontos do chão (um ponto dentro de objeto é rejeitado pelo jogo).
  materiais [n]                  os n maiores pedaços desenhados no último quadro (hash da textura, área).
  esconder <hash> [--segundos S] regra de cena que esconde o material; devolve o id da regra.
  mostrar [id]                   remove a regra (0 = todas).
"""

from __future__ import annotations

import argparse
import struct
import sys
import time

from iaemps2.bancada import personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import REGRA_ESCONDER, Cliente

EM_LIST_IS_ALIVE = 0x001BDB38
CITEMMGR_NUM = 0x0011F0E0
ITEM_MGR = 0x003CE148
VIDA = pz.BLOCO_G + 0x7ED6
VIDA_MAXIMA = pz.BLOCO_G + 0x7ED8
POS, POS_OLD, PARTES = 0xC0, 0x130, 0x110
PARTE_MUNDO = (0x80, 0x90, 0xA0)


def _cliente() -> Cliente:
    c = Cliente(porta=p.PORTA_PADRAO, tempo_limite_s=20.0)
    c.conectar()
    return c


def _u16(c: Cliente, endereco: int) -> int:
    return int(
        struct.unpack_from("<H", c.pedir(p.comando(p.Codigo.READ16, struct.pack("<I", endereco))), 0)[0]
    )


def _u32(c: Cliente, endereco: int) -> int:
    return int(
        struct.unpack_from("<I", c.pedir(p.comando(p.Codigo.READ32, struct.pack("<I", endereco))), 0)[0]
    )


def lista_viva(c: Cliente, indice: int) -> int:
    r = c.chamar(EM_LIST_IS_ALIVE, (indice,), tempo_limite_ms=2000)
    if not r.ok:
        raise RuntimeError(f"chamada {r.estado}")
    return r.v0


def contar_item(c: Cliente, id_item: int) -> int:
    r = c.chamar(CITEMMGR_NUM, (ITEM_MGR, id_item), tempo_limite_ms=2000)
    if not r.ok:
        raise RuntimeError(f"chamada {r.estado}")
    return r.v0


def escrever_vida(c: Cliente, valor: int) -> tuple[int, int, int]:
    """Devolve (antes, máxima, depois). O valor é limitado a 0..máxima."""
    antes, maxima = _u16(c, VIDA), _u16(c, VIDA_MAXIMA)
    novo = max(0, min(valor, maxima))
    c.pedir(p.comando(p.Codigo.WRITE16, struct.pack("<IH", VIDA, novo)))
    return antes, maxima, _u16(c, VIDA)


def teleportar(c: Cliente, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Escreve a posição na entidade do jogador (+0xC0 e +0x130) e em cada parte do modelo (+0x80, +0x90, +0xA0),
    três vezes com um quadro de intervalo (a receita do andarilho de 30/10); devolve a posição relida."""
    vetor, _, _ = pz.vetor_personagens(c)
    for _ in range(3):
        cmds = [
            p.comando(p.Codigo.WRITE32, struct.pack("<If", vetor + off + 4 * k, v))
            for off in (POS, POS_OLD)
            for k, v in enumerate((x, y, z))
        ]
        parte = _u32(c, vetor + PARTES)
        for _ in range(40):
            if not (0x00100000 < parte < 0x02000000):
                break
            for off in PARTE_MUNDO:
                cmds += [
                    p.comando(p.Codigo.WRITE32, struct.pack("<If", parte + off + 4 * k, v))
                    for k, v in enumerate((x, y, z))
                ]
            parte = _u32(c, parte + PARTES)
        c.pedir(*cmds)
        time.sleep(0.02)
    time.sleep(0.25)
    return pz.ler_vec3(c, vetor + POS)


def cmd_lista_viva(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        print(f"entrada {args.indice}: {'viva' if lista_viva(c, args.indice) else 'não viva'}")
    finally:
        c.fechar()
    return 0


def cmd_contar_item(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        print(f"item {args.id:#06x}: {contar_item(c, args.id)}")
    finally:
        c.fechar()
    return 0


def cmd_vida(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        antes, maxima, depois = escrever_vida(c, args.valor)
    finally:
        c.fechar()
    print(f"vida: {antes} -> {depois} (máxima {maxima})")
    return 0 if depois == max(0, min(args.valor, maxima)) else 1


def cmd_teleporte(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        vetor, _, _ = pz.vetor_personagens(c)
        origem = pz.ler_vec3(c, vetor + POS)
        alvo = (args.x, args.y, args.z)
        if args.relativo:
            alvo = (origem[0] + args.x, origem[1] + args.y, origem[2] + args.z)
        depois = teleportar(c, *alvo)
    finally:
        c.fechar()
    dist = sum((a - b) ** 2 for a, b in zip(depois, alvo, strict=True)) ** 0.5
    print(
        f"de ({origem[0]:.0f}, {origem[1]:.0f}, {origem[2]:.0f}) para ({depois[0]:.0f}, {depois[1]:.0f}, {depois[2]:.0f}); a {dist:.0f} mm do pedido"
    )
    return 0 if dist < 300 else 1


def cmd_materiais(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        quadro, lista = c.cena_lista()
    finally:
        c.fechar()
    por_textura: dict[int, int] = {}
    for a in lista:
        if a.qualifica:
            por_textura[a.hash_textura] = por_textura.get(a.hash_textura, 0) + a.area
    print(f"quadro {quadro}: {len(lista)} desenhos, {len(por_textura)} materiais de mundo")
    for h, area in sorted(por_textura.items(), key=lambda x: -x[1])[: args.n]:
        print(f"  {h:016x}  área {area}")
    return 0


def cmd_esconder(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        id_regra = c.cena_regra(REGRA_ESCONDER, hash_textura=args.hash, duracao_ms=int(args.segundos * 1000))
        time.sleep(0.5)
        est = c.cena_estatisticas(id_regra)
    finally:
        c.fechar()
    print(
        f"regra {id_regra}: material {args.hash:016x} escondido por {args.segundos:g} s (0 = até mostrar); "
        f"aplicada em {est.quadros_aplicada} de {est.quadros_total} quadros no primeiro meio segundo"
    )
    return 0 if est.quadros_aplicada > 0 else 1


def cmd_mostrar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        c.cena_limpar(args.id)
    finally:
        c.fechar()
    print("regra removida" if args.id else "todas as regras removidas")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("lista-viva")
    s.add_argument("indice", type=lambda x: int(x, 0))
    s.set_defaults(func=cmd_lista_viva)
    s = sub.add_parser("contar-item")
    s.add_argument("id", type=lambda x: int(x, 0))
    s.set_defaults(func=cmd_contar_item)
    s = sub.add_parser("vida")
    s.add_argument("valor", type=int)
    s.set_defaults(func=cmd_vida)
    s = sub.add_parser("teleporte")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s.add_argument("z", type=float)
    s.add_argument("--relativo", action="store_true", help="x, y, z somados à posição atual")
    s.set_defaults(func=cmd_teleporte)
    s = sub.add_parser("materiais")
    s.add_argument("n", type=int, nargs="?", default=10)
    s.set_defaults(func=cmd_materiais)
    s = sub.add_parser("esconder")
    s.add_argument("hash", type=lambda x: int(x, 16))
    s.add_argument("--segundos", type=float, default=20.0)
    s.set_defaults(func=cmd_esconder)
    s = sub.add_parser("mostrar")
    s.add_argument("id", type=int, nargs="?", default=0)
    s.set_defaults(func=cmd_mostrar)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
