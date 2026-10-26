"""Captura pela janela com recorte (card S2-01; caso B01).

Pega o jogo e só o jogo, mesmo com outra janela por cima: localiza a janela do emulador pelo processo,
captura o conteúdo completo da janela pela API do sistema e recorta a área do cliente (sem a barra de menu),
e depois a área do overlay, se ela estiver dentro. Reduz para a largura configurada e comprime em JPEG.

A parte que depende do Windows fica em funções próprias e é importada tarde, para o restante do pacote
rodar e ser testado em qualquer sistema. O que não depende de janela, recortar, reduzir, comprimir e
assinar, é puro e testado com imagens sintéticas.
"""

from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

PROCESSO_EMULADOR = "pcsx2-qt.exe"


class JanelaAusenteError(RuntimeError):
    """Emulador fechado, minimizado ou sem janela visível: ciclo sem captura (B01 E1)."""


@dataclass(frozen=True)
class Retangulo:
    esquerda: int
    topo: int
    direita: int
    fundo: int

    @property
    def largura(self) -> int:
        return self.direita - self.esquerda

    @property
    def altura(self) -> int:
        return self.fundo - self.topo

    def intersecao(self, outro: Retangulo) -> Retangulo | None:
        e, t = max(self.esquerda, outro.esquerda), max(self.topo, outro.topo)
        d, f = min(self.direita, outro.direita), min(self.fundo, outro.fundo)
        if d <= e or f <= t:
            return None
        return Retangulo(e, t, d, f)


@dataclass(frozen=True)
class Captura:
    jpeg: bytes
    largura: int
    altura: int
    digest: str
    duracao_ms: int
    origem: Retangulo  # área do cliente, em coordenadas de tela

    @property
    def bytes(self) -> int:
        return len(self.jpeg)


# ---------------- parte pura ----------------


def recortar_overlay(imagem: Image.Image, area: Retangulo, overlay: Retangulo | None) -> Image.Image:
    """Apaga (preenche de preto) a parte do overlay que cai dentro da área capturada, para o serviço
    nunca ler as palavras do próprio mestre como parte do jogo (B01 E3)."""
    if overlay is None:
        return imagem
    dentro = area.intersecao(overlay)
    if dentro is None:
        return imagem
    caixa = (
        dentro.esquerda - area.esquerda,
        dentro.topo - area.topo,
        dentro.direita - area.esquerda,
        dentro.fundo - area.topo,
    )
    saida = imagem.copy()
    saida.paste((0, 0, 0), caixa)
    return saida


def reduzir(imagem: Image.Image, largura_px: int) -> Image.Image:
    if imagem.width <= largura_px:
        return imagem
    altura = max(1, round(imagem.height * largura_px / imagem.width))
    return imagem.resize((largura_px, altura), Image.Resampling.BILINEAR)


def comprimir(imagem: Image.Image, qualidade: int) -> bytes:
    saida = io.BytesIO()
    imagem.convert("RGB").save(saida, "JPEG", quality=qualidade, optimize=True)
    return saida.getvalue()


def assinar(imagem: Image.Image) -> str:
    """Impressão digital da imagem reduzida em cinza e miúda: igual para capturas iguais, barata."""
    miuda = imagem.convert("L").resize((64, 36), Image.Resampling.BILINEAR)
    return hashlib.sha1(miuda.tobytes()).hexdigest()[:16]


def preparar(
    imagem: Image.Image,
    area: Retangulo,
    largura_px: int,
    qualidade: int,
    overlay: Retangulo | None = None,
    duracao_ms: int = 0,
) -> Captura:
    """O caminho puro: recortar overlay, reduzir, assinar, comprimir."""
    sem_overlay = recortar_overlay(imagem, area, overlay)
    pequena = reduzir(sem_overlay, largura_px)
    return Captura(
        jpeg=comprimir(pequena, qualidade),
        largura=pequena.width,
        altura=pequena.height,
        digest=assinar(pequena),
        duracao_ms=duracao_ms,
        origem=area,
    )


# ---------------- parte do Windows ----------------


