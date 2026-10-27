"""O adaptador falso: respostas gravadas, em ordem, sem rede. É o que o CI e a bancada usam."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from iaemps2.servicos.base import PedidoDescrever, PedidoDeTexto, Resposta, ServicoError

RESPOSTA_PADRAO = (
    '{"descricao": "Tela de jogo sem evento visível.", "fase": "exploracao", "aperto": 0, "confianca": 0.5}'
)
DECISAO_PADRAO = '{"alavanca": "nada", "parametros": {}, "motivo": "Nada a fazer agora."}'


class ServicoFalso:
    nome = "falso"

    def __init__(
        self,
        respostas: Iterable[str | ServicoError] = (),
        decisoes: Iterable[str | ServicoError] = (),
        latencia_ms: int = 5,
    ) -> None:
        self._fila: deque[str | ServicoError] = deque(respostas)
        self._decisoes: deque[str | ServicoError] = deque(decisoes)
        self.latencia_ms = latencia_ms
        self.pedidos: list[PedidoDescrever] = []
        self.pedidos_de_decisao: list[PedidoDeTexto] = []

    def enfileirar(self, *respostas: str | ServicoError) -> None:
        self._fila.extend(respostas)

    def enfileirar_decisoes(self, *decisoes: str | ServicoError) -> None:
        self._decisoes.extend(decisoes)

    def decidir(self, pedido: PedidoDeTexto) -> Resposta:
        self.pedidos_de_decisao.append(pedido)
        proxima = self._decisoes.popleft() if self._decisoes else DECISAO_PADRAO
        if isinstance(proxima, ServicoError):
            raise proxima
        return Resposta(
            texto=proxima, latencia_ms=self.latencia_ms, tokens_entrada=900, tokens_saida=40, modelo="falso"
        )

    def descrever(self, pedido: PedidoDescrever) -> Resposta:
        self.pedidos.append(pedido)
        proxima = self._fila.popleft() if self._fila else RESPOSTA_PADRAO
        if isinstance(proxima, ServicoError):
            raise proxima
        return Resposta(
            texto=proxima, latencia_ms=self.latencia_ms, tokens_entrada=300, tokens_saida=40, modelo="falso"
        )
