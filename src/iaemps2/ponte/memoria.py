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
    base: int = 0  # ponteiro lido, ou vetor de personagens
    vaga: int = -1  # vaga escolhida (entidade)
    tipo: int = -1  # tipo da entidade na hora

    def chaves(self) -> dict[str, float]:
        """O que vai no caminho de volta para conferir o alvo no fim do prazo."""
        return {"base": float(self.base), "vaga": float(self.vaga), "tipo": float(self.tipo)}


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
        return Resolvido(base + alvo.deslocamento, f"ponteiro {alvo.endereco:#010x} -> {base:#010x}", base)
    return _resolver_entidade(c, alvo)


def conferir_alvo(c: Cliente, alvo: Alvo, volta: dict[str, float]) -> int | None:
    """O endereço gravado na ida ainda é o mesmo alvo? Ponteiro trocado, vetor recriado, vaga morta ou de
    outro tipo: None, e a volta não escreve (escreveria em outro personagem ou em memória alheia)."""
    endereco = int(volta["endereco"])
    if alvo.modo == "fixo":
        return endereco
    if alvo.modo == "ponteiro":
        return endereco if _u32(c, alvo.endereco) == int(volta["base"]) else None
    vetor = _u32(c, alvo.endereco)
    if vetor != int(volta["base"]):
        return None
    base = endereco - alvo.deslocamento
    if _u32(c, base) & 0x201 != 1:
        return None
    if _ler_bruto(c, p.Codigo.READ8, "<B", base + TIPO) != int(volta["tipo"]):
        return None
    return endereco


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
    tipo = _ler_bruto(c, p.Codigo.READ8, "<B", vetor + vaga * passo + TIPO)
    return Resolvido(
        vetor + vaga * passo + alvo.deslocamento,
        f"vaga {vaga} a {distancia:.0f} mm do jogador",
        vetor,
        vaga,
        tipo,
    )


def ler(c: Cliente, alvo: Alvo, endereco: int) -> int:
    return _ler_bruto(c, LEITURAS[alvo.tipo], FORMATOS[alvo.tipo], endereco) // alvo.escala


def escrever(c: Cliente, alvo: Alvo, endereco: int, valor: int) -> None:
    bruto = valor * alvo.escala
    c.pedir(p.comando(ESCRITAS[alvo.tipo], struct.pack("<I" + FORMATOS[alvo.tipo][1:], endereco, bruto)))
