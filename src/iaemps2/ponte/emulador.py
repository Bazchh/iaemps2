"""Identificar o jogo e o modo do emulador (card S1-02; casos A02 e A07).

Por cima do cliente: pergunta quem é o jogo (título, serial, soma, versão) e se o emulador é a versão
própria (consulta de capacidades, código 0x80). No emulador original a consulta falha, e isso é o modo
reduzido. Também detecta troca de jogo entre duas identificações e serial ausente.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente, ComandoFalhouError, Identificacao

MODO_COMPLETO = "completo"
MODO_REDUZIDO = "reduzido"


@dataclass(frozen=True)
class Capacidades:
    versao_extensao: int
    pausa: bool
    velocidade: bool
    resultado_estado: bool
    cena: bool = False  # camada de cena (fase 4)

    @property
    def modo(self) -> str:
        return MODO_COMPLETO if (self.pausa or self.velocidade) else MODO_REDUZIDO


SEM_EXTENSAO = Capacidades(versao_extensao=0, pausa=False, velocidade=False, resultado_estado=False)


@dataclass(frozen=True)
class JogoEmExecucao:
    identificacao: Identificacao
    emulador_versao: str
    capacidades: Capacidades

    @property
    def identificado(self) -> bool:
        """Serial vazio (programa caseiro, disco não reconhecido) nunca casa perfil por título (A02 E1)."""
        return bool(self.identificacao.serial.strip())

    @property
    def modo(self) -> str:
        return self.capacidades.modo

    @property
    def chave(self) -> tuple[str, str]:
        """O que identifica o jogo para casar perfil e para detectar troca: serial e soma, nunca o título."""
        return (self.identificacao.serial, self.identificacao.crc)


def consultar_capacidades(cliente: Cliente) -> Capacidades:
    """No emulador original o código 0x80 cai no caso padrão e volta falha: modo reduzido (A07)."""
    try:
        corpo = cliente.pedir(p.comando(p.Codigo.EXT_CAPABILITIES))
    except ComandoFalhouError:
        return SEM_EXTENSAO
    versao, mascara = struct.unpack_from("<HI", corpo, 0)
    return Capacidades(
        versao_extensao=int(versao),
        pausa=bool(mascara & p.CAP_PAUSA),
        velocidade=bool(mascara & p.CAP_VELOCIDADE),
        resultado_estado=bool(mascara & p.CAP_RESULTADO_ESTADO),
        cena=bool(mascara & p.CAP_CENA),
    )


def identificar(cliente: Cliente) -> JogoEmExecucao:
    """Exige o jogo rodando (status já sondado pelo caso A01). Com o jogo carregando, o título falha."""
    return JogoEmExecucao(
        identificacao=cliente.identificar(),
        emulador_versao=cliente.versao(),
        capacidades=consultar_capacidades(cliente),
    )


def trocou_de_jogo(antes: JogoEmExecucao, agora: JogoEmExecucao) -> bool:
    """Serial ou soma mudaram: a sessão anterior encerra e nada dela vale para a nova (A02 A2)."""
    return antes.chave != agora.chave
