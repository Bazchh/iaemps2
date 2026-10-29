"""Simulador do canal do emulador (card S0-03): um servidor falso que fala o protocolo do PINE.

Dois modos: "original", só os 16 códigos do canal oficial, como o emulador que o jogador baixa; e
"proprio", com os quatro códigos da extensão (0x80 a 0x83) e o vigia de velocidade. Um jogo de
mentira por trás: título, serial, soma, status, 32 MB de memória zerada e slots que gravam arquivo
com atraso, como o emulador de verdade. Cenários de falha ligados por nome.

O núcleo é `processar(pedido) -> resposta`, puro, igual ao ParseCommand do emulador; o servidor TCP
só embrulha isso. Os testes usam o núcleo direto e o servidor pela porta efêmera.
"""

from __future__ import annotations

import contextlib
import socket
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iaemps2.ponte import protocolo as p

VERSAO_SIMULADA = "PCSX2 v2.8.2-sim"
# Cena de mentira da camada de cena (fase 4): (hash textura, hash forma, vértices, x0, y0, x1, y1, z_min, z_max,
# fallback, qualifica). Dois pedaços do mesmo material, um objeto sem hash e a interface.
CENA_DE_MENTIRA: tuple[tuple[int, int, int, int, int, int, int, int, int, int, int], ...] = (
    (0x1111, 0xAAAA, 64, 100, 100, 200, 180, 20_000, 30_000, 0, 1),
    (0x1111, 0xBBBB, 64, 210, 100, 300, 180, 20_000, 30_000, 0, 1),
    (0xF000_0000_0000_0001, 0xCCCC, 2, 0, 0, 512, 448, 0, 0, 1, 0),
    (0x2222, 0xDDDD, 12, 400, 380, 500, 440, 700_000, 700_000, 0, 1),
)

MEMORIA_EE = 32 * 1024 * 1024

CENARIOS = (
    "canal_cai",  # fecha a conexão depois de N comandos
    "status_trava",  # o comando de status demora além do tempo limite do cliente
    "salvamento_nunca_aparece",  # salvar responde OK mas o arquivo nunca é gravado
    "troca_serial",  # depois de N consultas de status, o jogo em execução muda
    "carregando",  # nos primeiros segundos, status "desligado" e comandos do jogo falham
)


@dataclass
class Jogo:
    titulo: str = "Resident Evil 4"
    serial: str = "SLUS-21134"
    crc: int = 0x013E349D
    versao: str = "1.01"
    status: p.Status = p.Status.RODANDO
    memoria: bytearray = field(default_factory=lambda: bytearray(MEMORIA_EE))


@dataclass
class Velocidade:
    modo: p.ModoVelocidade = p.ModoVelocidade.NORMAL
    escalar_lenta: float = 0.5
    escalar_turbo: float = 2.0
    prazo: float | None = None  # instante (relógio injetado) em que o vigia volta a normal

    def alvo(self) -> float:
        if self.modo == p.ModoVelocidade.LENTA:
            return self.escalar_lenta
        if self.modo == p.ModoVelocidade.TURBO:
            return self.escalar_turbo
        return 1.0


