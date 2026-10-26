"""O contador da sessão e o intervalo mínimo (cards S3-01 e D04).

O contador é monotônico e próprio da sessão: nunca usa a hora do sistema, então salto de relógio não o afeta.
O intervalo mínimo mede o tempo desde a última intervenção descontando o tempo congelado, que é o tempo em
tela fora de jogo (B04): em menu, vídeo ou carregamento o relógio do mestre para.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class Contador:
    """Milissegundos desde o início da sessão, por um relógio monotônico injetável."""

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._inicio = relogio()
        self._congelado_desde: float | None = None
        self._congelado_total = 0.0

    def agora_ms(self) -> int:
        return int((self._relogio() - self._inicio) * 1000)

    def congelar(self) -> None:
        if self._congelado_desde is None:
            self._congelado_desde = self._relogio()

    def descongelar(self) -> None:
        if self._congelado_desde is not None:
            self._congelado_total += self._relogio() - self._congelado_desde
            self._congelado_desde = None

    @property
    def congelado(self) -> bool:
        return self._congelado_desde is not None

    def ativo_ms(self) -> int:
        """Tempo da sessão descontado o congelado: é o relógio do intervalo mínimo."""
        parado = self._congelado_total
        if self._congelado_desde is not None:
            parado += self._relogio() - self._congelado_desde
        return int((self._relogio() - self._inicio - parado) * 1000)


class IntervaloMinimo:
    """Garante espaço entre intervenções (RN-05). Reversão do jogador conta como intervenção (D03)."""

    def __init__(self, contador: Contador, minimo_ms: int) -> None:
        if minimo_ms < 0:
            raise ValueError("intervalo mínimo negativo")
        self.contador = contador
        self.minimo_ms = minimo_ms
        self._ultima_ms: int | None = None

    def venceu(self) -> bool:
        return self.faltam_ms() == 0

    def faltam_ms(self) -> int:
        if self._ultima_ms is None:
            return 0
        passado = self.contador.ativo_ms() - self._ultima_ms
        return max(0, self.minimo_ms - passado)

    def zerar(self) -> None:
        """Uma intervenção aconteceu agora: a contagem recomeça."""
        self._ultima_ms = self.contador.ativo_ms()

    def tratar_como_vencido(self) -> None:
        """Retomada após pausa ou falha: o mestre pode agir de novo quando a situação pedir."""
        self._ultima_ms = None

    def reiniciar(self, minimo_ms: int | None = None) -> None:
        if minimo_ms is not None:
            self.minimo_ms = minimo_ms
        self._ultima_ms = None
