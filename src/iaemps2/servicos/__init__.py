"""Adaptadores do serviço de linguagem atrás de uma interface única: descrever e decidir. Ver o Blueprint Técnico, capítulo 2."""

from __future__ import annotations

from iaemps2.servicos.base import Servico, ServicoError
from iaemps2.servicos.falso import ServicoFalso


def criar(nome: str) -> Servico:
    """O adaptador pelo nome configurado em [servico] ativo."""
    if nome == "falso":
        return ServicoFalso()
    if nome == "provedor_g":
        from iaemps2.servicos.provedor_g import ProvedorG

        return ProvedorG()
    raise ServicoError("fora_do_ar", f"adaptador desconhecido: {nome}")
