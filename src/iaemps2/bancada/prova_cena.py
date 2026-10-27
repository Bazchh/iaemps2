"""Prova medida da camada de cena (card S7-00, portão da fase 4).

Roda contra a versão própria do emulador com o jogo de abertura. Carrega um estado salvo do mestre para cair
na cena sem ninguém no controle, e mede:

1. identidade: parcela dos desenhos com hash real; assinatura escolhida presente em quantos quadros (LC-15);
2. esconder: em quantos quadros de 10 s o objeto escolhido deixou de ser desenhado, e quanto a tela mudou;
3. profundidade: faixa e sentido da profundidade dos desenhos de mundo (LC-16), e o quadrado injetado em
   três profundidades e duas regiões, com a fração visível medida na captura da janela;
4. custo: tempo de CPU da camada por quadro sem regras, com uma e com dez.

Uso: python -m iaemps2.bancada.prova_cena [--slot 95] [--sem-carregar] [--saida pasta/resultado.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

from iaemps2.olho import captura as cap
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import REGRA_ESCONDER, REGRA_QUADRADO, Assinatura, Cliente
from iaemps2.ponte.emulador import identificar

COR_QUADRADO = (255, 0, 255)  # magenta: rgba 0xFFFF00FF em little-endian = R=255 G=0 B=255 A=255
Caixa = tuple[int, int, int, int]


def amostrar(c: Cliente, segundos: float, passo_s: float = 0.03) -> list[tuple[int, list[Assinatura]]]:
    """Quadros distintos vistos pelo canal durante `segundos`."""
    quadros: list[tuple[int, list[Assinatura]]] = []
    ultimo = -1
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        n, lista = c.cena_lista()
        if n != ultimo:
            quadros.append((n, lista))
            ultimo = n
        time.sleep(passo_s)
    return quadros


def esperar_cena(c: Cliente, limite_s: float = 25.0, minimo_qualificados: int = 50) -> None:
    """Depois de carregar um estado, a cena leva segundos para voltar a desenhar o mundo; espera por ela."""
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        _, lista = c.cena_lista()
        if sum(1 for a in lista if a.qualifica) >= minimo_qualificados:
            return
        time.sleep(0.25)
    print("aviso: a cena não encheu de desenhos de mundo no limite; seguindo mesmo assim")


def tamanho_do_quadro(quadros: list[tuple[int, list[Assinatura]]]) -> tuple[int, int]:
    """O quadro do jogo é o sprite de tela cheia mais comum (começa em 0,0 com dois vértices); 640x448 se não houver."""
    contagem: dict[tuple[int, int], int] = defaultdict(int)
    for _, lista in quadros:
        for a in lista:
            if a.vertices == 2 and a.x0 == 0 and a.y0 == 0 and a.x1 >= 256 and a.y1 >= 192:
                contagem[(a.x1, a.y1)] += 1
    if not contagem:
        return 640, 448
    return max(contagem.items(), key=lambda kv: kv[1])[0]


def viewport_da_captura(imagem: Image.Image, limiar: int = 18) -> Caixa:
    """Retângulo não preto da captura: o emulador põe barras pretas ao manter a proporção do jogo."""
    caixa = imagem.convert("L").point(lambda v: 255 if v > limiar else 0).getbbox()
    if caixa is None:
        return 0, 0, imagem.width, imagem.height
    return caixa[0], caixa[1], caixa[2] - caixa[0], caixa[3] - caixa[1]


def para_janela(caixa: Caixa, viewport: Caixa, quadro: tuple[int, int]) -> Caixa:
    """Caixa em pixels do jogo -> pixels da captura, pelo viewport."""
    vx, vy, vw, vh = viewport
    sx, sy = vw / quadro[0], vh / quadro[1]
    return (
        int(vx + caixa[0] * sx),
        int(vy + caixa[1] * sy),
        int(vx + caixa[2] * sx),
        int(vy + caixa[3] * sy),
    )


def custo_por_quadro(c: Cliente, segundos: float) -> dict[str, float]:
    a = c.cena_estatisticas()
    time.sleep(segundos)
    b = c.cena_estatisticas()
    quadros = max(1, b.camada_quadros - a.camada_quadros)
    return {
        "quadros": quadros,
        "us_por_quadro": (b.camada_ns_total - a.camada_ns_total) / quadros / 1000,
        "desenhos_ultimo_quadro": b.desenhos_ultimo_quadro,
    }


def fracao_visivel(
    imagem: Image.Image, caixa_janela: Caixa, cor: tuple[int, int, int] = COR_QUADRADO, tol: int = 60
) -> float:
    """Fração dos pixels da caixa (em pixels da captura) que têm a cor do quadrado."""
    pixels = list(imagem.crop(caixa_janela).convert("RGB").getdata())
    if not pixels:
        return 0.0
    iguais = sum(
        1 for r, g, b in pixels if abs(r - cor[0]) < tol and abs(g - cor[1]) < tol and abs(b - cor[2]) < tol
    )
    return iguais / len(pixels)


def diferenca(a: Image.Image, b: Image.Image, rect: Caixa) -> float:
    """Diferença média de cinza entre duas capturas numa caixa (0 = igual)."""
    ra = a.crop(rect).convert("L").getdata()
    rb = b.crop(rect).convert("L").getdata()
    pares = [(int(x), int(y)) for x, y in zip(ra, rb, strict=False)]
    return float(sum(abs(x - y) for x, y in pares)) / max(1, len(pares))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, default=95)
    parser.add_argument("--saida", type=Path, default=None)
    parser.add_argument(
        "--sem-carregar", action="store_true", help="não carrega estado salvo; usa a cena atual"
    )
    args = parser.parse_args(argv)
    pasta = args.saida.parent if args.saida is not None else Path(".")
    resultado: dict[str, object] = {}

    c = Cliente(porta=28011)
    c.conectar()
    resultado["emulador"] = c.versao()
    print("versao:", resultado["emulador"])
    jogo = identificar(c)
    print("jogo:", jogo.identificacao.titulo, jogo.identificacao.serial, jogo.modo)
    if not args.sem_carregar:
        c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([args.slot])))
        time.sleep(6)
        print("estado", args.slot, "carregado; status", c.status().name)
    c.cena_limpar(0)
    esperar_cena(c)

    # 1. identidade
    quadros = amostrar(c, 3.0)
    por_hash: dict[int, list[Assinatura]] = defaultdict(list)
    presentes: dict[int, set[int]] = defaultdict(set)
    total_desenhos = 0
    com_hash = 0
    z_mundo: list[int] = []
    qualificados_por_quadro: list[int] = []
    for n, lista in quadros:
        total_desenhos += len(lista)
        qualificados_por_quadro.append(sum(1 for a in lista if a.qualifica))
        for a in lista:
            if not a.fallback:
                com_hash += 1
            por_hash[a.hash_textura].append(a)
            presentes[a.hash_textura].add(n)
            if a.qualifica:
                z_mundo.extend((a.z_min, a.z_max))
    n_quadros = len(quadros)
    largura, altura = tamanho_do_quadro(quadros)
    quadro = (largura, altura)
    area_quadro = max(1, largura * altura)
    resultado["identidade"] = {
        "quadros_amostrados": n_quadros,
        "desenhos_por_quadro": total_desenhos / max(1, n_quadros),
        "parcela_com_hash": com_hash / max(1, total_desenhos),
        "qualificados_por_quadro_mediana": statistics.median(qualificados_por_quadro)
        if qualificados_por_quadro
        else 0,
        "quadro": quadro,
    }
    print("identidade:", json.dumps(resultado["identidade"]))

    # candidatos a alvo: hash real, desenho de mundo, presente em >= 90% dos quadros, área entre 1% e 30%, poucas cópias
    candidatos = []
    for h, lista in por_hash.items():
        if any(a.fallback for a in lista) or not all(a.qualifica for a in lista):
            continue
        presenca = len(presentes[h]) / max(1, n_quadros)
        copias = len(lista) / max(1, len(presentes[h]))
        area = statistics.median(a.area for a in lista) / area_quadro
        if presenca >= 0.9 and 0.01 <= area <= 0.30 and copias <= 2.0:
            candidatos.append((area, h, presenca, copias, lista[-1]))
    candidatos.sort(reverse=True)
    resultado["candidatos"] = len(candidatos)
    if not candidatos:
        print("nenhum alvo com hash real, estável e de tamanho médio; registre e pare")
        gravar(args.saida, resultado)
        c.fechar()
        return 2

    # captura de referência (janela do emulador) e o viewport do jogo dentro dela
    hwnd, area_janela = cap.localizar_janela()
    antes = cap.capturar_janela(hwnd, area_janela)
    viewport = viewport_da_captura(antes)
    resultado["captura"] = {"janela": antes.size, "viewport": viewport}
    print("captura:", resultado["captura"])
    antes.save(str(pasta / "alvo_antes.png"))

    # alvo: entre os candidatos, o que mais muda a tela ao ser escondido por meio segundo
    ensaios = []
    for area, h, presenca, copias, exemplo in candidatos[:8]:
        caixa = (exemplo.x0, exemplo.y0, exemplo.x1, exemplo.y1)
        id_e = c.cena_regra(REGRA_ESCONDER, hash_textura=h, duracao_ms=700)
        time.sleep(0.45)
        img = cap.capturar_janela(hwnd, area_janela)
        c.cena_limpar(id_e)
        time.sleep(0.35)
        ensaios.append(
            (diferenca(antes, img, para_janela(caixa, viewport, quadro)), area, h, presenca, copias, caixa)
        )
    ensaios.sort(reverse=True)
    resultado["ensaios_de_alvo"] = [
        {"hash": f"{h:016x}", "mudanca": d, "area_relativa": a, "caixa": cx} for d, a, h, _, _, cx in ensaios
    ]
    mudanca0, area, alvo, presenca, copias, caixa_alvo = ensaios[0]
    resultado["alvo"] = {
        "hash": f"{alvo:016x}",
        "area_relativa": area,
        "presenca": presenca,
        "copias_por_quadro": copias,
        "caixa": caixa_alvo,
        "mudanca_no_ensaio": mudanca0,
    }
    print("alvo:", json.dumps(resultado["alvo"]))

    # 4a. custo sem regras
    resultado["custo_sem_regras"] = custo_por_quadro(c, 3.0)
    print("custo sem regras:", resultado["custo_sem_regras"])

    # 2. esconder o alvo por 10 s
    id_esc = c.cena_regra(REGRA_ESCONDER, hash_textura=alvo, duracao_ms=10_000)
    time.sleep(1.0)
    durante = cap.capturar_janela(hwnd, area_janela)
    durante.save(str(pasta / "alvo_escondido.png"))
    resultado["custo_uma_regra"] = custo_por_quadro(c, 3.0)
    time.sleep(6.5)
    est = c.cena_estatisticas(id_esc)
    resultado["esconder"] = {
        "quadros_total": est.quadros_total,
        "quadros_vista": est.quadros_vista,
        "quadros_aplicada": est.quadros_aplicada,
        "parcela_escondido": est.quadros_aplicada / max(1, est.quadros_total),
        "mudanca_media_na_caixa": diferenca(antes, durante, para_janela(caixa_alvo, viewport, quadro)),
    }
    print("esconder:", json.dumps(resultado["esconder"]))
    time.sleep(1.0)  # a regra venceu sozinha

    # 4b. custo com dez regras que não casam
    for i in range(10):
        c.cena_regra(REGRA_ESCONDER, hash_textura=0x0123456789ABCD00 + i, duracao_ms=6_000)
    time.sleep(0.5)
    resultado["custo_dez_regras"] = custo_por_quadro(c, 3.0)
    print("custo dez regras:", resultado["custo_dez_regras"])
    c.cena_limpar(0)

    # 3. profundidade: faixa dos desenhos de mundo e o quadrado em três profundidades, no centro e no alto
    z_min, z_max = (min(z_mundo), max(z_mundo)) if z_mundo else (0, 0)
    z_med = int(statistics.median(z_mundo)) if z_mundo else 0
    resultado["profundidade_mundo"] = {"z_min": z_min, "z_mediana": z_med, "z_max": z_max}
    print("profundidade do mundo:", resultado["profundidade_mundo"])
    cx, cy = largura // 2, altura // 2
    caixa_centro: Caixa = (cx - 100, cy - 60, cx + 100, cy + 60)
    caixa_alta: Caixa = (cx - 100, 24, cx + 100, 104)
    provas = []
    for nome, z, caixa_q in (
        ("perto_centro", z_max, caixa_centro),
        ("meio_centro", z_med, caixa_centro),
        ("longe_centro", z_min, caixa_centro),
        ("perto_alto", z_max, caixa_alta),
        ("meio_alto", z_med, caixa_alta),
        ("longe_alto", z_min, caixa_alta),
    ):
        id_q = c.cena_regra(
            REGRA_QUADRADO, retangulo=caixa_q, z=z, rgba=0xFFFF00FF, duracao_ms=2_500, apos_n=1
        )
        time.sleep(1.2)
        img = cap.capturar_janela(hwnd, area_janela)
        img.save(str(pasta / f"quadrado_{nome}.png"))
        est = c.cena_estatisticas(id_q)
        provas.append(
            {
                "nome": nome,
                "z": z,
                "caixa": caixa_q,
                "fracao_visivel": fracao_visivel(img, para_janela(caixa_q, viewport, quadro)),
                "quadros_total": est.quadros_total,
                "quadros_aplicada": est.quadros_aplicada,
            }
        )
        print("quadrado", provas[-1])
        time.sleep(1.6)
    resultado["quadrado"] = provas

    c.cena_limpar(0)
    c.fechar()
    gravar(args.saida, resultado)
    return 0


def gravar(saida: Path | None, resultado: dict[str, object]) -> None:
    if saida is None:
        return
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print("resultado gravado em", saida)


if __name__ == "__main__":
    sys.exit(main())
