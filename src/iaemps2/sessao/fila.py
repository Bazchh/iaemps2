"""A fila única de eventos (card S3-01; Blueprint, capítulo 4, concorrência).

Serviço, captura e teclas só enfileiram. Um laço só retira, em ordem de chegada, e processa cada evento até
o fim antes do próximo. Nunca trava fina, nunca dois laços.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from iaemps2.sessao.maquina import Estado, Evento, Resultado, TransicaoInvalidaError, transicao


@dataclass(frozen=True)
class Mensagem:
    evento: Evento
    dados: dict[str, Any] = field(default_factory=dict)
    origem: str = "plataforma"  # plataforma | captura | servico | jogador


class FilaDeEventos:
    def __init__(self) -> None:
        self._fila: queue.Queue[Mensagem] = queue.Queue()

    def enfileirar(self, evento: Evento, origem: str = "plataforma", **dados: Any) -> None:
        """Pode ser chamada de qualquer thread. Nunca processa: só deposita."""
        self._fila.put(Mensagem(evento, dict(dados), origem))

    def retirar(self, espera_s: float | None = None) -> Mensagem | None:
        try:
            return self._fila.get(timeout=espera_s)
        except queue.Empty:
            return None

    def pendentes(self) -> int:
        return self._fila.qsize()


class Laco:
    """Aplica a máquina de estados aos eventos da fila, um por vez, na thread que o roda."""

    def __init__(
        self,
        fila: FilaDeEventos,
        executar_efeitos: Callable[[Resultado, Mensagem, Estado], None],
        registrar_invalida: Callable[[TransicaoInvalidaError, Mensagem], None] | None = None,
        estado_inicial: Estado = Estado.ABRINDO,
    ) -> None:
        self.fila = fila
        self.estado = estado_inicial
        self._executar = executar_efeitos
        self._invalida = registrar_invalida
        self._trava = threading.Lock()  # só para garantir um laço por vez; não é trava fina
        self.processados = 0
        self.recusados = 0

    def processar_um(self, espera_s: float | None = 0.0) -> bool:
        """Retira e processa um evento. Devolve False se a fila estava vazia."""
        mensagem = self.fila.retirar(espera_s)
        if mensagem is None:
            return False
        with self._trava:
            anterior = self.estado
            try:
                resultado = transicao(anterior, mensagem.evento)
            except TransicaoInvalidaError as erro:
                self.recusados += 1
                if self._invalida is not None:
                    self._invalida(erro, mensagem)
                return True
            self.estado = resultado.proximo
            self._executar(resultado, mensagem, anterior)
            self.processados += 1
        return True

    def processar_todos(self) -> int:
        n = 0
        while self.processar_um(espera_s=0.0):
            n += 1
        return n

    def rodar_ate(self, estado_final: Estado = Estado.ENCERRADA, espera_s: float = 0.2) -> None:
        while self.estado != estado_final:
            self.processar_um(espera_s)