class Simulador:
    def __init__(
        self,
        modo: str = "original",
        pasta_estados: Path | None = None,
        atraso_salvamento_s: float = 0.9,
        relogio: Callable[[], float] = time.monotonic,
        atraso_aplicacao_s: float = 0.0,
        cenarios: dict[str, int | float] | None = None,
    ) -> None:
        if modo not in ("original", "proprio"):
            raise ValueError("modo: original ou proprio")
        self.modo = modo
        self.pasta_estados = pasta_estados
        self.atraso_salvamento_s = atraso_salvamento_s
        self.atraso_aplicacao_s = atraso_aplicacao_s  # pausa e velocidade entram em vigor depois da resposta
        self._aplicacoes_pendentes: list[tuple[float, Callable[[], None]]] = []
        self.relogio = relogio
        self.cenarios = dict(cenarios or {})
        for nome in self.cenarios:
            if nome not in CENARIOS:
                raise ValueError(f"cenário desconhecido: {nome}")
        self.jogo = Jogo()
        self.velocidade = Velocidade()
        self.cena_quadro = 0
        self.cena_proximo_id = 0
        self.cena_regras: dict[int, dict[str, Any]] = {}
        self.vigia_memoria: dict[str, Any] | None = None  # faixa vigiada e tabela de acessos por pc
        # chamadas remotas recebidas: (função, args, prazo ms, âncora)
        self.chamadas: list[tuple[int, tuple[int, ...], int, int]] = []
        self.resposta_chamada: tuple[int, int, int] = (
            0,
            0,
            0,
        )  # (estado, v0, v1) devolvidos à próxima chamada
        self.comandos_atendidos = 0
        self.consultas_status = 0
        self.inicio = relogio()
        self._trava = threading.Lock()
        self._servidor: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._conexoes: list[socket.socket] = []  # parar() derruba todas, como um emulador que morre
        self.porta: int | None = None

    # ---------------- núcleo puro ----------------
    def _vm_valida(self) -> bool:
        if "carregando" in self.cenarios and self.relogio() - self.inicio < float(
            self.cenarios["carregando"]
        ):
            return False
        return self.jogo.status != p.Status.DESLIGADO

    def _status_atual(self) -> p.Status:
        if not self._vm_valida():
            return p.Status.DESLIGADO
        return self.jogo.status

    def vigiar(self) -> None:
        """Aplica o que já venceu o atraso e volta a velocidade a normal quando o prazo vence.
        O servidor chama a cada volta do laço e antes de cada pedido."""
        agora = self.relogio()
        prontas = [a for a in self._aplicacoes_pendentes if a[0] <= agora]
        self._aplicacoes_pendentes = [a for a in self._aplicacoes_pendentes if a[0] > agora]
        for _, aplicar in prontas:
            aplicar()
        v = self.velocidade
        if v.prazo is not None and self.relogio() >= v.prazo:
            v.modo = p.ModoVelocidade.NORMAL
            v.prazo = None

    def processar(self, pedido: bytes) -> bytes:
        """Igual ao ParseCommand do emulador: percorre os comandos do pedido; qualquer falha falha o pedido."""
        with self._trava:
            self.vigiar()
            if len(pedido) < 4:
                return p.empacotar_resposta(p.Resultado.FALHA)
            (tamanho,) = struct.unpack_from("<I", pedido, 0)
            if tamanho != len(pedido) or tamanho > p.TAMANHO_MAXIMO_PEDIDO:
                return p.empacotar_resposta(p.Resultado.FALHA)
            retorno = bytearray()
            i = 4
            try:
                while i < tamanho:
                    codigo = pedido[i]
                    i += 1
                    i = self._comando(codigo, pedido, i, retorno)
                    self.comandos_atendidos += 1
            except _FalhaError:
                return p.empacotar_resposta(p.Resultado.FALHA)
            if 5 + len(retorno) >= p.TAMANHO_MAXIMO_RESPOSTA:
                return p.empacotar_resposta(p.Resultado.FALHA)
            return p.empacotar_resposta(p.Resultado.OK, bytes(retorno))

    def _comando(self, codigo: int, buf: bytes, i: int, ret: bytearray) -> int:
        c = p.Codigo(codigo) if codigo in p.Codigo._value2member_map_ else None
        if c is None or (c >= 0x80 and self.modo != "proprio"):
            raise _FalhaError  # MsgUnimplemented: o emulador original cai no caso padrão
        if c in p.TAMANHO_LEITURA:
            self._exige_vm()
            (endereco,) = struct.unpack_from("<I", buf, i)
            n = p.TAMANHO_LEITURA[c]
            ret += self._ler(endereco, n)
            return i + 4
        if c in p.TAMANHO_ESCRITA:
            self._exige_vm()
            (endereco,) = struct.unpack_from("<I", buf, i)
            n = p.TAMANHO_ESCRITA[c]
            self._escrever(endereco, buf[i + 4 : i + 4 + n])
            return i + 4 + n
        if c == p.Codigo.VERSION:
            ret += p.texto(VERSAO_SIMULADA)
            return i
        if c == p.Codigo.SAVE_STATE:
            self._exige_vm()
            self._salvar_estado(buf[i])
            return i + 1
        if c == p.Codigo.LOAD_STATE:
            self._exige_vm()
            self._carregar_estado(buf[i])
            return i + 1
        if c == p.Codigo.TITLE:
            self._exige_vm()
            ret += p.texto(self.jogo.titulo)
            return i
        if c == p.Codigo.ID:
            self._exige_vm()
            ret += p.texto(self.jogo.serial)
            return i
        if c == p.Codigo.UUID:
            self._exige_vm()
            ret += p.texto(f"{self.jogo.crc:08x}")
            return i
        if c == p.Codigo.GAME_VERSION:
            self._exige_vm()
            ret += p.texto(self.jogo.versao)
            return i
        if c == p.Codigo.STATUS:
            self.consultas_status += 1
            limite = self.cenarios.get("troca_serial")
            if limite is not None and self.consultas_status > int(limite):
                self.jogo.titulo, self.jogo.serial, self.jogo.crc = "Outro Jogo", "SLUS-99999", 0xDEADBEEF
            ret += struct.pack("<I", int(self._status_atual()))
            return i
        # ---- extensão ----
        if c == p.Codigo.EXT_CAPABILITIES:
            ret += struct.pack(
                "<HI",
                p.VERSAO_EXTENSAO,
                p.CAP_PAUSA | p.CAP_VELOCIDADE | p.CAP_CENA | p.CAP_VIGIA | p.CAP_CHAMADA,
            )
            return i
        if c == p.Codigo.EXT_SCENE_LIST:
            self.cena_quadro += 1
            self._cena_avancar_quadro()
            ret += struct.pack("<II", self.cena_quadro, len(CENA_DE_MENTIRA))
            for h, hf, nv, x0, y0, x1, y1, zmin, zmax, fb, q in CENA_DE_MENTIRA:
                ret += struct.pack("<QQIhhhhIIBBH", h, hf, nv, x0, y0, x1, y1, zmin, zmax, fb, q, 0)
            return i
        if c == p.Codigo.EXT_SCENE_RULE:
            tipo, h, hf, _x0, _y0, _x1, _y1, _z, _rgba, duracao_ms, _apos_n = struct.unpack_from(
                "<BQQhhhhIIII", buf, i
            )
            if tipo not in (1, 2):
                raise _FalhaError
            self.cena_proximo_id += 1
            prazo = self.relogio() + duracao_ms / 1000 if duracao_ms > 0 else None
            self.cena_regras[self.cena_proximo_id] = {
                "tipo": tipo,
                "hash": h,
                "forma": hf,
                "prazo": prazo,
                "total": 0,
                "aplicada": 0,
            }
            ret += struct.pack("<I", self.cena_proximo_id)
            return i + 41
        if c == p.Codigo.EXT_SCENE_CLEAR:
            (id_regra,) = struct.unpack_from("<I", buf, i)
            if id_regra == 0:
                self.cena_regras.clear()
            else:
                self.cena_regras.pop(id_regra, None)
            return i + 4
        if c == p.Codigo.EXT_SCENE_STATS:
            (id_regra,) = struct.unpack_from("<I", buf, i)
            r = self.cena_regras.get(id_regra)
            ret += struct.pack(
                "<IIIIIQQIII",
                1 if r else 0,
                r["total"] if r else 0,
                r["aplicada"] if r else 0,
                r["aplicada"] if r else 0,
                self.cena_quadro,
                self.cena_quadro * 25_000,
                25_000,
                len(CENA_DE_MENTIRA),
                sum(1 for a in CENA_DE_MENTIRA if a[10]),
                sum(1 for a in CENA_DE_MENTIRA if not a[9]),
            )
            return i + 4
        if c == p.Codigo.EXT_WATCH_SET:
            self._exige_vm()
            inicio, fim, cond, duracao_ms = struct.unpack_from("<IIBI", buf, i)
            if inicio >= fim or (cond & 3) == 0:
                raise _FalhaError
            prazo = self.relogio() + duracao_ms / 1000 if duracao_ms > 0 else None
            self.vigia_memoria = {
                "inicio": inicio,
                "fim": fim,
                "cond": cond,
                "prazo": prazo,
                "total": 0,
                "tabela": {},
            }
            return i + 13
        if c == p.Codigo.EXT_WATCH_READ:
            zerar = buf[i] != 0
            self._vigia_prazo()
            vg = self.vigia_memoria
            tabela = vg["tabela"] if vg else {}
            restante = 0
            if vg and vg["prazo"] is not None:
                restante = max(0, int((vg["prazo"] - self.relogio()) * 1000))
            ret += struct.pack(
                "<IIIIIIII",
                1 if vg else 0,
                vg["inicio"] if vg else 0,
                vg["fim"] if vg else 0,
                vg["total"] if vg else 0,
                0,
                len(tabela),
                restante,
                len(tabela),
            )
            for pc, e in tabela.items():
                ret += struct.pack(
                    "<IIIIIBBHQ", pc, e["op"], e["e0"], e["e1"], e["n"], e["bits"], 1, 0, e["valor"]
                )
                ret += struct.pack("<32I", *e["regs"])
            if zerar and vg:
                vg["tabela"] = {}
                vg["total"] = 0
            return i + 1
        if c == p.Codigo.EXT_WATCH_CLEAR:
            self.vigia_memoria = None
            return i
        if c == p.Codigo.EXT_CALL:
            # o simulador não executa código do jogo: registra a chamada e devolve a resposta configurada;
            # com o jogo parado recusa (estado 2), como o emulador
            funcao, n, a0, a1, a2, a3, prazo_ms, ancora, ancora_end = struct.unpack_from("<IB4IIII", buf, i)
            if n > 4:
                raise _FalhaError
            estado, v0, v1 = self.resposta_chamada
            if not self._vm_valida() or self._status_atual() != p.Status.RODANDO:
                estado, v0, v1 = 2, 0, 0
            else:
                self.chamadas.append((funcao, (a0, a1, a2, a3)[:n], prazo_ms, ancora or ancora_end))
            ret += struct.pack("<BIII", estado, v0, v1, 1 if estado == 0 else 0)
            return i + 33
        if c == p.Codigo.EXT_SET_PAUSED:
            self._exige_vm()
            novo = p.Status.PAUSADO if buf[i] else p.Status.RODANDO

            def pausar(novo: p.Status = novo) -> None:
                self.jogo.status = novo

            self._aplicar(pausar)
            return i + 1
        if c == p.Codigo.EXT_SET_SPEED:
            self._exige_vm()
            modo, escalar, duracao_ms = struct.unpack_from("<BfI", buf, i)
            if modo > p.ModoVelocidade.TURBO or (modo != p.ModoVelocidade.NORMAL and not escalar > 0.0):
                raise _FalhaError  # como o emulador próprio: escalar 0 significaria ilimitado
            self._aplicar(lambda: self._definir_velocidade(modo, escalar, duracao_ms))
            return i + 9
        if c == p.Codigo.EXT_GET_SPEED:
            v = self.velocidade
            restante = 0 if v.prazo is None else max(0, int((v.prazo - self.relogio()) * 1000))
            ret += struct.pack("<BfI", int(v.modo), v.alvo(), restante)
            return i
        raise _FalhaError

    def _aplicar(self, aplicar: Callable[[], None]) -> None:
        """Agora, ou depois do atraso de aplicação (o emulador real responde antes de a thread da CPU agir)."""
        if self.atraso_aplicacao_s <= 0:
            aplicar()
        else:
            self._aplicacoes_pendentes.append((self.relogio() + self.atraso_aplicacao_s, aplicar))

    def _exige_vm(self) -> None:
        if not self._vm_valida():
            raise _FalhaError

    def _ler(self, endereco: int, n: int) -> bytes:
        if endereco + n > MEMORIA_EE:
            raise _FalhaError
        return bytes(self.jogo.memoria[endereco : endereco + n])

    def _vigia_prazo(self) -> None:
        v = self.vigia_memoria
        if v and v["prazo"] is not None and self.relogio() >= v["prazo"]:
            self.vigia_memoria = None

    def _vigia_registrar(self, endereco: int, dados: bytes) -> None:
        """Escrita pelo canal dentro da faixa vigiada conta como um acesso de uma instrução de mentira."""
        self._vigia_prazo()
        v = self.vigia_memoria
        if not v or not (v["cond"] & 2) or endereco >= v["fim"] or endereco + len(dados) <= v["inicio"]:
            return
        v["total"] += 1
        bits = len(dados) * 8
        pc = 0x00100000 + (endereco - v["inicio"])  # uma instrução por endereço, estável entre leituras
        op = (0x2B << 26) | (4 << 21) | (5 << 16) | (endereco & 0xFFFF)  # sw t1, desl(a0)
        valor = int.from_bytes(dados, "little")
        e = v["tabela"].get(pc)
        if e is None:
            regs = [0] * 32
            regs[4] = endereco - (endereco & 0xFFFF)
            v["tabela"][pc] = {
                "op": op,
                "e0": endereco,
                "e1": endereco,
                "n": 1,
                "bits": bits,
                "valor": valor,
                "regs": regs,
            }
        else:
            e["e1"] = endereco
            e["n"] += 1
            e["valor"] = valor

    def _escrever(self, endereco: int, dados: bytes) -> None:
        self._vigia_registrar(endereco, dados)
        if endereco + len(dados) > MEMORIA_EE:
            raise _FalhaError
        self.jogo.memoria[endereco : endereco + len(dados)] = dados

    def arquivo_estado(self, slot: int) -> Path | None:
        if self.pasta_estados is None:
            return None
        return self.pasta_estados / f"{self.jogo.serial} ({self.jogo.crc:08X}).{slot:02d}.p2s"

    def _salvar_estado(self, slot: int) -> None:
        """Como no emulador: responde OK na hora e grava depois, em duas etapas, sem avisar erro pelo canal."""
        if "salvamento_nunca_aparece" in self.cenarios:
            return
        caminho = self.arquivo_estado(slot)
        if caminho is None:
            return

        def gravar() -> None:
            # como o emulador ao comprimir: o arquivo aparece pequeno e cresce em pedaços até o fim
            time.sleep(self.atraso_salvamento_s / 3)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            pedacos = 16
            pausa = (self.atraso_salvamento_s * 2 / 3) / pedacos
            with caminho.open("wb") as arquivo:
                for _ in range(pedacos):
                    arquivo.write(b"P2S-SIM-COMPLETO" * 250)
                    arquivo.flush()
                    time.sleep(pausa)

        threading.Thread(target=gravar, daemon=True).start()

    def _carregar_estado(self, slot: int) -> None:
        """Slot vazio: o emulador mostra erro na própria tela e o canal responde OK. Igual aqui."""
        caminho = self.arquivo_estado(slot)
        if caminho is not None and caminho.is_file():
            self.jogo.status = p.Status.RODANDO

    def _cena_avancar_quadro(self) -> None:
        """Um quadro passou: regras vencidas somem; as de esconder que casam com a cena contam como aplicadas."""
        agora = self.relogio()
        for id_regra in [
            k for k, r in self.cena_regras.items() if r["prazo"] is not None and agora >= r["prazo"]
        ]:
            del self.cena_regras[id_regra]
        for r in self.cena_regras.values():
            r["total"] += 1
            casa = any(a[0] == r["hash"] and (r["forma"] == 0 or a[1] == r["forma"]) for a in CENA_DE_MENTIRA)
            if r["tipo"] == 2 or casa:
                r["aplicada"] += 1

    def _definir_velocidade(self, modo: int, escalar: float, duracao_ms: int) -> None:
        v = self.velocidade
        if modo == p.ModoVelocidade.NORMAL:
            v.modo, v.prazo = p.ModoVelocidade.NORMAL, None
            return
        if modo == p.ModoVelocidade.LENTA:
            v.escalar_lenta = escalar
        elif modo == p.ModoVelocidade.TURBO:
            v.escalar_turbo = escalar
        else:
            raise _FalhaError
        v.modo = p.ModoVelocidade(modo)
        v.prazo = self.relogio() + duracao_ms / 1000 if duracao_ms > 0 else None

    # ---------------- servidor TCP ----------------
    def iniciar(self, porta: int = 0) -> int:
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("127.0.0.1", porta))
        servidor.listen(4)
        servidor.settimeout(0.2)
        self._servidor = servidor
        self.porta = int(servidor.getsockname()[1])
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, daemon=True)
        self._thread.start()
        return self.porta

    def parar(self) -> None:
        self._parar.set()
        if self._servidor is not None:
            self._servidor.close()
        for conexao in list(self._conexoes):
            with contextlib.suppress(OSError):
                conexao.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                conexao.close()
        self._conexoes.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> Simulador:
        self.iniciar()
        return self

    def __exit__(self, *_: object) -> None:
        self.parar()

    def _laco(self) -> None:
        assert self._servidor is not None
        while not self._parar.is_set():
            try:
                cliente, _ = self._servidor.accept()
            except TimeoutError:
                self.vigiar()
                continue
            except OSError:
                break
            self._conexoes.append(cliente)
            threading.Thread(target=self._atender, args=(cliente,), daemon=True).start()

    def _atender(self, cliente: socket.socket) -> None:
        with cliente:
            cliente.settimeout(0.5)
            comandos_nesta_conexao = 0
            while not self._parar.is_set():
                try:
                    cabecalho = _ler_exato(cliente, 4)
                except TimeoutError:
                    continue
                except OSError:
                    return
                if not cabecalho:
                    return
                (tamanho,) = struct.unpack("<I", cabecalho)
                try:
                    corpo = _ler_exato(cliente, tamanho - 4)
                except OSError:
                    return
                pedido = cabecalho + corpo
                if pedido[4:5] == bytes([p.Codigo.STATUS]) and "status_trava" in self.cenarios:
                    time.sleep(float(self.cenarios["status_trava"]))
                limite = self.cenarios.get("canal_cai")
                if limite is not None and comandos_nesta_conexao >= int(limite):
                    return  # fecha a conexão sem responder: canal caído
                comandos_nesta_conexao += 1
                try:
                    cliente.sendall(self.processar(pedido))
                except OSError:
                    return


class _FalhaError(Exception):
    pass


def _ler_exato(sock: socket.socket, n: int) -> bytes:
    dados = bytearray()
    while len(dados) < n:
        pedaco = sock.recv(n - len(dados))
        if not pedaco:
            return bytes(dados)
        dados += pedaco
    return bytes(dados)