def localizar_janela(processo: str = PROCESSO_EMULADOR) -> tuple[int, Retangulo]:
    """A maior janela visível do processo do emulador, e a área do cliente dela em coordenadas de tela.
    Pelo processo, não pelo título: o título muda com o jogo."""
    import psutil
    import win32gui
    import win32process

    pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == processo}
    if not pids:
        raise JanelaAusenteError(f"processo {processo} não está rodando")
    candidatas: list[tuple[int, int]] = []

    def visitar(h: int, _: object) -> None:
        if not win32gui.IsWindowVisible(h) or win32gui.IsIconic(h):
            return
        _, pid = win32process.GetWindowThreadProcessId(h)
        if pid in pids:
            e, t, d, f = win32gui.GetWindowRect(h)
            candidatas.append(((d - e) * (f - t), h))

    win32gui.EnumWindows(visitar, None)
    if not candidatas:
        raise JanelaAusenteError(f"{processo} está rodando mas sem janela visível (minimizado?)")
    _, hwnd = max(candidatas)
    ce, ct, cd, cf = win32gui.GetClientRect(hwnd)
    x0, y0 = win32gui.ClientToScreen(hwnd, (ce, ct))
    x1, y1 = win32gui.ClientToScreen(hwnd, (cd, cf))
    if x1 - x0 < 64 or y1 - y0 < 64:
        raise JanelaAusenteError("a janela do emulador está pequena demais para capturar")
    return hwnd, Retangulo(x0, y0, x1, y1)


def capturar_janela(hwnd: int, area: Retangulo) -> Image.Image:
    """Conteúdo completo da janela pela API do sistema (funciona coberta e com D3D12), recortado na área
    do cliente. A captura é da janela inteira; o deslocamento é o da área do cliente dentro dela."""
    import ctypes

    import win32gui
    import win32ui

    je, jt, jd, jf = win32gui.GetWindowRect(hwnd)
    largura, altura = jd - je, jf - jt
    hdc = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(hdc)
    mem = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(mfc, largura, altura)
        mem.SelectObject(bmp)
        ok = ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 3)  # 3 = PW_RENDERFULLCONTENT
        if not ok:
            raise JanelaAusenteError("a janela do emulador não aceitou a captura")
        info = bmp.GetInfo()
        inteira = Image.frombuffer(
            "RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1
        )
    finally:
        mem.DeleteDC()
        mfc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)
        win32gui.DeleteObject(bmp.GetHandle())
    caixa = (area.esquerda - je, area.topo - jt, area.direita - je, area.fundo - jt)
    return inteira.crop(caixa)


def area_do_cliente(hwnd: int) -> Retangulo | None:
    """A área do cliente de uma janela já conhecida, ou None se ela sumiu ou foi minimizada."""
    import win32gui

    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return None
    ce, ct, cd, cf = win32gui.GetClientRect(hwnd)
    x0, y0 = win32gui.ClientToScreen(hwnd, (ce, ct))
    x1, y1 = win32gui.ClientToScreen(hwnd, (cd, cf))
    if x1 - x0 < 64 or y1 - y0 < 64:
        return None
    return Retangulo(x0, y0, x1, y1)


class Capturador:
    """O caso B01 inteiro, guardando a janela entre capturas: procurar o processo e enumerar janelas é o
    que custa (perto de 100 ms); com a janela guardada, cada captura fica em dezenas de milissegundos."""

    def __init__(
        self,
        largura_px: int = 640,
        qualidade: int = 80,
        processo: str = PROCESSO_EMULADOR,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.largura_px = largura_px
        self.qualidade = qualidade
        self.processo = processo
        self.relogio = relogio
        self._hwnd: int | None = None

    def capturar(self, overlay: Retangulo | None = None) -> Captura:
        inicio = self.relogio()
        hwnd = self._hwnd
        area = area_do_cliente(hwnd) if hwnd is not None else None
        if hwnd is None or area is None:
            hwnd, area = localizar_janela(self.processo)
            self._hwnd = hwnd
        try:
            imagem = capturar_janela(hwnd, area)
        except JanelaAusenteError:
            self._hwnd = None
            raise
        duracao = int((self.relogio() - inicio) * 1000)
        return preparar(imagem, area, self.largura_px, self.qualidade, overlay, duracao)


def capturar(largura_px: int = 640, qualidade: int = 80, overlay: Retangulo | None = None) -> Captura:
    """Uma captura avulsa, sem guardar a janela. Para o ciclo, use Capturador."""
    return Capturador(largura_px, qualidade).capturar(overlay)
