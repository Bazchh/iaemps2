"""Prova de identidade de pedaço de malha (card S7-01, lacuna LC-15).

Com o emulador próprio e a cena do jogo de abertura carregada, mede quanto a assinatura de forma (hash das
coordenadas de textura) separa os pedaços que compartilham material, quanto ela se mantém entre quadros, e
quanto da tela muda ao esconder um pedaço só, comparado a esconder o material inteiro.

Uso: python -m iaemps2.bancada.prova_identidade [--slot 95] [--sem-carregar] [--saida pasta/identidade.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from iaemps2.bancada.prova_cena import (
    amostrar,
    diferenca,
    esperar_cena,
    gravar,
    para_janela,
    tamanho_do_quadro,
    viewport_da_captura,
)
from iaemps2.olho import captura as cap
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import REGRA_ESCONDER, Cliente


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, default=95)
    parser.add_argument("--saida", type=Path, default=None)
    parser.add_argument("--sem-carregar", action="store_true")
    args = parser.parse_args(argv)
    pasta = args.saida.parent if args.saida is not None else Path(".")
    resultado: dict[str, object] = {}

    c = Cliente(porta=28011)
    c.conectar()
    if not args.sem_carregar:
        c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([args.slot])))
        time.sleep(6)
    c.cena_limpar(0)
    esperar_cena(c)

    quadros = amostrar(c, 3.0)
    n_quadros = len(quadros)
    quadro = tamanho_do_quadro(quadros)
    area_quadro = quadro[0] * quadro[1]

    # por material: quantos pedaços distintos; por pedaço: presença entre quadros e cópias por quadro
    formas_por_material: dict[int, set[int]] = defaultdict(set)
    presenca: dict[tuple[int, int], set[int]] = defaultdict(set)
    copias: dict[tuple[int, int], int] = defaultdict(int)
    caixas: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    areas: dict[tuple[int, int], int] = {}
    for n, lista in quadros:
        for a in lista:
            if a.fallback or not a.qualifica:
                continue
            chave = (a.hash_textura, a.hash_forma)
            formas_por_material[a.hash_textura].add(a.hash_forma)
            presenca[chave].add(n)
            copias[chave] += 1
            caixas[chave] = (a.x0, a.y0, a.x1, a.y1)
            areas[chave] = a.area
    pedacos = list(presenca)
    estaveis = [k for k in pedacos if len(presenca[k]) / n_quadros >= 0.95]
    unicos = [k for k in pedacos if copias[k] / max(1, len(presenca[k])) <= 1.05]
    resultado["identidade"] = {
        "quadros": n_quadros,
        "materiais_de_mundo": len(formas_por_material),
        "pedacos_de_mundo": len(pedacos),
        "pedacos_por_material_mediana": statistics.median(len(v) for v in formas_por_material.values()),
        "pedacos_por_material_max": max(len(v) for v in formas_por_material.values()),
        "parcela_pedacos_presentes_em_95pc_dos_quadros": len(estaveis) / max(1, len(pedacos)),
        "parcela_pedacos_com_uma_copia_por_quadro": len(unicos) / max(1, len(pedacos)),
    }
    print("identidade:", json.dumps(resultado["identidade"]))

    # esconder um pedaço só, comparado ao material inteiro, nos cinco pedaços estáveis de maior área
    hwnd, area_janela = cap.localizar_janela()
    antes = cap.capturar_janela(hwnd, area_janela)
    viewport = viewport_da_captura(antes)
    antes.save(str(pasta / "identidade_antes.png"))
    candidatos = sorted(
        (k for k in estaveis if 0.005 <= areas[k] / area_quadro <= 0.4), key=lambda k: areas[k], reverse=True
    )[:5]
    ensaios = []
    for i, (tex, forma) in enumerate(candidatos):
        caixa_janela = para_janela(caixas[(tex, forma)], viewport, quadro)
        id_p = c.cena_regra(REGRA_ESCONDER, hash_textura=tex, hash_forma=forma, duracao_ms=900)
        time.sleep(0.5)
        so_pedaco = cap.capturar_janela(hwnd, area_janela)
        c.cena_limpar(id_p)
        time.sleep(0.4)
        id_m = c.cena_regra(REGRA_ESCONDER, hash_textura=tex, duracao_ms=900)
        time.sleep(0.5)
        material = cap.capturar_janela(hwnd, area_janela)
        est = c.cena_estatisticas(id_m)
        c.cena_limpar(id_m)
        time.sleep(0.4)
        so_pedaco.save(str(pasta / f"identidade_pedaco_{i}.png"))
        material.save(str(pasta / f"identidade_material_{i}.png"))
        ensaios.append(
            {
                "material": f"{tex:016x}",
                "forma": f"{forma:016x}",
                "pedacos_no_material": len(formas_por_material[tex]),
                "caixa": caixas[(tex, forma)],
                "area_relativa": areas[(tex, forma)] / area_quadro,
                "mudanca_na_caixa_so_pedaco": diferenca(antes, so_pedaco, caixa_janela),
                "mudanca_na_caixa_material": diferenca(antes, material, caixa_janela),
                "quadros_material_aplicada": est.quadros_aplicada,
            }
        )
        print("ensaio", json.dumps(ensaios[-1]))
    resultado["ensaios"] = ensaios
    c.cena_limpar(0)
    c.fechar()
    gravar(args.saida, resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
