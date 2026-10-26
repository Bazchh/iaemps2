"""Log estruturado (card S0-04): uma linha JSON por evento, sempre com sessão e ciclo quando existem.

Uso:
    from iaemps2 import log
    log.configurar()                      # uma vez, no ponto de entrada
    with log.contexto(sessao="…", ciclo=12):
        log.evento("captura.enviada", bytes=46000)

Nada de segredo entra aqui: a chave do serviço nunca é passada como campo, e o formatador recusa
qualquer campo cujo nome contenha "chave" ou "token".
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TextIO

_sessao: contextvars.ContextVar[str | None] = contextvars.ContextVar("sessao", default=None)
_ciclo: contextvars.ContextVar[int | None] = contextvars.ContextVar("ciclo", default=None)
NOME = "iaemps2"
PROIBIDOS = ("chave", "token", "senha", "secret", "key")


class CampoProibidoError(ValueError):
    """Tentativa de registrar um campo que pode carregar segredo."""


class FormatadorJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        linha: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "nivel": registro.levelname.lower(),
            "evento": registro.getMessage(),
            "sessao": _sessao.get(),
            "ciclo": _ciclo.get(),
        }
        extras = getattr(registro, "campos", None)
        if isinstance(extras, dict):
            linha.update(extras)
        if registro.exc_info:
            linha["erro"] = self.formatException(registro.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar(destino: TextIO | None = None, nivel: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(NOME)
    logger.handlers.clear()
    manipulador = logging.StreamHandler(destino or sys.stderr)
    manipulador.setFormatter(FormatadorJson())
    logger.addHandler(manipulador)
    logger.setLevel(nivel)
    logger.propagate = False
    return logger


@contextmanager
def contexto(sessao: str | None = None, ciclo: int | None = None) -> Iterator[None]:
    marca_sessao = _sessao.set(sessao) if sessao is not None else None
    marca_ciclo = _ciclo.set(ciclo) if ciclo is not None else None
    try:
        yield
    finally:
        if marca_ciclo is not None:
            _ciclo.reset(marca_ciclo)
        if marca_sessao is not None:
            _sessao.reset(marca_sessao)


def evento(nome: str, nivel: int = logging.INFO, **campos: Any) -> None:
    for campo in campos:
        if any(proibido in campo.lower() for proibido in PROIBIDOS):
            raise CampoProibidoError(f"campo {campo!r} não entra no log")
    logging.getLogger(NOME).log(nivel, nome, extra={"campos": campos})


def falha(nome: str, **campos: Any) -> None:
    evento(nome, nivel=logging.ERROR, **campos)
