"""Card S9-01: índice de funções por subsistema a partir da lista do Ghidra e da tabela de módulos realocados."""

from __future__ import annotations

from pathlib import Path

from iaemps2.bancada import mapa


def test_classificacao_por_nome_e_por_modulo() -> None:
    assert mapa.subsistema("cItemMgr::get", "executavel") == "inventario"
    assert mapa.subsistema("EmSetEvent", "executavel") == "personagens"
    assert mapa.subsistema("SceAtCreateItemAt", "executavel") == "cenas_e_roteiro"
    assert mapa.subsistema("FUN_002a5108", "executavel") == "ligador_snr2"
    assert mapa.subsistema("FUN_08001234", "em12") == "personagens"
    assert mapa.subsistema("FUN_0c001234", "pl11") == "jogador"
    assert mapa.subsistema("FUN_00123456", "executavel") == "sem_classificacao"


def test_gerar_indice(tmp_path: Path) -> None:
    funcoes = tmp_path / "funcoes.csv"
    funcoes.write_text(
        "endereco,nome,tamanho,chamadores\n"
        "0011e630,cItemMgr::get,500,17\n"
        "08000100,em12__Em12Init__FP3cEm,80,1\n"
        "40000200,FUN_40000200,40,0\n",
        encoding="utf-8",
    )
    modulos = tmp_path / "modulos.csv"
    modulos.write_text(
        "modulo,base,tamanho\nem12.rel,08000000,444692\npl11.rel,40000000,33729\n", encoding="utf-8"
    )
    saida = tmp_path / "indice.csv"
    contagem = mapa.gerar(funcoes, modulos, saida)
    linhas = saida.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "endereco,nome,modulo,subsistema,tamanho,chamadores"
    assert linhas[1] == "0011e630,cItemMgr::get,executavel,inventario,500,17"
    assert linhas[2] == "08000100,Em12Init__FP3cEm,em12,personagens,80,1"
    assert linhas[3] == "40000200,FUN_40000200,pl11,jogador,40,0"
    assert contagem == {"inventario": 1, "personagens": 1, "jogador": 1}
