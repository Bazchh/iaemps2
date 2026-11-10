# -*- coding: utf-8 -*-
"""Gera o documento de estruturas do jogo (S9-02) a partir do perfil de memória.

Uso: python gerar_estruturas.py [perfis/memoria/SLUS-21134.json] [docs/Estruturas-SLUS-21134.md]
A fonte única é o bloco "estruturas" do perfil; a tabela de cobertura e todos os números são calculados
daqui, nada é digitado à mão. O teste tests/test_estruturas.py falha quando o documento está desatualizado.
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
ENTRADA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "Estruturas-SLUS-21134.md"

PROVAS_FORTES = {"decompilado", "vigia", "foto", "ao_vivo", "publica"}
STATUS = {"lida": "lida", "parcial": "parcial", "nao_lida": "não lida"}


def provas_de(campo):
    return {p.strip() for p in campo["p"].split(",") if p.strip()}


def celula(texto):
    return str(texto).replace("|", "\\|").replace("\n", " ") or "—"


def determinado(celula_):
    """Quem escreve / quem lê conta só quando vem de prova no PS2: nem vazio, nem 'não lido', nem só o nome do
    GameCube '(gc)', nem dedução '(inferido)'."""
    return bool(celula_) and not any(m in celula_ for m in ("não lid", "(gc)", "(inferido)"))


def cobertura(estrutura):
    campos = estrutura["campos"]
    com_prova = sum(1 for c in campos if provas_de(c) & PROVAS_FORTES)
    com_fluxo = sum(1 for c in campos if determinado(c["e"]) and determinado(c["l"]))
    return len(campos), com_prova, com_fluxo


def gerar(perfil):
    e = perfil["estruturas"]
    jogo = perfil["jogo"]
    linhas = []
    w = linhas.append
    w(f"# Estruturas e tabelas do jogo de abertura ({jogo['titulo']}, {jogo['serial']} {jogo['versao']})")
    w("")
    w(f"Documento gerado de `perfis/memoria/{jogo['serial']}.json` (bloco `estruturas`, versão {e['versao']}, {e['data']}) por")
    w("`docs/fonte/gerar_estruturas.py`. Não editar à mão: mudar o perfil e gerar de novo. Entrega do card S9-02.")
    w("")
    w(e["nota"])
    w("")
    w("## Cobertura")
    w("")
    w("Uma linha por estrutura: campos descritos, campos com prova no PS2 (não só nome do GameCube), campos com quem")
    w("escreve e quem lê determinados por prova (células marcadas '(gc)' ou '(inferido)' não contam), e o estado.")
    w("As estruturas sem campo são as que ninguém leu ainda. O critério de aceite do card (três campos por estrutura")
    w("conferidos ao vivo pelo cliente) ainda não foi aplicado a nenhuma linha.")
    w("")
    w("| estrutura | raiz | campos | com prova no PS2 | com escreve e lê | estado |")
    w("|---|---|---|---|---|---|")
    tot = [0, 0, 0]
    for s in e["lista"]:
        n, prova, fluxo = cobertura(s)
        tot[0] += n
        tot[1] += prova
        tot[2] += fluxo
        w(f"| [{celula(s['nome'])}](#{s['id'].lower()}) | {celula(s['raiz'])} | {n} | {prova} | {fluxo} | {STATUS[s['status']]} |")
    w(f"| **total** | | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | {sum(1 for s in e['lista'] if s['status'] == 'lida')} lidas, "
      f"{sum(1 for s in e['lista'] if s['status'] == 'parcial')} parciais, {sum(1 for s in e['lista'] if s['status'] == 'nao_lida')} não lidas |")
    w("")
    w("Legenda das provas: " + "; ".join(f"**{k}** = {v}" for k, v in e["provas"].items()) + ".")
    w("")
    for s in e["lista"]:
        w(f'<a id="{s["id"].lower()}"></a>')
        w(f"## {s['nome']}")
        w("")
        w(f"- **Raiz:** {s['raiz']}")
        if s.get("tamanho"):
            w(f"- **Tamanho:** {s['tamanho']}")
        w(f"- **Estado:** {STATUS[s['status']]}")
        w("")
        w(s["resumo"])
        w("")
        if s["campos"]:
            w("| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |")
            w("|---|---|---|---|---|---|---|")
            for c in s["campos"]:
                w(f"| `{celula(c['d'])}` | {celula(c['t'])} | {celula(c['n'])} | {celula(c['s'])} | {celula(c['e'])} | {celula(c['l'])} | {celula(c['p'])} |")
            w("")
        if s["funcoes"]:
            w("Funções:")
            w("")
            for f in s["funcoes"]:
                w(f"- `{celula(f['endereco'])}` {celula(f['nome'])}: {celula(f['papel'])}")
            w("")
        if s["pendencias"]:
            w("Pendências:")
            w("")
            for p in s["pendencias"]:
                w(f"- {p}")
            w("")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    perfil = json.loads(ENTRADA.read_text(encoding="utf-8"))
    SAIDA.write_text(gerar(perfil), encoding="utf-8", newline="\n")
    print(f"{SAIDA} gerado: {len(perfil['estruturas']['lista'])} estruturas")
