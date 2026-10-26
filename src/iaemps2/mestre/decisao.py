"""A decisão em formato fechado e a validação dupla (card S3-03; casos C02, C03, C04; contrato 2).

O serviço devolve alavanca, parâmetros e motivo. A plataforma confere duas vezes: primeiro contra o catálogo,
as faixas e as regras de mesa; depois, antes de executar, contra a situação atual. Fora disso a decisão é
descartada inteira, nunca aproximada. "Nada" é decisão com motivo. Motivo impróprio vira o motivo padrão da
alavanca; a ação não é cancelada por causa do motivo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from iaemps2.catalogo.catalogo import NADA, Catalogo
from iaemps2.olho.situacao import Fase, Situacao
from iaemps2.ponte.protocolo import Status

LIMITE_MOTIVO = 120
PALAVRAS_QUE_GUIAM = (
    "vá ",
    "va ",
    "vai ",
    "siga ",
    "pegue ",
    "use ",
    "aperte ",
    "entre ",
    "volte ",
    "corra ",
    "atire ",
    "fuja ",
)


class DecisaoInvalidaError(ValueError):
    """A resposta do serviço não cabe no contrato 2."""


class Decisao(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alavanca: str = Field(min_length=1, max_length=40)
    parametros: dict[str, float] = Field(default_factory=dict)
    motivo: str = Field(default="", max_length=1000)


def validar_resposta(texto: str) -> Decisao:
    """Do texto do serviço à decisão bruta, ainda sem conferir contra o catálogo."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rstrip()[:-3] if t.rstrip().endswith("```") else t
    try:
        dados: Any = json.loads(t)
    except json.JSONDecodeError as erro:
        raise DecisaoInvalidaError(f"não é JSON: {erro.msg}") from erro
    if not isinstance(dados, dict):
        raise DecisaoInvalidaError("JSON não é um objeto")
    if "parametros" in dados and dados["parametros"] is None:
        dados["parametros"] = {}
    try:
        return Decisao.model_validate(dados)
    except ValidationError as erro:
        detalhes = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in erro.errors())
        raise DecisaoInvalidaError(detalhes) from erro


@dataclass(frozen=True)
class Veredito:
    """O que a plataforma decidiu sobre a decisão do serviço (grava em decisoes)."""

    alavanca: str  # 'nada' ou uma do catálogo
    parametros: dict[str, float]
    motivo: str
    motivo_origem: str  # servico | padrao | ausente
    origem: str  # servico | descarte | ritmo | bloqueio | falha
    descarte_motivo: str | None = None

    @property
    def executa(self) -> bool:
        return self.origem == "servico" and self.alavanca != NADA


def conferir_motivo(motivo: str, padrao: str) -> tuple[str, str]:
    """C04: uma frase, até o limite, sem instruir o jogador. Devolve (motivo, origem)."""
    limpo = " ".join(motivo.split())
    if not limpo:
        return padrao, "ausente"
    if len(limpo) > LIMITE_MOTIVO:
        return padrao, "padrao"
    baixo = limpo.lower() + " "
    if any(p in baixo for p in PALAVRAS_QUE_GUIAM):
        return padrao, "padrao"
    return limpo, "servico"


def descartar(decisao: Decisao | None, motivo: str) -> Veredito:
    return Veredito(NADA, {}, "", "ausente", "descarte", motivo)


def conferir(
    decisao: Decisao,
    catalogo: Catalogo,
    situacao: Situacao,
    aperto_dos_slots: dict[int, int],
) -> Veredito:
    """Validação 1 (C02 passo 3): catálogo, disponibilidade, faixa, regra de mesa, motivo."""
    if decisao.alavanca == NADA:
        nada = catalogo.alavanca(NADA)
        padrao = nada.motivo_padrao if nada else "Nada a fazer agora."
        motivo, origem_motivo = conferir_motivo(decisao.motivo, padrao)
        return Veredito(NADA, {}, motivo, origem_motivo, "servico")
    alavanca = catalogo.alavanca(decisao.alavanca)
    if alavanca is None:
        return descartar(decisao, f"fora do catálogo: {decisao.alavanca}")
    if not alavanca.disponivel:
        return descartar(decisao, f"indisponível: {decisao.alavanca}")
    esperados = set(alavanca.parametros)
    recebidos = set(decisao.parametros)
    if esperados != recebidos:
        return descartar(
            decisao,
            f"parâmetros de {alavanca.nome}: esperados {sorted(esperados)}, vieram {sorted(recebidos)}",
        )
    for nome, faixa in alavanca.parametros.items():
        if not faixa.contem(decisao.parametros[nome]):
            return descartar(
                decisao,
                f"fora da faixa: {alavanca.nome}.{nome}={decisao.parametros[nome]:g} não está em [{faixa.minimo:g}, {faixa.maximo:g}]",
            )
    if alavanca.nome == "recarregar":
        slot = int(decisao.parametros["slot"])
        if slot not in aperto_dos_slots:
            return descartar(decisao, f"recarregar: slot {slot} sem contexto")
        if aperto_dos_slots[slot] >= situacao.aperto:
            return descartar(
                decisao,
                f"regra de mesa (não derrota): slot {slot} tem aperto {aperto_dos_slots[slot]}, atual {situacao.aperto}",
            )
    motivo, origem_motivo = conferir_motivo(decisao.motivo, alavanca.motivo_padrao)
    parametros = {k: float(v) for k, v in decisao.parametros.items()}
    if "slot" in parametros:
        parametros["slot"] = float(int(parametros["slot"]))
    return Veredito(alavanca.nome, parametros, motivo, origem_motivo, "servico")


def situacao_mudou(
    decidida: Situacao, status_decidido: Status, agora: Situacao | None, status_agora: Status
) -> str | None:
    """Validação 2 (C02 passo 4; RN-08): status e fase iguais aos do pedido; senão, descarta por situação velha."""
    if status_agora != status_decidido:
        return f"status mudou: {status_decidido.name.lower()} -> {status_agora.name.lower()}"
    if agora is None:
        return None  # sem leitura nova: vale a decidida
    if agora.fase != decidida.fase:
        return f"fase mudou: {decidida.fase} -> {agora.fase}"
    if agora.fase is Fase.COMBATE and abs(agora.aperto - decidida.aperto) >= 2:
        return f"aperto mudou demais: {decidida.aperto} -> {agora.aperto}"
    return None
