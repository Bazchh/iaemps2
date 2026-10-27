"""Adaptador real do primeiro provedor, o que o cliente já tem acesso. A chave vem só da variável de ambiente.

O SDK é importado tarde, para o pacote carregar sem ele instalado. O modelo é configurável; o padrão é o
mais leve com leitura de imagem. Toda falha vira ServicoError com a classe do contrato 4.
"""

from __future__ import annotations

import time
from typing import Any

from iaemps2.config import Config
from iaemps2.servicos.base import PedidoDescrever, PedidoDeTexto, Resposta, ServicoError

MODELO_PADRAO = "gemini-3.5-flash-lite"


class ProvedorG:
    nome = "provedor_g"

    def __init__(self, modelo: str = MODELO_PADRAO, tempo_limite_s: float = 20.0) -> None:
        chave = Config.chave_servico()
        if not chave:
            raise ServicoError("fora_do_ar", "sem chave: defina IAEMPS2_CHAVE_SERVICO no ambiente")
        from google import genai

        self.modelo = modelo
        self._cliente = genai.Client(api_key=chave, http_options={"timeout": int(tempo_limite_s * 1000)})

    def descrever(self, pedido: PedidoDescrever) -> Resposta:
        from google.genai import types

        return self._gerar(
            [
                types.Part.from_bytes(data=pedido.captura_jpeg, mime_type="image/jpeg"),
                types.Part.from_text(text=pedido.instrucao()),
            ]
        )

    def decidir(self, pedido: PedidoDeTexto) -> Resposta:
        from google.genai import types

        return self._gerar([types.Part.from_text(text=pedido.instrucao())])

    def _gerar(self, partes: list[Any]) -> Resposta:
        from google.genai import errors, types

        inicio = time.monotonic()
        conteudo = types.Content(role="user", parts=partes)
        try:
            resposta: Any = self._cliente.models.generate_content(
                model=self.modelo,
                contents=conteudo,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
            )
        except errors.APIError as erro:
            raise ServicoError(_classe(getattr(erro, "code", None)), str(erro)[:200]) from erro
        except Exception as erro:  # rede, tempo esgotado
            raise ServicoError("fora_do_ar", str(erro)[:200]) from erro
        latencia = int((time.monotonic() - inicio) * 1000)
        texto = resposta.text or ""
        if not texto:
            razao = _razao_de_bloqueio(resposta)
            if razao:
                raise ServicoError("recusa", razao)
            raise ServicoError("formato", "resposta vazia")
        uso = getattr(resposta, "usage_metadata", None)
        return Resposta(
            texto=texto,
            latencia_ms=latencia,
            tokens_entrada=getattr(uso, "prompt_token_count", None),
            tokens_saida=getattr(uso, "candidates_token_count", None),
            modelo=self.modelo,
        )


def _classe(codigo: int | None) -> str:
    if codigo == 429:
        return "limite"
    if codigo in (400, 403):
        return "recusa"
    return "fora_do_ar"


def _razao_de_bloqueio(resposta: Any) -> str | None:
    feedback = getattr(resposta, "prompt_feedback", None)
    razao = getattr(feedback, "block_reason", None)
    if razao:
        return f"bloqueado pelo provedor: {razao}"
    candidatos = getattr(resposta, "candidates", None) or []
    for c in candidatos:
        motivo = getattr(c, "finish_reason", None)
        if motivo and str(motivo).upper().endswith(("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST")):
            return f"recusado pelo provedor: {motivo}"
    return None
