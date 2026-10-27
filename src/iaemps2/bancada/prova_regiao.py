"""Prova de identidade por material e região (card S7-01, parte 2, lacuna LC-15).

Com o emulador próprio e um estado com inimigos, usa o perfil de cena para achar os materiais de inimigo,
rastreia a caixa deles quadro a quadro (posição na tela) e esconde o material só dentro dessa região, para
medir se a regra age no inimigo e poupa o resto da cena (o jogador compartilha material com o inimigo).

Uso: python -m iaemps2.bancada.prova_regiao [--slot 91] [--sem-carregar] [--saida pasta/regiao.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from iaemps2.bancada.prova_cena import (
    Caixa,
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
from iaemps2.ponte.cliente import REGRA_ESCONDER, Assinatura, Cliente

PERFIL = Path(__file__).resolve().parents[3] / "perfis" / "cena" / "SLUS-21134.json"


def materiais_da_classe(classe: str) -> set[int]:
    perfil = json.loads(PERFIL.read_text(encoding="utf-8"))
    return {int(m["material"], 16) for m in perfil["materiais"] if m["classe"] == classe}


def uniao(caixas: list[Caixa], margem: int = 8) -> Caixa | None:
    if not caixas:
        return None
    return (
        min(c[0] for c in caixas) - margem,
        min(c[1] for c in caixas) - margem,
        max(c[2] for c in caixas) + margem,
        max(c[3] for c in caixas) + margem,
    )


def rastrear(quadros: list[tuple[int, list[Assinatura]]], materiais: set[int]) -> list[Caixa | None]:
    """A caixa dos materiais escolhidos em cada quadro: o rastreio mais simples que existe."""
    return [
        uniao([(a.x0, a.y0, a.x1, a.y1) for a in lista if a.hash_textura in materiais])
        for _, lista in quadros
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, default=91)
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

    inimigo = materiais_da_classe("inimigo")
    personagem = materiais_da_classe("personagem")
    quadros = amostrar(c, 3.0)
    quadro = tamanho_do_quadro(quadros)
    trilha = rastrear(quadros, inimigo)
    presentes = [t for t in trilha if t is not None]
    centros = [((t[0] + t[2]) / 2, (t[1] + t[3]) / 2) for t in presentes]
    resultado["rastreio"] = {
        "quadros": len(quadros),
        "quadros_com_inimigo": len(presentes),
        "deslocamento_px": round(max(x for x, _ in centros) - min(x for x, _ in centros), 1)
        if centros
        else None,
        "caixa_ultima": presentes[-1] if presentes else None,
    }
    print("rastreio:", json.dumps(resultado["rastreio"]))
    if not presentes:
        print("nenhum material de inimigo na tela; carregue um estado com inimigo visível")
        gravar(args.saida, resultado)
        c.fechar()
        return 2
    regiao = presentes[-1]

    hwnd, area_janela = cap.localizar_janela()
    antes = cap.capturar_janela(hwnd, area_janela)
    viewport = viewport_da_captura(antes)
    antes.save(str(pasta / "regiao_antes.png"))
    dentro = para_janela(regiao, viewport, quadro)
    fora = para_janela((0, 0, quadro[0], regiao[1]), viewport, quadro)  # faixa acima da região

    ensaios = []
    for nome, materiais, com_regiao in (
        ("inimigo_na_regiao", inimigo, True),
        ("inimigo_na_tela_toda", inimigo, False),
        ("personagem_na_regiao", personagem, True),
        ("personagem_na_tela_toda", personagem, False),
    ):
        ids = [
            c.cena_regra(
                REGRA_ESCONDER,
                hash_textura=m,
                retangulo=regiao if com_regiao else (0, 0, 0, 0),
                duracao_ms=2_500,
            )
            for m in materiais
        ]
        time.sleep(0.8)
        img = cap.capturar_janela(hwnd, area_janela)
        img.save(str(pasta / f"regiao_{nome}.png"))
        aplicadas = sum(c.cena_estatisticas(i).quadros_aplicada for i in ids)
        totais = sum(c.cena_estatisticas(i).quadros_total for i in ids)
        c.cena_limpar(0)
        time.sleep(0.6)
        ensaios.append(
            {
                "ensaio": nome,
                "materiais": len(materiais),
                "mudanca_dentro_da_regiao": round(diferenca(antes, img, dentro), 2),
                "mudanca_fora_da_regiao": round(diferenca(antes, img, fora), 2),
                "parcela_quadros_aplicada": round(aplicadas / max(1, totais), 3),
            }
        )
        print("ensaio", json.dumps(ensaios[-1]))
    resultado["regiao"] = regiao
    resultado["ensaios"] = ensaios
    c.cena_limpar(0)
    c.fechar()
    gravar(args.saida, resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
