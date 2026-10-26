"""Só o que mudou vai ao serviço (card S2-02; caso B03).

Compara a miniatura em cinza da captura nova com a da última enviada: a fração de pontos que mudou além de
um degrau é a medida de diferença. Abaixo do limiar, a captura é poupada; acima, ou com o tempo máximo sem
envio vencido, é liberada. Mudança de tamanho (tela cheia, outro jogo) descarta a referência e envia.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from iaemps2.olho.captura import MINIATURA, Captura

DEGRAU = 16  # níveis de cinza (0 a 255) que um ponto precisa mudar para contar


@dataclass(frozen=True)
class Veredito:
    enviar: bool
    motivo: str  # mudanca | intervalo_vencido | primeira | tamanho_mudou | sem_mudanca
    diferenca: float | None  # fração de pontos que mudaram; None quando não houve comparação


def diferenca(a: bytes, b: bytes, degrau: int = DEGRAU) -> float:
    """Fração de pontos da miniatura que mudaram mais que o degrau. 0 = iguais; 1 = tudo mudou."""
    if len(a) != len(b) or not a:
        return 1.0
    mudaram = sum(1 for x, y in zip(a, b, strict=True) if abs(x - y) > degrau)
    return mudaram / len(a)


class Comparador:
    """Decide, captura a captura, o que vai ao serviço. Guarda a última enviada como referência."""

    def __init__(
        self,
        limiar: float = 0.04,
        tempo_maximo_s: float = 30.0,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 <= limiar <= 1:
            raise ValueError("limiar entre 0 e 1")
        self.limiar = limiar
        self.tempo_maximo_s = tempo_maximo_s
        self.relogio = relogio
        self._referencia: Captura | None = None
        self._enviada_em: float | None = None
        self.enviadas = 0
        self.poupadas = 0

    def avaliar(self, captura: Captura) -> Veredito:
        ref = self._referencia
        if ref is None:
            return self._liberar(captura, "primeira", None)
        if (ref.largura, ref.altura) != (captura.largura, captura.altura) or len(ref.miniatura) != len(
            captura.miniatura
        ):
            return self._liberar(captura, "tamanho_mudou", None)
        medida = diferenca(ref.miniatura, captura.miniatura)
        if medida >= self.limiar:
            return self._liberar(captura, "mudanca", medida)
        if self._enviada_em is not None and self.relogio() - self._enviada_em >= self.tempo_maximo_s:
            return self._liberar(captura, "intervalo_vencido", medida)
        self.poupadas += 1
        return Veredito(False, "sem_mudanca", medida)

    def _liberar(self, captura: Captura, motivo: str, medida: float | None) -> Veredito:
        self._referencia = captura
        self._enviada_em = self.relogio()
        self.enviadas += 1
        return Veredito(True, motivo, medida)

    def esquecer(self) -> None:
        """Descarta a referência: a próxima captura é enviada como 'primeira'."""
        self._referencia = None
        self._enviada_em = None


def tamanho_esperado() -> int:
    return MINIATURA[0] * MINIATURA[1]
