"""Cliente do canal oficial do emulador (card S1-01): conectar, sondar, versão, status.

Fala o protocolo de `protocolo.py` por um socket local. Sem regra de negócio: devolve o que o emulador
diz e classifica as falhas de conexão (porta fechada, outro programa na porta, canal caído, tempo esgotado)
para a plataforma decidir. Testado contra o simulador; o teste marcado `emulador` roda contra o real.
"""

from __future__ import annotations

import socket
import struct
import threading
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
class Assinatura:
    """Um lote de desenho do último quadro, como a camada de cena o vê (prova S7-00)."""

    hash_textura: int
    hash_forma: (
        int  # coordenadas de textura quantizadas: não muda com câmera nem pose; nomeia o pedaço de malha
    )
    vertices: int
    x0: int
    y0: int
    x1: int
    y1: int
    z_min: int
    z_max: int
    fallback: bool  # identidade pelo endereço da textura, não por hash
    qualifica: bool  # desenho de mundo: alvo + profundidade + teste e escrita de profundidade

    @property
    def area(self) -> int:
        return max(0, self.x1 - self.x0) * max(0, self.y1 - self.y0)


@dataclass(frozen=True)
class EstatisticasCena:
    regra_existe: bool
    quadros_total: int
    quadros_vista: int
    quadros_aplicada: int
    camada_quadros: int
    camada_ns_total: int
    camada_ns_ultimo_quadro: int
    desenhos_ultimo_quadro: int
    qualificados_ultimo_quadro: int
    com_hash_ultimo_quadro: int


@dataclass(frozen=True)
class AcessoVigiado:
    """Uma instrução do jogo que tocou a faixa vigiada, com o que ela fez no primeiro e no último acesso."""

    pc: int
    op: int
    primeiro_endereco: int
    ultimo_endereco: int
    contagem: int
    bits: int
    escrita: bool
    ultimo_valor: int
    registradores: tuple[int, ...]  # 32 registradores gerais (32 bits baixos) no primeiro acesso

    @property
    def base(self) -> int:
        """Registrador-base da instrução (rs): o ponteiro de onde o endereço saiu."""
        return (self.op >> 21) & 0x1F

    @property
    def deslocamento(self) -> int:
        d = self.op & 0xFFFF
        return d - 0x10000 if d & 0x8000 else d


@dataclass(frozen=True)
class EstadoVigia:
    ativo: bool
    inicio: int
    fim: int
    acessos_total: int
    descartados: int
    instrucoes: int
    restante_ms: int


VIGIA_LEITURA = 1
VIGIA_ESCRITA = 2
VIGIA_AMBOS = 3

# memória reservada pela extensão para a chamada remota: 0x01FF0000 trampolim, pilha abaixo de 0x01FF8000,
# e esta página livre para os dados que o mestre passa por ponteiro (structs, textos)
AREA_DO_MESTRE = 0x01FF8000
AREA_DO_MESTRE_FIM = 0x01FFC000


@dataclass(frozen=True)
class ResultadoChamada:
    estado: str  # "ok", "prazo" (abortada no prazo, registradores restaurados) ou "recusada" (ocupado ou jogo parado)
    v0: int
    v1: int
    duracao_ms: int

    @property
    def ok(self) -> bool:
        return self.estado == "ok"


ESTADOS_CHAMADA = {0: "ok", 1: "prazo", 2: "recusada"}

REGRA_ESCONDER = 1
REGRA_QUADRADO = 2


