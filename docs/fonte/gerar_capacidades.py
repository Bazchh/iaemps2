# -*- coding: utf-8 -*-
"""Gera o catálogo de capacidades do jogo (S9-03) a partir do perfil de memória.

Uso: python gerar_capacidades.py [perfis/memoria/SLUS-21134.json] [docs/Capacidades-SLUS-21134.md]
A fonte única é o bloco "capacidades" do perfil. O teste tests/test_capacidades.py falha quando o documento está
desatualizado ou quando um endereço do catálogo não existe no índice de funções.
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
ENTRADA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "Capacidades-SLUS-21134.md"

ESTADOS = {
    "provada": "provada (registro datado e ferramenta em src/)",
    "provada_sem_ferramenta": "provada, sem ferramenta em src/",
    "provada_em_script": "provada só em script de reversa (uma execução)",
    "candidata": "candidata (lida no C, nunca acionada)",
    "trava": "trava (nunca acionar)",
}
VIAS = {"chamada": "chamada remota", "escrita": "escrita de memória", "canal_cena": "camada de cena"}


def celula(texto):
    return str(texto).replace("|", "\\|").replace("\n", " ") or "—"


def sorteavel(c):
    """Entra no sorteio do aceite: provada, com ferramenta em src/ ou acionável pelo cliente do canal."""
    return c["estado"] == "provada"


def gerar(perfil):
    cp = perfil["capacidades"]
    jogo = perfil["jogo"]
    lista = cp["lista"]
    linhas = []
    w = linhas.append
    w(f"# Catálogo de capacidades do jogo de abertura ({jogo['titulo']}, {jogo['serial']} {jogo['versao']})")
    w("")
    w(f"Documento gerado de `perfis/memoria/{jogo['serial']}.json` (bloco `capacidades`, versão {cp['versao']}, {cp['data']}) por")
    w("`docs/fonte/gerar_capacidades.py`. Não editar à mão: mudar o perfil e gerar de novo. Entrega do card S9-03.")
    w("")
    w(cp["nota"])
    w("")
    w(f"**Regra geral:** {cp['regra_geral']}.")
    w("")
    w("## Resumo")
    w("")
    cont = {k: sum(1 for c in lista if c["estado"] == k) for k in ESTADOS}
    w("| estado | quantas | o que significa |")
    w("|---|---|---|")
    for k, texto in ESTADOS.items():
        w(f"| {k} | {cont[k]} | {texto} |")
    w(f"| **total** | **{len(lista)}** | {sum(1 for c in lista if sorteavel(c))} entram no sorteio do aceite |")
    w("")
    w("Critério de aceite do card (o cliente escolhe três capacidades ao acaso, sem semente, e cada uma funciona ao vivo")
    w(f"como descrita, com o jogo seguindo): **{cp['aceite_cliente']}**. As escolhíveis são as de estado 'provada'. O que")
    w("está marcado 'trava' não entra no catálogo de ações do S8-03.")
    w("")
    w("## Tabela")
    w("")
    w("| capacidade | função | endereço | via | argumentos | trampolim | ferramenta | estado | prova | ensaio |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for c in lista:
        w(
            f"| [{celula(c['nome'])}](#{c['id']}) | {celula(c['funcao'])} | {celula(', '.join(c['endereco']))} | "
            f"{VIAS[c['via']]} | {c['n_args']} | {'sim' if c['trampolim'] else 'não'} | {celula(c['ferramenta'])} | "
            f"{c['estado']} | {celula(c['prova']['data'] or '—')} | {celula(c['ensaio']['data'].split(',')[0] if c['ensaio']['data'] else '—')} |"
        )
    w("")
    for k, texto in ESTADOS.items():
        grupo = [c for c in lista if c["estado"] == k]
        if not grupo:
            continue
        w(f"## {texto[0].upper() + texto[1:]}")
        w("")
        for c in grupo:
            w(f'<a id="{c["id"]}"></a>')
            w(f"### {c['nome']}")
            w("")
            w(f"- **Função:** {c['funcao']} ({', '.join(c['endereco']) or 'sem endereço'}); símbolo: `{celula(c['simbolo'])}`")
            w(f"- **Via:** {VIAS[c['via']]}; {c['n_args']} argumentos; trampolim {'necessário' if c['trampolim'] else 'desnecessário'}")
            w(f"- **Argumentos:** {c['argumentos']}")
            w(f"- **Ferramenta:** {c['ferramenta']}")
            if c["pre_condicoes"]:
                w("- **Pré-condições:**")
                for pc in c["pre_condicoes"]:
                    w(f"  - {pc}")
            else:
                w("- **Pré-condições:** nenhuma registrada")
            w(f"- **Efeito visível:** {c['efeito']}")
            w(f"- **Como desfazer:** {c['desfazer']}")
            w(f"- **Risco / causa da trava:** {c['risco']}")
            w(f"- **Prova:** {c['prova']['data'] or 'nenhuma'}; {c['prova']['detalhe']}")
            w(f"- **Ensaio:** {c['ensaio']['data'] or '—'}; {c['ensaio']['resultado']}")
            w("")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    perfil = json.loads(ENTRADA.read_text(encoding="utf-8"))
    SAIDA.write_text(gerar(perfil), encoding="utf-8", newline="\n")
    print(f"{SAIDA} gerado: {len(perfil['capacidades']['lista'])} capacidades")
