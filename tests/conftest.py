"""Trava de rede: nenhum teste chama a rede nem o emulador real (Blueprint, capítulo 9).

Qualquer tentativa de abrir um socket durante os testes falha na hora com mensagem clara.
O simulador do canal (card S0-03) e o adaptador falso cobrem tudo. Testes marcados com
`emulador` ou `servico` são pulados sem a variável IAEMPS2_TESTES_REAIS=1.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from typing import Any

import pytest


class RedeProibidaError(RuntimeError):
    """Um teste tentou abrir conexão de rede."""


def _socket_proibido(*_args: Any, **_kwargs: Any) -> None:
    raise RedeProibidaError("teste tentou abrir socket; use o simulador ou o adaptador falso")


@pytest.fixture(autouse=True)
def sem_rede(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("emulador") or request.node.get_closest_marker("servico"):
        yield
        return
    monkeypatch.setattr(socket, "socket", _socket_proibido)
    monkeypatch.setattr(socket, "create_connection", _socket_proibido)
    yield


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("IAEMPS2_TESTES_REAIS") == "1":
        return
    pular = pytest.mark.skip(reason="precisa do emulador ou do serviço real; defina IAEMPS2_TESTES_REAIS=1")
    for item in items:
        if item.get_closest_marker("emulador") or item.get_closest_marker("servico"):
            item.add_marker(pular)
