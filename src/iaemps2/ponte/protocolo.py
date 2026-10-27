"""O protocolo binário do canal oficial do emulador (PINE), mais a extensão da versão própria.

Pedido:  u32 tamanho total (inclui estes 4 bytes) · um ou mais comandos (u8 código · argumento).
Resposta: u32 tamanho total (inclui estes 5 bytes) · u8 resultado (0 ok, 255 falha) · retornos em sequência.
Vários comandos no mesmo pedido são processados em ordem; o primeiro que falha falha o pedido inteiro.
Verificado no código-fonte do emulador 2.8.2 (pcsx2/PINE.cpp). Ver o Blueprint Técnico, capítulo 6.
"""

from __future__ import annotations

import struct
from enum import IntEnum

PORTA_PADRAO = 28011
TAMANHO_MAXIMO_PEDIDO = 650_000
TAMANHO_MAXIMO_RESPOSTA = 450_000


class Codigo(IntEnum):
    # canal oficial
    READ8 = 0x00
    READ16 = 0x01
    READ32 = 0x02
    READ64 = 0x03
    WRITE8 = 0x04
    WRITE16 = 0x05
    WRITE32 = 0x06
    WRITE64 = 0x07
    VERSION = 0x08
    SAVE_STATE = 0x09
    LOAD_STATE = 0x0A
    TITLE = 0x0B
    ID = 0x0C
    UUID = 0x0D
    GAME_VERSION = 0x0E
    STATUS = 0x0F
    # extensão da versão própria (bit 7 ligado)
    EXT_CAPABILITIES = 0x80
    EXT_SET_PAUSED = 0x81
    EXT_SET_SPEED = 0x82
    EXT_GET_SPEED = 0x83
    # camada de cena (fase 4, prova S7-00; ainda fora da máscara de capacidades)
    EXT_SCENE_LIST = 0x84
    EXT_SCENE_RULE = 0x85
    EXT_SCENE_CLEAR = 0x86
    EXT_SCENE_STATS = 0x88


class Resultado(IntEnum):
    OK = 0x00
    FALHA = 0xFF


class Status(IntEnum):
    RODANDO = 0
    PAUSADO = 1
    DESLIGADO = 2


class ModoVelocidade(IntEnum):
    NORMAL = 0
    LENTA = 1
    TURBO = 2
    ILIMITADA = 3  # só lida: o jogador ligou pelo atalho do emulador; o mestre nunca pede


# máscara de capacidades da extensão
CAP_PAUSA = 1
CAP_VELOCIDADE = 2
CAP_RESULTADO_ESTADO = 4
CAP_CENA = 8  # camada de cena (fase 4): códigos 0x84 a 0x88
VERSAO_EXTENSAO = 1

TAMANHO_LEITURA = {Codigo.READ8: 1, Codigo.READ16: 2, Codigo.READ32: 4, Codigo.READ64: 8}
TAMANHO_ESCRITA = {Codigo.WRITE8: 1, Codigo.WRITE16: 2, Codigo.WRITE32: 4, Codigo.WRITE64: 8}


def empacotar_pedido(*comandos: bytes) -> bytes:
    corpo = b"".join(comandos)
    return struct.pack("<I", 4 + len(corpo)) + corpo


def comando(codigo: Codigo, argumento: bytes = b"") -> bytes:
    return bytes([codigo]) + argumento


def empacotar_resposta(resultado: Resultado, retorno: bytes = b"") -> bytes:
    return struct.pack("<IB", 5 + len(retorno), resultado) + retorno


def texto(valor: str) -> bytes:
    """Retorno de texto do canal: u32 tamanho (com o nulo final) + bytes + nulo."""
    dados = valor.encode("utf-8") + b"\x00"
    return struct.pack("<I", len(dados)) + dados


def ler_texto(dados: bytes, posicao: int) -> tuple[str, int]:
    (n,) = struct.unpack_from("<I", dados, posicao)
    inicio = posicao + 4
    return dados[inicio : inicio + n].rstrip(b"\x00").decode("utf-8", "replace"), inicio + n
