"""Ferramenta do mapeador: captura e assinaturas lado a lado, e um rascunho de perfil de cena (caso K03).

Com o emulador próprio e o jogo numa cena, amostra alguns segundos de assinaturas, agrupa os pedaços por
material, desenha as caixas numeradas sobre a captura e grava um rascunho de perfil com classes sugeridas:

- "interface": desenhos sem profundidade presentes em todos os quadros (vida, munição, mira);
- "cenario": material de mundo cujos pedaços ficam parados;
- "movel": material de mundo cujos pedaços mudam de lugar com a câmera parada (personagem, inimigo, animação);
- "desconhecido": o resto.

O mapeador confirma ou corrige as classes no arquivo e, para cada "movel", diz se é jogador, inimigo ou
outro. Nenhuma captura do jogo entra no repositório: a imagem fica na pasta de saída.

Uso: python -m iaemps2.bancada.mapear_cena --saida ~/IAEmPS2/perfis/cena/rascunho-SLUS-21134 [--slot 96] [--segundos 3]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from PIL import ImageDraw

from iaemps2.bancada.prova_cena import (
    amostrar,
    esperar_cena,
    para_janela,
    tamanho_do_quadro,
    viewport_da_captura,
)
from iaemps2.olho import captura as cap
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Assinatura, Cliente
from iaemps2.ponte.emulador import identificar

VERSAO_DO_PERFIL = 1


def classificar(
    material: int, pedacos: list[Assinatura], presenca: float, n_quadros: int, deslocamento: float
) -> str:
    if not pedacos:
        return "desconhecido"
    if not any(a.qualifica for a in pedacos):
        return "interface" if presenca >= 0.95 else "desconhecido"
    if presenca < 0.5:
        return "desconhecido"
    return "movel" if deslocamento >= 2.0 else "cenario"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--saida", type=Path, required=True, help="pasta de saída (criada)")
    parser.add_argument("--slot", type=int, default=None, help="carrega um estado salvo do mestre antes")
    parser.add_argument("--segundos", type=float, default=3.0)
    args = parser.parse_args(argv)
    args.saida.mkdir(parents=True, exist_ok=True)

    c = Cliente(porta=28011)
    c.conectar()
    jogo = identificar(c)
    if args.slot is not None:
        c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([args.slot])))
        time.sleep(6)
    c.cena_limpar(0)
    esperar_cena(c)
    quadros = amostrar(c, args.segundos)
    n = len(quadros)
    quadro = tamanho_do_quadro(quadros)

    por_material: dict[int, list[Assinatura]] = defaultdict(list)
    presentes: dict[int, set[int]] = defaultdict(set)
    centros: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for k, lista in quadros:
        for a in lista:
            por_material[a.hash_textura].append(a)
            presentes[a.hash_textura].add(k)
            centros[(a.hash_textura, a.hash_forma)].append(((a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2))

    def deslocamento_do_material(m: int) -> float:
        """Desvio-padrão médio do centro dos pedaços estáveis do material, em pixels do jogo."""
        valores = []
        for (mat, _), pontos in centros.items():
            if mat != m or len(pontos) < max(3, n // 2):
                continue
            xs, ys = [q[0] for q in pontos], [q[1] for q in pontos]
            valores.append((statistics.pstdev(xs) + statistics.pstdev(ys)) / 2)
        return statistics.median(valores) if valores else 0.0

    hwnd, area_janela = cap.localizar_janela()
    imagem = cap.capturar_janela(hwnd, area_janela)
    viewport = viewport_da_captura(imagem)
    desenho = ImageDraw.Draw(imagem)
    cores = {"interface": "#1f9d55", "cenario": "#1f4fd1", "movel": "#c53030", "desconhecido": "#c77d0a"}

    materiais = []
    ultimo = quadros[-1][1]
    for indice, (m, pedacos) in enumerate(sorted(por_material.items(), key=lambda kv: -len(kv[1]))):
        presenca = len(presentes[m]) / max(1, n)
        desloc = deslocamento_do_material(m)
        classe = classificar(m, pedacos, presenca, n, desloc)
        # uma caixa por pedaço estável, não a união do material: a união cobre a tela quando o material é a casca
        # de todas as árvores
        for a in (a for a in ultimo if a.hash_textura == m):
            if len(centros[(a.hash_textura, a.hash_forma)]) < max(3, n // 2):
                continue
            caixa = para_janela((a.x0, a.y0, a.x1, a.y1), viewport, quadro)
            desenho.rectangle(caixa, outline=cores[classe], width=1)
            desenho.text((caixa[0] + 2, caixa[1] + 1), str(indice), fill=cores[classe])
        formas = sorted(
            {
                f"{a.hash_forma:016x}"
                for a in pedacos
                if (a.hash_textura, a.hash_forma) in centros
                and len(centros[(a.hash_textura, a.hash_forma)]) >= max(3, n // 2)
            }
        )
        materiais.append(
            {
                "indice": indice,
                "material": f"{m:016x}",
                "classe_sugerida": classe,
                "classe": None,
                "fallback": bool(pedacos[0].fallback),
                "mundo": bool(any(a.qualifica for a in pedacos)),
                "presenca": round(presenca, 3),
                "pedacos_por_quadro": round(len(pedacos) / max(1, len(presentes[m])), 1),
                "deslocamento_px": round(desloc, 1),
                "pedacos_estaveis": formas,
                "nota": "",
            }
        )

    imagem.save(str(args.saida / "captura_com_caixas.png"))
    perfil = {
        "versao_do_perfil": VERSAO_DO_PERFIL,
        "jogo": {
            "serial": jogo.identificacao.serial,
            "crc": jogo.identificacao.crc,
            "titulo": jogo.identificacao.titulo,
        },
        "cena": {"quadro": quadro, "quadros_amostrados": n, "slot_carregado": args.slot},
        "classes": [
            "cenario",
            "inimigo",
            "item",
            "interface",
            "perigo",
            "saida",
            "jogador",
            "movel",
            "desconhecido",
        ],
        "materiais": materiais,
    }
    (args.saida / "perfil-rascunho.json").write_text(
        json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    resumo: dict[str, int] = defaultdict(int)
    for entrada in materiais:
        resumo[str(entrada["classe_sugerida"])] += 1
    print("materiais:", len(materiais), "| sugestões:", dict(resumo))
    print("rascunho em", args.saida)
    c.cena_limpar(0)
    c.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
