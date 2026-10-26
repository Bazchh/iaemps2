"""Card S2-02: diferença entre capturas e tempo máximo.

Critério de aceite: dado o jogo parado numa tela, quando passam dez ciclos, então no máximo um envio acontece
pelo tempo máximo e os outros são registrados como poupados.
"""

from __future__ import annotations

from PIL import Image

from iaemps2.olho import captura as cap
from iaemps2.olho.diferenca import DEGRAU, Comparador, Veredito, diferenca, tamanho_esperado

AREA = cap.Retangulo(0, 0, 640, 360)


def _captura(
    cor: tuple[int, int, int], largura: int = 640, altura: int = 360, mancha: int = 0
) -> cap.Captura:
    img = Image.new("RGB", (largura, altura), cor)
    if mancha:
        img.paste((255, 255, 255), (0, 0, mancha, altura))
    return cap.preparar(img, AREA, largura_px=640, qualidade=70)


def test_diferenca_iguais_e_diferentes() -> None:
    a, b = _captura((40, 40, 40)), _captura((40, 40, 40))
    assert diferenca(a.miniatura, b.miniatura) == 0.0
    c = _captura((200, 200, 200))
    assert diferenca(a.miniatura, c.miniatura) == 1.0
    assert diferenca(a.miniatura, b"") == 1.0  # tamanhos diferentes: tudo mudou
    assert len(a.miniatura) == tamanho_esperado()


def test_degrau_ignora_ruido_pequeno() -> None:
    a, b = _captura((100, 100, 100)), _captura((100 + DEGRAU, 100 + DEGRAU, 100 + DEGRAU))
    assert diferenca(a.miniatura, b.miniatura) == 0.0
    c = _captura((100 + DEGRAU + 1,) * 3)
    assert diferenca(a.miniatura, c.miniatura) == 1.0


def test_jogo_parado_dez_ciclos_so_um_envio_pelo_tempo() -> None:
    agora = [0.0]
    comp = Comparador(limiar=0.04, tempo_maximo_s=30, relogio=lambda: agora[0])
    parado = _captura((60, 60, 60))
    vereditos: list[Veredito] = []
    for _ in range(10):
        vereditos.append(comp.avaliar(parado))
        agora[0] += 5  # dez ciclos de 5 s = 50 s
    enviados = [v for v in vereditos if v.enviar]
    assert [v.motivo for v in enviados] == ["primeira", "intervalo_vencido"]
    assert comp.enviadas == 2 and comp.poupadas == 8
    assert all(v.motivo == "sem_mudanca" and v.diferenca == 0.0 for v in vereditos if not v.enviar)


def test_mudanca_real_libera() -> None:
    comp = Comparador(limiar=0.04, tempo_maximo_s=999)
    assert comp.avaliar(_captura((60, 60, 60))).motivo == "primeira"
    pouca = comp.avaliar(_captura((60, 60, 60), mancha=10))  # ~1,5 % da largura
    assert not pouca.enviar and pouca.diferenca is not None and pouca.diferenca < 0.04
    muita = comp.avaliar(_captura((60, 60, 60), mancha=100))  # ~15 %
    assert (
        muita.enviar and muita.motivo == "mudanca" and muita.diferenca is not None and muita.diferenca > 0.1
    )


def test_referencia_troca_a_cada_envio() -> None:
    comp = Comparador(limiar=0.04, tempo_maximo_s=999)
    comp.avaliar(_captura((0, 0, 0)))
    assert comp.avaliar(_captura((200, 200, 200))).enviar
    assert not comp.avaliar(_captura((200, 200, 200))).enviar  # a nova referência é a clara


def test_tamanho_mudou_descarta_a_referencia() -> None:
    comp = Comparador(limiar=0.04, tempo_maximo_s=999)
    comp.avaliar(_captura((60, 60, 60)))
    v = comp.avaliar(_captura((60, 60, 60), largura=320, altura=180))
    assert v.enviar and v.motivo == "tamanho_mudou" and v.diferenca is None


def test_esquecer_volta_a_primeira() -> None:
    comp = Comparador()
    comp.avaliar(_captura((60, 60, 60)))
    comp.esquecer()
    assert comp.avaliar(_captura((60, 60, 60))).motivo == "primeira"
