"""Card S2-01: captura pela janela com recorte.

Critério de aceite: dado o jogo com outra janela por cima, quando o olho captura, então a imagem mostra o jogo
sem barra de menu e sem o overlay, com até 80 KB, em menos de 100 ms. A parte pura é provada com imagens
sintéticas; a parte da janela, contra o emulador real, no teste marcado.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from iaemps2.olho import captura as cap


def _cena(largura: int = 1050, altura: int = 666) -> Image.Image:
    """Uma 'cena' com gradiente, para a redução e a assinatura terem o que ver."""
    img = Image.new("RGB", (largura, altura))
    px = img.load()
    assert px is not None
    for y in range(altura):
        for x in range(0, largura, 1):
            px[x, y] = ((x * 255) // largura, (y * 255) // altura, 128)
    return img


AREA = cap.Retangulo(243, 75, 1293, 741)


def test_preparar_reduz_comprime_e_assina() -> None:
    c = cap.preparar(_cena(), AREA, largura_px=640, qualidade=80)
    assert c.largura == 640 and c.altura == 406
    assert 0 < c.bytes <= 80_000
    assert len(c.digest) == 16 and c.origem == AREA
    decodificada = Image.open(io.BytesIO(c.jpeg))
    assert decodificada.size == (640, 406) and decodificada.format == "JPEG"


def test_imagem_menor_que_a_largura_nao_e_ampliada() -> None:
    c = cap.preparar(_cena(320, 200), AREA, largura_px=640, qualidade=80)
    assert (c.largura, c.altura) == (320, 200)


def test_overlay_dentro_da_area_e_apagado() -> None:
    cena = _cena()
    overlay = cap.Retangulo(AREA.esquerda + 10, AREA.topo + 10, AREA.esquerda + 330, AREA.topo + 290)
    sem = cap.recortar_overlay(cena, AREA, overlay)
    assert sem.getpixel((20, 20)) == (0, 0, 0)  # dentro do overlay: apagado
    assert sem.getpixel((400, 400)) != (0, 0, 0)  # fora: a cena
    assert cena.getpixel((20, 20)) != (0, 0, 0)  # a original não foi alterada


def test_overlay_fora_da_area_nao_toca_a_imagem() -> None:
    cena = _cena()
    overlay = cap.Retangulo(0, 0, 200, 60)  # acima e à esquerda da área do jogo
    assert cap.recortar_overlay(cena, AREA, overlay) is cena


def test_assinatura_e_estavel_e_sensivel() -> None:
    a, b = _cena(), _cena()
    assert cap.assinar(a) == cap.assinar(b)
    b.paste((255, 255, 255), (0, 0, 500, 300))
    assert cap.assinar(a) != cap.assinar(b)


def test_intersecao() -> None:
    r = cap.Retangulo(0, 0, 10, 10)
    assert r.intersecao(cap.Retangulo(5, 5, 20, 20)) == cap.Retangulo(5, 5, 10, 10)
    assert r.intersecao(cap.Retangulo(10, 10, 20, 20)) is None


@pytest.mark.emulador
def test_emulador_real_captura_o_jogo_sem_menu() -> None:
    import win32gui

    hwnd, area = cap.localizar_janela()
    _, jt, _, _ = win32gui.GetWindowRect(hwnd)
    assert area.topo > jt  # a área do cliente começa abaixo da barra de título e do menu
    capturador = cap.Capturador(largura_px=640, qualidade=80)
    primeira = capturador.capturar()  # paga a localização da janela
    c = capturador.capturar()  # o ciclo normal: janela guardada
    assert c.largura == 640 and c.bytes <= 80_000 and c.duracao_ms < 100, (c.bytes, c.duracao_ms)
    assert primeira.digest == c.digest or primeira.bytes > 0
    img = Image.open(io.BytesIO(c.jpeg)).convert("L")
    # sem a barra de menu clara no topo: a primeira linha não é cinza de menu
    topo = [img.getpixel((x, 1)) for x in range(0, 640, 40)]
    assert not all(isinstance(v, int) and 200 < v < 256 for v in topo)


def test_nome_do_processo_do_emulador_por_prefixo() -> None:
    # o instalado e o compilado são o mesmo emulador; outro programa com prefixo parecido não é
    assert cap.e_o_emulador("pcsx2-qt.exe")
    assert cap.e_o_emulador("PCSX2-QTX64-AVX2.EXE")
    assert not cap.e_o_emulador("pcsx2-qt")  # sem .exe não é um processo do Windows
    assert not cap.e_o_emulador("pcsx2.exe")
    assert not cap.e_o_emulador(None)