@dataclass(frozen=True)
class Velocidade:
    modo: p.ModoVelocidade
    alvo: float
    restante_ms: int


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
        self._trava = threading.RLock()
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
        """Envia os comandos num pedido só e devolve o retorno. Reconecta uma vez se o canal caiu.
        Um pedido por vez: o laço e o relógio de fim das ações usam o mesmo canal de threads diferentes."""
        with self._trava:
            return self._pedir(*comandos)

    def _pedir(self, *comandos: bytes) -> bytes:
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

    # ---------- extensão da versão própria (códigos 0x81 a 0x83; falham no emulador original) ----------
    def pausar(self, pausar: bool) -> None:
        self.pedir(p.comando(p.Codigo.EXT_SET_PAUSED, bytes([1 if pausar else 0])))

    def velocidade(self, modo: p.ModoVelocidade, escalar: float, duracao_ms: int) -> None:
        self.pedir(
            p.comando(p.Codigo.EXT_SET_SPEED, struct.pack("<BfI", int(modo), float(escalar), int(duracao_ms)))
        )

    def velocidade_atual(self) -> Velocidade:
        corpo = self.pedir(p.comando(p.Codigo.EXT_GET_SPEED))
        modo, alvo, restante = struct.unpack_from("<BfI", corpo, 0)
        return Velocidade(p.ModoVelocidade(modo), float(alvo), int(restante))

    # ---------- camada de cena (prova S7-00; códigos 0x84 a 0x88) ----------
    def cena_lista(self) -> tuple[int, list[Assinatura]]:
        """(número do quadro, assinaturas do último quadro)."""
        corpo = self.pedir(p.comando(p.Codigo.EXT_SCENE_LIST))
        quadro, n = struct.unpack_from("<II", corpo, 0)
        itens = []
        for i in range(n):
            h, hf, nv, x0, y0, x1, y1, zmin, zmax, fb, q, _ = struct.unpack_from(
                "<QQIhhhhIIBBH", corpo, 8 + i * 40
            )
            itens.append(Assinatura(h, hf, nv, x0, y0, x1, y1, zmin, zmax, bool(fb), bool(q)))
        return int(quadro), itens

    def cena_regra(
        self,
        tipo: int,
        hash_textura: int = 0,
        hash_forma: int = 0,
        retangulo: tuple[int, int, int, int] = (0, 0, 0, 0),
        z: int = 0,
        rgba: int = 0xFFFF00FF,
        duracao_ms: int = 0,
        apos_n: int = 1,
    ) -> int:
        """Grava uma regra (esconder ou quadrado injetado) com prazo; devolve o id."""
        x0, y0, x1, y1 = retangulo
        corpo = self.pedir(
            p.comando(
                p.Codigo.EXT_SCENE_RULE,
                struct.pack(
                    "<BQQhhhhIIII",
                    tipo,
                    hash_textura,
                    hash_forma,
                    x0,
                    y0,
                    x1,
                    y1,
                    z,
                    rgba,
                    duracao_ms,
                    apos_n,
                ),
            )
        )
        return int(struct.unpack_from("<I", corpo, 0)[0])

    def cena_limpar(self, id_regra: int = 0) -> None:
        self.pedir(p.comando(p.Codigo.EXT_SCENE_CLEAR, struct.pack("<I", id_regra)))

    def cena_estatisticas(self, id_regra: int = 0) -> EstatisticasCena:
        corpo = self.pedir(p.comando(p.Codigo.EXT_SCENE_STATS, struct.pack("<I", id_regra)))
        campos = struct.unpack_from("<IIIIIQQIII", corpo, 0)
        return EstatisticasCena(bool(campos[0]), *campos[1:])

    # ---------- vigia de memória (card S8-01; códigos 0x89 a 0x8B) ----------
    def vigia_definir(
        self, inicio: int, fim: int, condicao: int = VIGIA_ESCRITA, duracao_ms: int = 0
    ) -> None:
        """Vigia a faixa [inicio, fim) sem pausar o jogo; o emulador fica mais lento enquanto o vigia existe."""
        self.pedir(p.comando(p.Codigo.EXT_WATCH_SET, struct.pack("<IIBI", inicio, fim, condicao, duracao_ms)))

    def vigia_ler(self, zerar: bool = False) -> tuple[EstadoVigia, list[AcessoVigiado]]:
        corpo = self.pedir(p.comando(p.Codigo.EXT_WATCH_READ, bytes([1 if zerar else 0])))
        ativo, inicio, fim, total, descartados, instrucoes, restante, n = struct.unpack_from(
            "<IIIIIIII", corpo, 0
        )
        itens = []
        for i in range(n):
            base = 32 + i * 160
            pc, op, e0, e1, cont, bits, escrita, _pad, valor = struct.unpack_from("<IIIIIBBHQ", corpo, base)
            regs = struct.unpack_from("<32I", corpo, base + 32)
            itens.append(AcessoVigiado(pc, op, e0, e1, cont, bits, bool(escrita), valor, tuple(regs)))
        return EstadoVigia(bool(ativo), inicio, fim, total, descartados, instrucoes, restante), itens

    def vigia_limpar(self) -> None:
        self.pedir(p.comando(p.Codigo.EXT_WATCH_CLEAR))

    # ---------- chamada remota (card S8-02; código 0x8C) ----------
    def chamar(
        self, funcao: int, argumentos: tuple[int, ...] = (), tempo_limite_ms: int = 2000
    ) -> ResultadoChamada:
        """Executa uma função do jogo no processador emulado, com até 4 argumentos inteiros, e devolve v0 e v1.
        O jogo fica parado só durante a chamada; o emulador restaura os registradores ao fim ou no prazo."""
        if len(argumentos) > 4:
            raise ValueError("a chamada remota aceita até 4 argumentos")
        args = tuple(a & 0xFFFFFFFF for a in argumentos) + (0,) * (4 - len(argumentos))
        corpo = self.pedir(
            p.comando(
                p.Codigo.EXT_CALL, struct.pack("<IB4II", funcao, len(argumentos), *args, tempo_limite_ms)
            )
        )
        estado, v0, v1, duracao = struct.unpack_from("<BIII", corpo, 0)
        return ResultadoChamada(ESTADOS_CHAMADA.get(estado, "recusada"), v0, v1, duracao)

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
