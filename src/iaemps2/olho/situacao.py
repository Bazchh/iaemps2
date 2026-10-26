"""A situação em formato fechado (card S2-03; casos B02 e B04; decisão DC-16; contrato 1 do Blueprint).

O serviço devolve JSON; aqui ele é validado contra o contrato: descrição em uma linha de até 160 caracteres,
fase numa lista fixa, aperto de 0 a 4, confiança de 0 a 1, nenhum campo a mais ou a menos. Fora disso é
resposta inválida, e nada é inventado para preencher. Também: suspeita quando a fase contradiz o status do
emulador, e o bloqueio por tela fora de jogo com o marco de morte.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from iaemps2.ponte.protocolo import Status


class Fase(StrEnum):
    EXPLORACAO = "exploracao"
    COMBATE = "combate"
    MENU = "menu"
    VIDEO = "video"
    CARREGAMENTO = "carregamento"
    MORTE = "morte"
    SISTEMA = "sistema"


FASES_DE_JOGO = frozenset({Fase.EXPLORACAO, Fase.COMBATE})
LIMITE_DESCRICAO = 160


class SituacaoInvalidaError(ValueError):
    """A resposta do serviço não cabe no contrato."""


class Situacao(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    descricao: str = Field(min_length=1, max_length=LIMITE_DESCRICAO)
    fase: Fase
    aperto: int = Field(ge=0, le=4)
    confianca: float = Field(ge=0, le=1)

    @field_validator("descricao")
    @classmethod
    def _uma_linha(cls, valor: str) -> str:
        limpa = " ".join(valor.split())
        if not limpa:
            raise ValueError("descrição vazia")
        if len(limpa) > LIMITE_DESCRICAO:
            raise ValueError("descrição longa demais")
        return limpa

    @property
    def em_jogo(self) -> bool:
        return self.fase in FASES_DE_JOGO


def validar(resposta_bruta: str) -> Situacao:
    """Do texto do serviço à situação. Aceita o JSON cercado de cerca de código, que alguns serviços mandam."""
    texto = _sem_cerca(resposta_bruta)
    try:
        dados: Any = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise SituacaoInvalidaError(f"não é JSON: {erro.msg}") from erro
    if not isinstance(dados, dict):
        raise SituacaoInvalidaError("JSON não é um objeto")
    try:
        return Situacao.model_validate(dados)
    except ValidationError as erro:
        detalhes = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in erro.errors())
        raise SituacaoInvalidaError(detalhes) from erro


def suspeita(situacao: Situacao, status: Status) -> str | None:
    """A descrição contradiz o emulador: combate ou exploração com o jogo pausado ou desligado (B02 E3)."""
    if situacao.em_jogo and status != Status.RODANDO:
        return f"fase {situacao.fase} com emulador {status.name.lower()}"
    return None


def bloqueia_intervencao(situacao: Situacao) -> bool:
    """Fora de jogo (menu, vídeo, carregamento, morte, sistema) o mestre não decide (B04)."""
    return not situacao.em_jogo


def e_marco_de_morte(anterior: Situacao | None, atual: Situacao) -> bool:
    """A morte vira marco uma vez, na transição para a fase morte (B04 passo 3)."""
    return atual.fase == Fase.MORTE and (anterior is None or anterior.fase != Fase.MORTE)


def _sem_cerca(texto: str) -> str:
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
