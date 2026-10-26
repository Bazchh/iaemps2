"""Cliente do canal oficial do emulador (card S1-01): conectar, sondar, versão, status.

Fala o protocolo de `protocolo.py` por um socket local. Sem regra de negócio: devolve o que o emulador
diz e classifica as falhas de conexão (porta fechada, outro programa na porta, canal caído, tempo esgotado)
para a plataforma decidir. Testado contra o simulador; o teste marcado `emulador` roda contra o real.
"""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

from iaemps2.ponte import protocolo as p


class CanalError(RuntimeError):
    """Falha no canal, com a classe do contrato 4 do Blueprint."""

    def __init__(self, classe: str, detalhe: str) -> None:
        super().__init__(f"{classe}: {detalhe}")
        self.classe = classe
        self.detalhe = detalhe


class ComandoFalhouError(RuntimeError):
    """O emulador respondeu 255: comando desconhecido, sem jogo, ou argumento inválido."""


@dataclass(frozen=True)
class Identificacao:
    titulo: str
    serial: str
    crc: str
    versao_jogo: str


class Cliente:
    """Uma conexão com o canal. Cada chamada é um pedido e uma resposta; reconecta sozinho se o canal cair."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        porta: int = p.PORTA_PADRAO,
        tempo_limite_s: float = 3.0,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.host = host
        self.porta = porta
        self.tempo_limite_s = tempo_limite_s
        self.relogio = relogio
        self.dormir = dormir
        self._sock: socket.socket | None = None
        self.reconexoes = 0

    # ---------- conexão ----------
    def conectar(self) -> None:
        self.fechar()
        try:
            self._sock = socket.create_connection((self.host, self.porta), timeout=self.tempo_limite_s)
        except ConnectionRefusedError as erro:
            raise CanalError("porta_fechada", f"ninguém escuta em {self.host}:{self.porta}") from erro
        except TimeoutError as erro:
            raise CanalError("travado", f"sem resposta ao conectar em {self.host}:{self.porta}") from erro
        except OSError as erro:
            raise CanalError("porta_fechada", str(erro)) from erro

    def fechar(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> Cliente:
        self.conectar()
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    @property
    def conectado(self) -> bool:
        return self._sock is not None

    # ---------- protocolo ----------
    def pedir(self, *comandos: bytes) -> bytes:
        """Envia os comandos num pedido só e devolve o retorno. Reconecta uma vez se o canal caiu."""
        if self._sock is None:
            self.conectar()
        pedido = p.empacotar_pedido(*comandos)
        try:
            return self._trocar(pedido)
        except CanalError as erro:
            if erro.classe != "canal_caido":
                raise
            self.reconexoes += 1
            self.conectar()
            return self._trocar(pedido)

    def _trocar(self, pedido: bytes) -> bytes:
        assert self._sock is not None
        try:
            self._sock.sendall(pedido)
            cabecalho = _ler_exato(self._sock, 5)
        except TimeoutError as erro:
            self.fechar()
            raise CanalError("travado", "o emulador não respondeu no tempo limite") from erro
        except OSError as erro:
            self.fechar()
            raise CanalError("canal_caido", str(erro)) from erro
        if len(cabecalho) < 5:
            self.fechar()
            raise CanalError("canal_caido", "conexão fechada pelo emulador")
        tamanho, resultado = struct.unpack("<IB", cabecalho)
        if tamanho < 5 or tamanho > p.TAMANHO_MAXIMO_RESPOSTA:
            self.fechar()
            raise CanalError("outro_programa", f"resposta fora do protocolo (tamanho {tamanho})")
        try:
            corpo = _ler_exato(self._sock, tamanho - 5)
        except OSError as erro:
            self.fechar()
            raise CanalError("canal_caido", str(erro)) from erro
        if len(corpo) < tamanho - 5:
            self.fechar()
            raise CanalError("canal_caido", "resposta incompleta")
        if resultado == p.Resultado.FALHA:
            raise ComandoFalhouError("o emulador respondeu falha")
        if resultado != p.Resultado.OK:
            self.fechar()
            raise CanalError("outro_programa", f"código de resultado desconhecido {resultado}")
        return corpo

    # ---------- comandos ----------
    def versao(self) -> str:
        corpo = self.pedir(p.comando(p.Codigo.VERSION))
        texto, _ = p.ler_texto(corpo, 0)
        if not texto.startswith("PCSX2"):
            self.fechar()
            raise CanalError("outro_programa", f"a porta respondeu {texto!r}, não é o canal do emulador")
        return texto

    def status(self) -> p.Status:
        corpo = self.pedir(p.comando(p.Codigo.STATUS))
        (valor,) = struct.unpack_from("<I", corpo, 0)
        try:
            return p.Status(valor)
        except ValueError as erro:
            raise CanalError("outro_programa", f"status desconhecido {valor}") from erro

    def identificar(self) -> Identificacao:
        corpo = self.pedir(
            p.comando(p.Codigo.TITLE),
            p.comando(p.Codigo.ID),
            p.comando(p.Codigo.UUID),
            p.comando(p.Codigo.GAME_VERSION),
        )
        titulo, i = p.ler_texto(corpo, 0)
        serial, i = p.ler_texto(corpo, i)
        crc, i = p.ler_texto(corpo, i)
        versao_jogo, _ = p.ler_texto(corpo, i)
        return Identificacao(titulo, serial, crc, versao_jogo)

    def esperar_jogo(self, limite_s: float, intervalo_s: float = 1.0) -> p.Status:
        """Sonda o status até "rodando" ou até o limite. "Desligado" nos primeiros segundos é carregamento normal."""
        inicio = self.relogio()
        ultimo = p.Status.DESLIGADO
        while True:
            ultimo = self.status()
            if ultimo == p.Status.RODANDO:
                return ultimo
            if self.relogio() - inicio >= limite_s:
                return ultimo
            self.dormir(intervalo_s)


def _ler_exato(sock: socket.socket, n: int) -> bytes:
    dados = bytearray()
    while len(dados) < n:
        pedaco = sock.recv(n - len(dados))
        if not pedaco:
            break
        dados += pedaco
    return bytes(dados)
