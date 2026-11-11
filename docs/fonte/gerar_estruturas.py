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


RESULTADOS = ("bate", "lido", "diverge", "não conferível")


def conferidos(estrutura):
    """Contagem por resultado da conferência ao vivo (bate, lido, diverge, não conferível); zeros sem conferência."""
    cf = estrutura.get("conferencia")
    cont = dict.fromkeys(RESULTADOS, 0)
    if cf:
        for r in cf["campos"].values():
            cont[r["resultado"]] = cont.get(r["resultado"], 0) + 1
    return cont


def celula_conferencia(estrutura):
    cf = estrutura.get("conferencia")
    if not cf:
        return "—"
    if not estrutura["campos"]:
        return "sem campos"
    c = conferidos(estrutura)
    return f"{c['bate']} batem, {c['lido']} lidos, {c['diverge']} divergem, {c['não conferível']} não conferíveis"


def gerar(perfil):
    e = perfil["estruturas"]
    jogo = perfil["jogo"]
    linhas = []
    w = linhas.append
    w(f"# Estruturas e tabelas do jogo de abertura ({jogo['titulo']}, {jogo['serial']} {jogo['versao']})")
    w("")
    w(
        f"Documento gerado de `perfis/memoria/{jogo['serial']}.json` (bloco `estruturas`, versão {e['versao']}, {e['data']}) por"
    )
    w(
        "`docs/fonte/gerar_estruturas.py`. Não editar à mão: mudar o perfil e gerar de novo. Entrega do card S9-02."
    )
    w("")
    w(e["nota"])
    w("")
    w("## Cobertura")
    w("")
    w(
        "Uma linha por estrutura: campos descritos, campos com prova no PS2 (não só nome do GameCube), campos com quem"
    )
    w(
        "escreve e quem lê determinados por prova (células marcadas '(gc)' ou '(inferido)' não contam), o resultado da"
    )
    w("conferência ao vivo automática e o estado. As estruturas sem campo são as que ninguém leu ainda.")
    w("")
    com_cf = [s for s in e["lista"] if s.get("conferencia")]
    if com_cf:
        tot_cf = dict.fromkeys(RESULTADOS, 0)
        for s in com_cf:
            for k, v in conferidos(s).items():
                tot_cf[k] += v
        datas = sorted({s["conferencia"]["data"] for s in com_cf})
        estados = sorted({est for s in com_cf for est in s["conferencia"]["estados"]})
        pend = sum(1 for s in com_cf if s["conferencia"]["aceite_cliente"] == "pendente")
        w(
            f"Conferência ao vivo automática ({', '.join(datas)}; estados {', '.join(map(str, estados))}; uma execução por estado):"
        )
        w(f"{tot_cf['bate']} campos batem com a relação anotada, {tot_cf['lido']} foram lidos sem relação")
        w(
            f"independente, {tot_cf['diverge']} divergem e {tot_cf['não conferível']} não eram conferíveis nesses estados."
        )
        w(
            "'Bate' significa que o valor lido satisfez a relação escrita ao lado dele, que pode ser um cruzamento com outra"
        )
        w(
            "estrutura ou com a ISO, uma faixa, ou a constante que o perfil já afirmava; 'lido' é só o valor, sem relação"
        )
        w(
            "disponível. A força de cada 'bate' é a da relação escrita. Os resultados valem para esses estados e essa"
        )
        w(
            f"sala, não para o jogo inteiro. O critério de aceite do card (três campos por estrutura conferidos ao vivo pelo"
        )
        w(
            f"cliente) continua pendente em {pend} de {len(com_cf)} estruturas: os três campos sorteados por estrutura estão"
        )
        w("listados na seção de cada uma, com o valor lido, para o cliente olhar.")
    else:
        w("Nenhuma conferência ao vivo registrada ainda.")
    w("")
    w("| estrutura | raiz | campos | com prova no PS2 | com escreve e lê | conferência ao vivo | estado |")
    w("|---|---|---|---|---|---|---|")
    tot = [0, 0, 0]
    for s in e["lista"]:
        n, prova, fluxo = cobertura(s)
        tot[0] += n
        tot[1] += prova
        tot[2] += fluxo
        w(
            f"| [{celula(s['nome'])}](#{s['id'].lower()}) | {celula(s['raiz'])} | {n} | {prova} | {fluxo} | {celula_conferencia(s)} | {STATUS[s['status']]} |"
        )
    w(
        f"| **total** | | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | | {sum(1 for s in e['lista'] if s['status'] == 'lida')} lidas, "
        f"{sum(1 for s in e['lista'] if s['status'] == 'parcial')} parciais, {sum(1 for s in e['lista'] if s['status'] == 'nao_lida')} não lidas |"
    )
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
                w(
                    f"| `{celula(c['d'])}` | {celula(c['t'])} | {celula(c['n'])} | {celula(c['s'])} | {celula(c['e'])} | {celula(c['l'])} | {celula(c['p'])} |"
                )
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
        cf = s.get("conferencia")
        if cf:
            w(
                f"Conferência ao vivo ({cf['data']}; estados {', '.join(map(str, cf['estados']))}; sala {cf['sala']}; "
                f"semente {cf['semente']}; aceite do cliente: {cf['aceite_cliente']}):"
            )
            w("")
            if not s["campos"]:
                w("- sem campos no perfil: nada a conferir")
            for d in cf["sorteados"]:
                r = cf["campos"].get(d)
                if r:
                    w(
                        f"- sorteado `{celula(d)}` (estado {r['estado']}): **{r['resultado']}** — lido {celula(r['lido'])}; relação: {celula(r['relacao'])}"
                    )
                else:
                    w(f"- sorteado `{celula(d)}`: sem leitura")
            for d, r in cf["campos"].items():
                if r["resultado"] == "diverge" and d not in cf["sorteados"]:
                    w(
                        f"- divergência em `{celula(d)}` (estado {r['estado']}): lido {celula(r['lido'])}; relação: {celula(r['relacao'])}"
                    )
            for o in cf["observacoes"]:
                w(f"- observação: {celula(o)}")
            w("")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    perfil = json.loads(ENTRADA.read_text(encoding="utf-8"))
    SAIDA.write_text(gerar(perfil), encoding="utf-8", newline="\n")
    print(f"{SAIDA} gerado: {len(perfil['estruturas']['lista'])} estruturas")
