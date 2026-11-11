"""Índice do mapa completo do jogo de abertura: uma linha por função, com módulo e subsistema.

Junta a lista de funções exportada pelo Ghidra (``funcoes.csv``: endereço, nome, tamanho, chamadores) com a tabela de
módulos realocados (``modulos.csv`` do realocador) e classifica cada função por subsistema a partir do nome que o
jogo dá a ela ou, sem nome, do módulo em que está. A saída é o ``perfis/memoria/<serial>.funcoes.csv`` do
repositório; o C decompilado fica fora (``~/IAEmPS2/reversa/saida/``).

Uso: python -m iaemps2.bancada.mapa <funcoes.csv do Ghidra> <modulos.csv> <saida.csv>
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

SUBSISTEMAS: list[tuple[str, str]] = [
    (r"^(cItemMgr|cItem\b|Merchant|ItemExamine|pzl|WeaponId2|itemInfo|searchItemPieceData)", "inventario"),
    (
        r"^(cEm\b|cEmMgr|cEm[A-Z]|Em[A-Z]|EmSet|EmList|em[0-9a-f]{2}__|SceCountEm|SceDestroyEm|IsGanado)",
        "personagens",
    ),
    (r"^(cPlayer|cPl[A-Z0-9]|Pl[A-Z]|pl[0-9a-f]{2}__|cSub)", "jogador"),
    (
        r"^(cObjWep|cObjBull|cObjLauncher|cObjRocket|cPlWep|cEmWep|Dmg_tbl|EmAtkHitCk|LifeDown)",
        "armas_e_dano",
    ),
    (r"^(Sce[A-Z]|sce[A-Z]|Scenario|Event|EventMgr|readEmList)", "cenas_e_roteiro"),
    (r"^(Task|SceSleep|TaskSleep|cSofdec|Diedemo)", "tarefas_e_threads"),
    (r"^(cDvd|Dvd|DVD|Afs|IdTex)", "disco_e_arquivos"),
    (r"^(Snd|Sfx|Se[A-Z]|cVoice|Str[A-Z]|ADX|adx)", "som"),
    (r"^(Camera|cCamera|cam[A-Z])", "camera"),
    (
        r"^(cModel|Mot[A-Z]|Cloth|Parts|cLight|cEff|Eff|Esp|GS|Vu0|Vu1|Vif|OTW|SsPrim|IDSystem|MessageControl)",
        "modelos_e_graficos",
    ),
    (r"^(cSat|cAtari|Atari|Hit[A-Z]|FlrAt|cSatMgr)", "colisao"),
    (r"^(mem_alloc|Mem_|Debug_free|Debug_alloc|InitModule|SearchEmModule|EmRead)", "memoria_e_modulos"),
    (r"^(FUN_002a4[0-9a-f]{3}|FUN_002a5[0-9a-f]{3})", "ligador_snr2"),
    (
        r"^(memset|memcpy|strcmp|strcpy|strlen|sprintf|printf|eprintf|OSReport|qsort|sqrt|sin|cos)",
        "biblioteca_c",
    ),
    (r"^(Card|cCard|Save|Load|Get[A-Z]|Set[A-Z])", "sistema_e_save"),
]


def subsistema(nome: str, modulo: str) -> str:
    for padrao, sub in SUBSISTEMAS:
        if re.match(padrao, nome):
            return sub
    if modulo.startswith("em"):
        return "personagens"
    if modulo.startswith("pl"):
        return "jogador"
    return "sem_classificacao"


def modulo_de(endereco: int, modulos: list[tuple[str, int, int]]) -> str:
    for nome, base, tamanho in modulos:
        if base <= endereco < base + tamanho:
            return nome
    if endereco < 0x00400000:
        return "executavel"
    if 0x01000000 <= endereco < 0x02000000:
        return "modulo_vivo_estado91"
    return "?"


def gerar(funcoes_ghidra: Path, modulos_csv: Path, saida: Path) -> dict[str, int]:
    modulos: list[tuple[str, int, int]] = []
    if modulos_csv.exists():
        with modulos_csv.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                modulos.append((r["modulo"][:-4], int(r["base"], 16), int(r["tamanho"])))
    contagem: dict[str, int] = {}
    with funcoes_ghidra.open(encoding="utf-8") as f, saida.open("w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["endereco", "nome", "modulo", "subsistema", "tamanho", "chamadores"])
        for r in csv.DictReader(f):
            endereco = int(r["endereco"], 16)
            mod = modulo_de(endereco, modulos)
            nome = r["nome"]
            if mod not in ("executavel", "?") and nome.startswith(f"{mod}__"):
                nome = nome[len(mod) + 2 :]
            sub = subsistema(nome, mod)
            contagem[sub] = contagem.get(sub, 0) + 1
            w.writerow([f"{endereco:08x}", nome, mod, sub, r["tamanho"], r["chamadores"]])
    return contagem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("funcoes", type=Path)
    parser.add_argument("modulos", type=Path)
    parser.add_argument("saida", type=Path)
    args = parser.parse_args(argv)
    contagem = gerar(args.funcoes, args.modulos, args.saida)
    for sub, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"{sub:24s} {n:6d}")
    print(f"total {sum(contagem.values())} funções em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
