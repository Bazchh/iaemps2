"""Trava de rede: nenhum teste sai da máquina (Blueprint, capítulo 9).

Só conexões para o endereço local passam, porque o simulador do canal (card S0-03) escuta em 127.0.0.1.
Qualquer outra conexão falha na hora com mensagem clara. O adaptador falso cobre o serviço de linguagem.
Testes marcados com `emulador` ou `servico` são pulados sem a variável IAEMPS2_TESTES_REAIS=1.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Iterator
from typing import Any

import pytest

LOCAIS = {"127.0.0.1", "::1", "localhost"}


class RedeProibidaError(RuntimeError):
    """Um teste tentou abrir conexão para fora da máquina."""


def _so_local(original: Callable[..., Any]) -> Callable[..., Any]:
    def conectar(self: socket.socket, endereco: Any, *args: Any, **kwargs: Any) -> Any:
        host = endereco[0] if isinstance(endereco, tuple) else endereco
        if str(host) not in LOCAIS:
            raise RedeProibidaError(
                f"teste tentou conectar em {host!r}; use o simulador ou o adaptador falso"
            )
        return original(self, endereco, *args, **kwargs)

    return conectar


@pytest.fixture(autouse=True)
def sem_rede(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("emulador") or request.node.get_closest_marker("servico"):
        yield
        return
    monkeypatch.setattr(socket.socket, "connect", _so_local(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _so_local(socket.socket.connect_ex))
    yield


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("IAEMPS2_TESTES_REAIS") == "1":
        return
    pular = pytest.mark.skip(reason="precisa do emulador ou do serviço real; defina IAEMPS2_TESTES_REAIS=1")
    for item in items:
        if item.get_closest_marker("emulador") or item.get_closest_marker("servico"):
            item.add_marker(pular)
