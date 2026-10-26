"""A interface única do serviço de linguagem (Blueprint, capítulo 2): descrever e decidir.

Todo adaptador devolve texto bruto e as medidas; quem valida contra o contrato é o olho (situação) e o
mestre (decisão). Nenhum adaptador conhece o emulador, o catálogo nem o registro. A chave nunca passa por
aqui como argumento: o adaptador real a lê da variável de ambiente ao ser criado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from iaemps2.olho.situacao import LIMITE_DESCRICAO, Fase

ESCALA_APERTO = "0 tranquilo, 1 atento, 2 pressionado, 3 em perigo, 4 prestes a morrer"


@dataclass(frozen=True)
class PedidoDescrever:
    """Contrato 1 do Blueprint: o que vai ao serviço para virar situação."""

    jogo_titulo: str
    jogo_serial: str
    status: str  # rodando | pausado | desligado
    velocidade: float
    ultima_alavanca: str | None
    ultima_alavanca_ha_ms: int | None
    situacao_anterior: dict[str, Any] | None
    captura_jpeg: bytes = field(repr=False)

    def instrucao(self) -> str:
        fases = ", ".join(f.value for f in Fase)
        return (
            "Você observa a tela de um jogo de PlayStation 2 como espectador. Descreva a situação do jogador "
            "em UMA linha de até "
            f"{LIMITE_DESCRICAO} caracteres, em português do Brasil, e classifique. Responda SÓ com JSON, sem "
            "comentário e sem cerca de código, exatamente com estes quatro campos: "
            '{"descricao": string, "fase": uma de [' + fases + "], "
            '"aperto": inteiro de 0 a 4 (' + ESCALA_APERTO + '), "confianca": número de 0 a 1}. '
            "Fases: exploracao e combate são jogo; menu, video, carregamento, morte e sistema não são. "
            f"Contexto: jogo {self.jogo_titulo} ({self.jogo_serial}); emulador {self.status}; velocidade "
            f"{self.velocidade:g}x; última ação do mestre: {self.ultima_alavanca or 'nenhuma'}"
            + (f" há {self.ultima_alavanca_ha_ms} ms" if self.ultima_alavanca_ha_ms is not None else "")
            + "; situação anterior: "
            + (
                json.dumps(self.situacao_anterior, ensure_ascii=False)
                if self.situacao_anterior
                else "nenhuma"
            )
            + "."
        )


@dataclass(frozen=True)
class Resposta:
    texto: str
    latencia_ms: int
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    modelo: str | None = None


class ServicoError(RuntimeError):
    """Falha do serviço, com a classe do contrato 4: fora_do_ar, limite, recusa, formato."""

    def __init__(self, classe: str, detalhe: str) -> None:
        super().__init__(f"{classe}: {detalhe}")
        self.classe = classe
        self.detalhe = detalhe


class Servico(Protocol):
    nome: str

    def descrever(self, pedido: PedidoDescrever) -> Resposta: ...
