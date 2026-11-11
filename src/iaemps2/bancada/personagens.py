"""Personagens do jogo de abertura (SLUS-21134): listar o vetor e criar um na frente do jogador pela chamada remota.

O que o código do jogo diz (lido em 28 e 29/10, card S8-02): o gerenciador global ``EmMgr`` (0x004203B0) aponta
para o vetor de 60 personagens de 0xED0 bytes (0x01789F40). Cada sala tem suas entradas numa lista global de 32
bytes (``EM_LIST``, 0x0042DEE4) e os scripts da sala chamam ``EmSetFromList2(i)`` para criar a entrada i;
``EmSetEvent(struct)`` cria um personagem a partir de uma struct avulsa com o mesmo formato (um evento do jogo
monta uma na pilha). Criar um personagem onde o jogo não previu é gravar essa struct numa página livre e chamar
``EmSetEvent`` pela extensão do emulador. O módulo do tipo precisa estar carregado ou o jogo o lê do disco (só
quatro módulos de inimigo ficam carregados por vez).

Comandos:
  listar                          slots ocupados do vetor: tipo, vida, posição, origem (lista ou evento).
  criar <tipo> [--vida N] [--distancia M] [--variante V]
                                  grava a struct e chama EmSetEvent; salva o estado no slot 95 antes.

Tipos vistos na lista do estágio 1: 0x12 aldeão (vida 500), 0x15 aldeão da vila (800), 0x23 corvo (10),
0x28 (100), 0x0F aliado com modelo de jogador. Tipos 0x00 a 0x0F são modelos de jogador (PL00..PL0F); a função de
mapeamento junta 3, 5 e 0xC como um só personagem por traje (candidata: Ada).
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from dataclasses import dataclass

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente, ResultadoChamada

EM_MGR = 0x004203B0
VETOR = 0x01789F40
PASSO = 0xED0
SLOTS = 60
EM_SET_EVENT = 0x001BD800
# a matriz da câmera é escrita a cada quadro pela thread de jogo (4 `sq` em 0x252830): ancorar a chamada nesse
# acesso faz a função rodar nessa thread, onde ela pode dormir pelo escalonador (carregar do disco o módulo de um
# tipo ainda não residente)
ANCORA_CAMERA = 0x004327C0
BLOCO_G = 0x00425BA0  # pG
CAMERA_OLHO = 0x003CA220
CAMERA_ALVO = 0x003CA230
SLOT_DE_SEGURANCA = 95


@dataclass(frozen=True)
class Personagem:
    slot: int
    cabecalho: int
    tipo: int
    variante: int
    origem: int  # índice na lista da sala ou 0xFF (criado por evento)
    vida: int
    vida_maxima: int
    posicao: tuple[float, float, float]

    @property
    def ativo(self) -> bool:
        return (self.cabecalho & 0x201) == 1


def montar_struct(
    tipo: int, variante: int, vida: int, posicao_mm: tuple[float, float, float], sala: int
) -> bytes:
    """EM_LIST de 32 bytes como o evento 0x1000 do jogo monta: posição em centímetros, rotação zero, +0x1A = 1."""
    cm = tuple(round(v / 10.0) for v in posicao_mm)
    return struct.pack("<BBBBIHBBhhhhhhHhI", 0, tipo, variante, 0, 1, vida, 0, 0, *cm, 0, 0, 0, sala, 1, 0)


def a_frente(
    jogador: tuple[float, float, float],
    olho: tuple[float, float, float],
    alvo: tuple[float, float, float],
    distancia_mm: float,
) -> tuple[float, float, float]:
    """Ponto à frente do jogador: a direção é a da câmera (alvo menos olho) no plano do chão, não a rotação da entidade."""
    dx, dz = alvo[0] - olho[0], alvo[2] - olho[2]
    n = math.hypot(dx, dz) or 1.0
    return (jogador[0] + dx / n * distancia_mm, jogador[1], jogador[2] + dz / n * distancia_mm)


def _ler(c: Cliente, codigo: p.Codigo, endereco: int) -> bytes:
    return c.pedir(p.comando(codigo, struct.pack("<I", endereco)))


def ler_vec3(c: Cliente, endereco: int) -> tuple[float, float, float]:
    corpo = c.pedir(*(p.comando(p.Codigo.READ32, struct.pack("<I", endereco + 4 * i)) for i in range(3)))
    x, y, z = struct.unpack_from("<fff", corpo, 0)
    return (float(x), float(y), float(z))


def ler_personagem(c: Cliente, slot: int) -> Personagem:
    base = VETOR + slot * PASSO
    corpo = c.pedir(
        p.comando(p.Codigo.READ32, struct.pack("<I", base)),
        p.comando(p.Codigo.READ8, struct.pack("<I", base + 0x11C)),
        p.comando(p.Codigo.READ8, struct.pack("<I", base + 0x11D)),
        p.comando(p.Codigo.READ8, struct.pack("<I", base + 0x4C0)),
        p.comando(p.Codigo.READ16, struct.pack("<I", base + 0x4B0)),
        p.comando(p.Codigo.READ16, struct.pack("<I", base + 0x4B2)),
    )
    cab, tipo, var, origem, vida, vida_max = struct.unpack_from("<IBBBhh", corpo, 0)
    return Personagem(slot, cab, tipo, var, origem, vida, vida_max, ler_vec3(c, base + 0xC0))


def listar_personagens(c: Cliente) -> list[Personagem]:
    return [ler_personagem(c, s) for s in range(SLOTS)]


def sala_atual(c: Cliente) -> int:
    corpo = c.pedir(p.comando(p.Codigo.READ16, struct.pack("<I", BLOCO_G + 0x7EB8)))
    return int(struct.unpack_from("<H", corpo, 0)[0])  # byte baixo sala, byte alto estágio


def criar_personagem(
    c: Cliente, tipo: int, vida: int = 1000, distancia_mm: float = 2000.0, variante: int = 0
) -> tuple[ResultadoChamada, Personagem | None]:
    jogador = ler_vec3(c, VETOR + 0xC0)
    posicao = a_frente(jogador, ler_vec3(c, CAMERA_OLHO), ler_vec3(c, CAMERA_ALVO), distancia_mm)
    dados = montar_struct(tipo, variante, vida, posicao, sala_atual(c))
    c.pedir(
        *(p.comando(p.Codigo.WRITE8, struct.pack("<IB", AREA_DO_MESTRE + i, b)) for i, b in enumerate(dados))
    )
    # com o módulo do tipo residente (ver bancada/modulos.py) a criação não dorme: chamada imediata
    r = c.chamar(EM_SET_EVENT, (AREA_DO_MESTRE,), tempo_limite_ms=5000)
    if not r.ok or r.v0 == 0 or not (VETOR <= r.v0 < VETOR + SLOTS * PASSO):  # errEm vale 0
        return r, None
    return r, ler_personagem(c, (r.v0 - VETOR) // PASSO)


def _cliente() -> Cliente:
    c = Cliente(porta=28011, tempo_limite_s=20.0)
    c.conectar()
    return c


def _linha(q: Personagem) -> str:
    x, y, z = q.posicao
    origem = "evento" if q.origem == 0xFF else f"lista {q.origem}"
    return f"slot {q.slot:2d} cab {q.cabecalho:08x} tipo {q.tipo:#04x} var {q.variante} vida {q.vida}/{q.vida_maxima} pos ({x:.0f}, {y:.0f}, {z:.0f}) {origem}"


def listar(_: argparse.Namespace) -> int:
    c = _cliente()
    try:
        vivos = [q for q in listar_personagens(c) if q.cabecalho]
        jogador = ler_vec3(c, VETOR + 0xC0)
        print(
            f"sala {sala_atual(c):04x}; jogador em ({jogador[0]:.0f}, {jogador[1]:.0f}, {jogador[2]:.0f}); {len(vivos)} slots usados"
        )
    finally:
        c.fechar()
    for q in vivos:
        print("  ", _linha(q))
    return 0


def criar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([SLOT_DE_SEGURANCA])))
        r, q = criar_personagem(c, args.tipo, args.vida, args.distancia * 1000.0, args.variante)
    finally:
        c.fechar()
    print(f"chamada: {r.estado} em {r.duracao_ms} ms, v0 {r.v0:#x}")
    if q is None:
        print("o jogo não criou o personagem (errEm); estado salvo no slot", SLOT_DE_SEGURANCA)
        return 1
    print("criado:", _linha(q))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("listar")
    s.set_defaults(func=listar)
    s = sub.add_parser("criar")
    s.add_argument("tipo", type=lambda x: int(x, 0))
    s.add_argument("--vida", type=int, default=1000)
    s.add_argument("--distancia", type=float, default=2.0, help="metros à frente do jogador")
    s.add_argument("--variante", type=int, default=0)
    s.set_defaults(func=criar)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
