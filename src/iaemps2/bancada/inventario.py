"""Inventário do jogo de abertura (SLUS-21134): listar a maleta e dar um item pelo canal.

O que o código do jogo diz (lido em 28/10, card S8-01): o gerenciador global de itens (``cItemMgr``) guarda um
vetor de 384 itens de 14 bytes. A maleta é um tabuleiro de peças (``pzlPlayer``/``pzlBoard``/``pzlPiece``)
remontado a cada abertura a partir do vetor: só vira peça o item cujo id está na tabela de dados de peça
(largura, altura e centro); a posição gravada no item (+0xA, +0xB) é o **centro** da peça em meias-células, a
orientação fica em +0xC e +0xD diz se a peça está na maleta. Uma peça cujo canto cai fora do tabuleiro ou sobre
outra peça é descartada, e o item não aparece. Para dar um item, basta gravar o slot como ``cItemMgr::construct``
faria e escolher a primeira célula livre, na mesma ordem que o jogo usa ao pegar um item (linha por linha, coluna
por coluna, sem girar).

Comandos:
  listar [--maleta LxA]                  slots ocupados, posição de cada peça e a grade de ocupação.
  dar <id> [--quantidade N] [--maleta LxA]   grava o item num slot livre, na primeira célula onde cabe.

Suposição declarada: maleta de 10x6 (o tamanho inicial); passe ``--maleta 11x7`` etc. se o jogador comprou uma
maior (o jogo usa 10x6, 11x7, 12x8 e 15x8). Ids: 0x23 pistola, 0x04 balas de pistola, 0x05 erva verde,
0x35 lança-foguetes.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

GERENCIADOR = 0x003CE148
TABELA_PECAS = 0x00326DE8  # ITEM_PIECE_INFO: entradas de 0x58 bytes até o id 0xFFFF
TABELA_ARMAS = 0x003A99C0  # 43 entradas de 0x16 bytes (DAT_002f0200)
ARMAS = 43
TAMANHO_ITEM = 14
TAMANHO_PECA = 0x58
MALETA_INICIAL = (10, 6)
LEITURAS_POR_PEDIDO = 2000


@dataclass(frozen=True)
class Peca:
    id: int
    largura: int
    altura: int
    centro_x: float
    centro_y: float


@dataclass
class Item:
    slot: int
    id: int
    quantidade: int
    flags: int
    dono: int
    niveis: int
    carga_x8: int
    x2: int  # centro da peça em meias-células
    y2: int
    orientacao: int
    na_maleta: int

    @classmethod
    def dos_bytes(cls, slot: int, dados: bytes) -> Item:
        id_, quantidade, flags, dono, niveis, carga, x2, y2, orientacao, na_maleta = struct.unpack(
            "<HHBBHHBBBB", dados[:TAMANHO_ITEM]
        )
        return cls(slot, id_, quantidade, flags, dono, niveis, carga, x2, y2, orientacao, na_maleta)

    def para_bytes(self) -> bytes:
        return struct.pack(
            "<HHBBHHBBBB",
            self.id,
            self.quantidade,
            self.flags,
            self.dono,
            self.niveis,
            self.carga_x8,
            self.x2,
            self.y2,
            self.orientacao,
            self.na_maleta,
        )

    @property
    def ocupado(self) -> bool:
        return bool(self.flags & 1)

    def canto(self, peca: Peca) -> tuple[int, int]:
        """Célula do canto superior esquerdo da peça (o jogo guarda o centro em meias-células)."""
        return int(self.x2 / 2 - peca.centro_x), int(self.y2 / 2 - peca.centro_y)


def pecas(dados: bytes) -> dict[int, Peca]:
    """Tabela de dados de peça: id u16, largura u8 (+4), altura u8 (+5), centro (+8, +0xC), grade de '1' (+0x10)."""
    saida = {}
    e = 0
    while e + TAMANHO_PECA <= len(dados):
        id_ = struct.unpack_from("<H", dados, e)[0]
        if id_ == 0xFFFF:
            break
        largura, altura = dados[e + 4], dados[e + 5]
        cx, cy = struct.unpack_from("<ff", dados, e + 8)
        saida[id_] = Peca(id_, largura, altura, cx, cy)
        e += TAMANHO_PECA
    return saida


def armas(dados: bytes) -> dict[int, tuple[int, int]]:
    """Tabela de armas: id -> (id do item de munição ou 0xFF, capacidade do pente no nível 1)."""
    saida = {}
    for i in range(ARMAS):
        e = i * 0x16
        id_ = struct.unpack_from("<H", dados, e)[0]
        if id_:
            saida[id_] = (dados[e + 6], int(struct.unpack_from("<H", dados, e + 8)[0]))
    return saida


def ocupacao(itens: list[Item], tabela: dict[int, Peca], largura: int, altura: int) -> list[list[bool]]:
    grade = [[False] * largura for _ in range(altura)]
    for item in itens:
        peca = tabela.get(item.id)
        if not item.ocupado or not item.na_maleta or peca is None:
            continue
        x0, y0 = item.canto(peca)
        for y in range(y0, y0 + peca.altura):
            for x in range(x0, x0 + peca.largura):
                if 0 <= x < largura and 0 <= y < altura:
                    grade[y][x] = True
    return grade


def encaixar(grade: list[list[bool]], largura: int, altura: int) -> tuple[int, int] | None:
    """Primeira célula onde uma peça largura x altura cabe sem girar: linha por linha, coluna por coluna
    (a mesma ordem da função do jogo que decide se um item pego cabe)."""
    linhas, colunas = len(grade), len(grade[0]) if grade else 0
    for y in range(linhas - altura + 1):
        for x in range(colunas - largura + 1):
            if not any(grade[y + j][x + i] for j in range(altura) for i in range(largura)):
                return x, y
    return None


def montar_item(
    slot: int,
    id_: int,
    quantidade: int,
    dono: int,
    peca: Peca,
    arma: tuple[int, int] | None,
    canto: tuple[int, int],
) -> Item:
    """O que cItemMgr::construct grava para armas (tipo 1) e descartáveis (tipo 3), mais a posição: armas têm
    quantidade 1 e carga do nível 1 em +0x8 (<< 3). Os tipos 9 e 10 recebem outros valores em +0x6/+0x8 no jogo e
    não são tratados aqui."""
    carga = arma[1] if arma else 0
    x2 = int((canto[0] + peca.centro_x) * 2)
    y2 = int((canto[1] + peca.centro_y) * 2)
    return Item(slot, id_, 1 if arma else quantidade, 1, dono, 0, carga << 3, x2, y2, 0, 1)


def ler_bloco(c: Cliente, inicio: int, tamanho: int) -> bytes:
    """Lê um bloco em leituras de 8 bytes agrupadas por pedido."""
    partes = []
    fim = inicio + tamanho
    for lote in range(inicio, fim, LEITURAS_POR_PEDIDO * 8):
        comandos = [
            p.comando(p.Codigo.READ64, struct.pack("<I", e))
            for e in range(lote, min(fim, lote + LEITURAS_POR_PEDIDO * 8), 8)
        ]
        partes.append(c.pedir(*comandos))
    return b"".join(partes)[:tamanho]


def escrever_bloco(c: Cliente, endereco: int, dados: bytes) -> None:
    c.pedir(*(p.comando(p.Codigo.WRITE8, struct.pack("<IB", endereco + i, b)) for i, b in enumerate(dados)))


@dataclass
class Inventario:
    vetor: int
    slots: int
    dono: int
    itens: list[Item]
    pecas: dict[int, Peca]
    armas: dict[int, tuple[int, int]]


def ler_inventario(c: Cliente) -> Inventario:
    mgr = ler_bloco(c, GERENCIADOR, 0x20)
    vetor, slots = struct.unpack_from("<II", mgr, 0x14)[0], struct.unpack_from("<I", mgr, 0x1C)[0]
    dados = ler_bloco(c, vetor, slots * TAMANHO_ITEM)
    itens = [Item.dos_bytes(s, dados[s * TAMANHO_ITEM : (s + 1) * TAMANHO_ITEM]) for s in range(slots)]
    return Inventario(
        vetor,
        slots,
        mgr[0x13],
        itens,
        pecas(ler_bloco(c, TABELA_PECAS, 0x1800)),
        armas(ler_bloco(c, TABELA_ARMAS, ARMAS * 0x16)),
    )


def dar_item(c: Cliente, id_: int, quantidade: int, maleta: tuple[int, int] = MALETA_INICIAL) -> Item:
    inv = ler_inventario(c)
    peca = inv.pecas.get(id_)
    if peca is None:
        raise ValueError(f"o id {id_:#x} não tem dados de peça: não iria para a maleta")
    canto = encaixar(ocupacao(inv.itens, inv.pecas, *maleta), peca.largura, peca.altura)
    if canto is None:
        raise ValueError(
            f"não há lugar livre de {peca.largura}x{peca.altura} na maleta de {maleta[0]}x{maleta[1]} sem girar"
        )
    livre = next((i for i in inv.itens if not i.ocupado), None)
    if livre is None:
        raise ValueError("vetor de itens cheio")
    item = montar_item(livre.slot, id_, quantidade, inv.dono, peca, inv.armas.get(id_), canto)
    endereco = inv.vetor + item.slot * TAMANHO_ITEM
    escrever_bloco(c, endereco, item.para_bytes())
    c.pedir(
        p.comando(p.Codigo.WRITE32, struct.pack("<II", GERENCIADOR + 0x18, endereco))
    )  # último acrescentado
    return item


def _cliente() -> Cliente:
    c = Cliente(porta=28011, tempo_limite_s=20.0)
    c.conectar()
    return c


def _maleta(texto: str) -> tuple[int, int]:
    largura, altura = texto.lower().split("x")
    return int(largura), int(altura)


def _descrever(item: Item, inv: Inventario) -> str:
    peca = inv.pecas.get(item.id)
    onde = (
        f"maleta canto {item.canto(peca)} {peca.largura}x{peca.altura}"
        if peca and item.na_maleta
        else "fora da maleta"
    )
    arma = inv.armas.get(item.id)
    carga = f" pente {item.carga_x8 >> 3}" if arma else ""
    return f"slot {item.slot:3d} id {item.id:#06x} qtd {item.quantidade:3d}{carga} {onde}"


def listar(args: argparse.Namespace) -> int:
    c = _cliente()
    inv = ler_inventario(c)
    c.fechar()
    ocupados = [i for i in inv.itens if i.ocupado]
    print(f"vetor em {inv.vetor:08x}, {inv.slots} slots, {len(ocupados)} ocupados, dono {inv.dono}")
    for item in ocupados:
        print("  ", _descrever(item, inv))
    for linha in ocupacao(ocupados, inv.pecas, *args.maleta):
        print("   ", "".join("#" if x else "." for x in linha))
    return 0


def dar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        item = dar_item(c, args.id, args.quantidade, args.maleta)
        inv = ler_inventario(c)
    finally:
        c.fechar()
    print("gravado:", _descrever(item, inv))
    print("abra a maleta para ver; o jogo monta o tabuleiro ao abrir")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("listar")
    s.add_argument("--maleta", type=_maleta, default=MALETA_INICIAL)
    s.set_defaults(func=listar)
    s = sub.add_parser("dar")
    s.add_argument("id", type=lambda x: int(x, 0))
    s.add_argument("--quantidade", type=int, default=1)
    s.add_argument("--maleta", type=_maleta, default=MALETA_INICIAL)
    s.set_defaults(func=dar)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
