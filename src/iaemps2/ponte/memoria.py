"""Leitura e escrita de uma variável do perfil pelo canal (caso A08; card S8-03).

Resolve o alvo declarado (endereço fixo, ponteiro mais deslocamento, ou vaga do vetor de personagens escolhida
por regra), lê e escreve no tipo certo e devolve o valor real (bruto dividido pela escala). Nada aqui decide se a
escrita pode acontecer: isso é do executor.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from iaemps2.catalogo.mundo import Alvo
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

FORMATOS = {"u8": "<B", "u16": "<H", "s16": "<h", "u32": "<I"}
LEITURAS = {"u8": p.Codigo.READ8, "u16": p.Codigo.READ16, "s16": p.Codigo.READ16, "u32": p.Codigo.READ32}
ESCRITAS = {"u8": p.Codigo.WRITE8, "u16": p.Codigo.WRITE16, "s16": p.Codigo.WRITE16, "u32": p.Codigo.WRITE32}
HEAP = (0x00100000, 0x02000000)
# vetor de personagens do jogo de abertura: EmMgr (+0 vetor, +4 vagas, +8 passo); vaga 0 = jogador
EM_MGR = 0x004203B0
POS, TIPO, VIDA = 0xC0, 0x11C, 0x4B0
TIPOS_DE_INIMIGO = range(0x10, 0x50)


class AlvoNaoResolvidoError(RuntimeError):
    """Ponteiro fora da memória, nenhuma entidade que sirva, ou vetor fora do esperado."""


@dataclass(frozen=True)
class Resolvido:
    endereco: int
    detalhe: str  # como chegou lá (ponteiro lido, vaga escolhida)


def _ler_bruto(c: Cliente, codigo: p.Codigo, formato: str, endereco: int) -> int:
    corpo = c.pedir(p.comando(codigo, struct.pack("<I", endereco)))
    return int(struct.unpack_from(formato, corpo, 0)[0])


def _u32(c: Cliente, endereco: int) -> int:
    return _ler_bruto(c, p.Codigo.READ32, "<I", endereco)


def _vec3(c: Cliente, endereco: int) -> tuple[float, float, float]:
    corpo = c.pedir(*(p.comando(p.Codigo.READ32, struct.pack("<I", endereco + 4 * i)) for i in range(3)))
    x, y, z = struct.unpack_from("<fff", corpo, 0)
    return float(x), float(y), float(z)


def resolver(c: Cliente, alvo: Alvo) -> Resolvido:
    if alvo.modo == "fixo":
        return Resolvido(alvo.endereco + alvo.deslocamento, "endereço fixo")
    if alvo.modo == "ponteiro":
        base = _u32(c, alvo.endereco)
        if not HEAP[0] <= base < HEAP[1]:
            raise AlvoNaoResolvidoError(
                f"ponteiro em {alvo.endereco:#010x} aponta para {base:#x}, fora da memória"
            )
        return Resolvido(base + alvo.deslocamento, f"ponteiro {alvo.endereco:#010x} -> {base:#010x}")
    return _resolver_entidade(c, alvo)


def _resolver_entidade(c: Cliente, alvo: Alvo) -> Resolvido:
    vetor, vagas, passo = (_u32(c, alvo.endereco + 4 * i) for i in range(3))
    if not HEAP[0] <= vetor < HEAP[1] or not 0 < vagas <= 256 or passo not in (0xED0, 0x1470):
        raise AlvoNaoResolvidoError(
            f"vetor de personagens fora do esperado: {vetor:#x}, {vagas} vagas, passo {passo:#x}"
        )
    jogador = _vec3(c, vetor + POS)
    melhor: tuple[float, int] | None = None
    for vaga in range(1, vagas):
        base = vetor + vaga * passo
        if _u32(c, base) & 0x201 != 1:
            continue
        tipo = _ler_bruto(c, p.Codigo.READ8, "<B", base + TIPO)
        if tipo not in TIPOS_DE_INIMIGO:
            continue
        if _ler_bruto(c, p.Codigo.READ16, "<h", base + VIDA) <= 0:
            continue
        pos = _vec3(c, base + POS)
        distancia = math.hypot(pos[0] - jogador[0], pos[2] - jogador[2])
        if melhor is None or distancia < melhor[0]:
            melhor = (distancia, vaga)
    if melhor is None:
        raise AlvoNaoResolvidoError("nenhum inimigo vivo no vetor de personagens")
    distancia, vaga = melhor
    return Resolvido(vetor + vaga * passo + alvo.deslocamento, f"vaga {vaga} a {distancia:.0f} mm do jogador")


def ler(c: Cliente, alvo: Alvo, endereco: int) -> int:
    return _ler_bruto(c, LEITURAS[alvo.tipo], FORMATOS[alvo.tipo], endereco) // alvo.escala


def escrever(c: Cliente, alvo: Alvo, endereco: int, valor: int) -> None:
    bruto = valor * alvo.escala
    c.pedir(p.comando(ESCRITAS[alvo.tipo], struct.pack("<I" + FORMATOS[alvo.tipo][1:], endereco, bruto)))
