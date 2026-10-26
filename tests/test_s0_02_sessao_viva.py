"""Card S0-02: sessão viva, esquema, gatilhos e provas.

Critério de aceite: dado um arquivo de sessão novo, quando os três comandos proibidos rodam, então os três
falham com "registro só de acréscimo" ou violação de CHECK e nada muda; e uma cadeia ciclo, captura,
situação, decisão, intervenção grava e é lida de volta inteira.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from iaemps2.registro import banco

TABELAS = list(banco.PREENCHE_UMA_VEZ)


@pytest.fixture
def con(tmp_path: Path) -> sqlite3.Connection:
    c = banco.criar(tmp_path / "sessao.sqlite")
    yield c
    c.close()


def _sessao(con: sqlite3.Connection) -> str:
    return banco.abrir_sessao(
        con,
        jogo_titulo="Resident Evil 4",
        jogo_serial="SLUS-21134",
        jogo_crc="013e349d",
        jogo_versao="1.01",
        emulador_versao="PCSX2 v2.8.2",
        modo="reduzido",
        tom="imprevisivel",
        intensidade="media",
        servico="falso",
        aceite_versao="1",
        config_json="{}",
    )


def _cadeia(con: sqlite3.Connection) -> tuple[str, int, int]:
    sessao = _sessao(con)
    ciclo = banco.gravar_ciclo(con, sessao, 1, 0, "rodando", "observando")
    captura = banco.gravar_captura(
        con,
        {
            "ciclo_id": ciclo,
            "arquivo": "capturas/000001.jpg",
            "largura": 640,
            "altura": 406,
            "bytes": 46000,
            "digest": "abc",
            "diferenca": 0.3,
            "enviada": 1,
            "motivo_envio": "mudanca",
        },
    )
    situacao = banco.gravar_situacao(
        con,
        {
            "captura_id": captura,
            "descricao": "Leon cercado por quatro aldeões, pouca vida",
            "fase": "combate",
            "aperto": 3,
            "confianca": 0.8,
            "latencia_ms": 900,
            "resposta_bruta": "{}",
        },
    )
    decisao = banco.gravar_decisao(
        con,
        {
            "ciclo_id": ciclo,
            "situacao_id": situacao,
            "catalogo_versao": 1,
            "alavanca": "recarregar",
            "parametros_json": '{"slot": 93}',
            "motivo": "Um fôlego.",
            "motivo_origem": "servico",
            "origem": "servico",
            "pedido_bruto": "{}",
            "resposta_bruta": "{}",
            "latencia_ms": 700,
        },
    )
    intervencao = banco.gravar_intervencao(
        con,
        {
            "decisao_id": decisao,
            "alavanca": "recarregar",
            "parametros_json": '{"slot": 93}',
            "origem": "mestre",
            "estado_antes_json": '{"status": "rodando"}',
            "comando_ms": 1200,
            "reversivel": 1,
        },
    )
    return sessao, ciclo, intervencao


def test_esquema_tem_as_doze_tabelas(con: sqlite3.Connection) -> None:
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    assert set(TABELAS) <= nomes
    assert len(TABELAS) == 12
    assert con.execute("pragma user_version").fetchone()[0] == 1
    assert con.execute("pragma journal_mode").fetchone()[0] == "wal"


def test_cadeia_grava_e_volta_inteira(con: sqlite3.Connection) -> None:
    _, ciclo, intervencao = _cadeia(con)
    banco.preencher_uma_vez(
        con,
        "intervencoes",
        intervencao,
        {"confirmado_ms": 1900, "estado_depois_json": '{"status": "rodando"}', "resultado": "confirmada"},
    )
    banco.fechar_ciclo(con, ciclo, 2000)
    linha = banco.cadeia(con, intervencao)
    assert linha is not None
    assert linha["ciclo"] == 1
    assert linha["captura"] == "capturas/000001.jpg"
    assert linha["fase"] == "combate" and linha["aperto"] == 3
    assert linha["alavanca_decidida"] == "recarregar" and linha["alavanca"] == "recarregar"
    assert linha["resultado"] == "confirmada"
    assert linha["estado_depois_json"] == '{"status": "rodando"}'


# ---- as três tentativas proibidas do card ----


def test_proibido_alterar_ciclo_fechado(con: sqlite3.Connection) -> None:
    _, ciclo, _ = _cadeia(con)
    banco.fechar_ciclo(con, ciclo, 2000)
    with pytest.raises(sqlite3.IntegrityError, match="só de acréscimo"):
        con.execute("update ciclos set fim_ms = 9999 where id = ?", (ciclo,))
    with pytest.raises(sqlite3.IntegrityError, match="só de acréscimo"):
        con.execute("update ciclos set numero = 7 where id = ?", (ciclo,))
    assert tuple(con.execute("select fim_ms, numero from ciclos where id = ?", (ciclo,)).fetchone()) == (
        2000,
        1,
    )


def test_proibido_apagar_decisao(con: sqlite3.Connection) -> None:
    _cadeia(con)
    with pytest.raises(sqlite3.IntegrityError, match="só de acréscimo"):
        con.execute("delete from decisoes")
    assert con.execute("select count(*) from decisoes").fetchone()[0] == 1


def test_proibido_fase_fora_da_lista(con: sqlite3.Connection) -> None:
    sessao = _sessao(con)
    ciclo = banco.gravar_ciclo(con, sessao, 1, 0, "rodando", "observando")
    captura = banco.gravar_captura(
        con,
        {
            "ciclo_id": ciclo,
            "arquivo": "c.jpg",
            "largura": 1,
            "altura": 1,
            "bytes": 1,
            "digest": "d",
            "enviada": 1,
        },
    )
    with pytest.raises(banco.RegistroError, match="CHECK"):
        banco.gravar_situacao(
            con,
            {
                "captura_id": captura,
                "descricao": "x",
                "fase": "cutscene",
                "aperto": 1,
                "confianca": 0.5,
                "latencia_ms": 1,
                "resposta_bruta": "{}",
            },
        )
    assert con.execute("select count(*) from situacoes").fetchone()[0] == 0


# ---- o que pode: preencher uma vez ----


def test_delete_recusado_em_toda_tabela_com_linhas(con: sqlite3.Connection) -> None:
    _cadeia(con)
    com_linhas = [t for t in TABELAS if con.execute(f"select count(*) from {t}").fetchone()[0] > 0]
    assert len(com_linhas) >= 6  # sessoes, ciclos, capturas, situacoes, decisoes, intervencoes
    for tabela in com_linhas:
        with pytest.raises(sqlite3.IntegrityError, match="só de acréscimo"):
            con.execute(f"delete from {tabela}")
    gatilhos = {r[0] for r in con.execute("select name from sqlite_master where type = 'trigger'")}
    assert all(f"{t}_sem_delete" in gatilhos and f"{t}_sem_update" in gatilhos for t in TABELAS)


def test_preencher_uma_vez_so_de_vazio_para_valor(con: sqlite3.Connection) -> None:
    _, _, intervencao = _cadeia(con)
    banco.preencher_uma_vez(con, "intervencoes", intervencao, {"resultado": "falhou"})
    with pytest.raises(banco.RegistroError, match="já preenchida"):
        banco.preencher_uma_vez(con, "intervencoes", intervencao, {"resultado": "confirmada"})
    with pytest.raises(banco.RegistroError, match="não se preenchem depois"):
        banco.preencher_uma_vez(con, "intervencoes", intervencao, {"alavanca": "pausa"})
    assert con.execute("select resultado from intervencoes").fetchone()[0] == "falhou"


def test_sem_funcao_de_alterar_ou_apagar() -> None:
    nomes = [n for n in dir(banco) if not n.startswith("_")]
    assert not any(
        n.startswith(("alterar", "apagar", "excluir", "atualizar", "update", "delete")) for n in nomes
    )


def test_intervencao_sem_decisao_e_impossivel(con: sqlite3.Connection) -> None:
    with pytest.raises(banco.RegistroError, match="FOREIGN KEY"):
        banco.gravar_intervencao(
            con,
            {
                "decisao_id": 999,
                "alavanca": "pausa",
                "parametros_json": "{}",
                "origem": "mestre",
                "estado_antes_json": "{}",
                "comando_ms": 1,
                "reversivel": 0,
            },
        )


def test_abrir_recusa_outra_migracao(tmp_path: Path) -> None:
    caminho = tmp_path / "velha.sqlite"
    c = sqlite3.connect(caminho)
    c.execute("pragma user_version = 7")
    c.close()
    with pytest.raises(banco.RegistroError, match="migração 0007"):
        banco.abrir(caminho)


def test_criar_recusa_existente(tmp_path: Path) -> None:
    caminho = tmp_path / "s.sqlite"
    banco.criar(caminho).close()
    with pytest.raises(FileExistsError):
        banco.criar(caminho)
    banco.abrir(caminho).close()


def test_id_de_sessao_e_ordenavel() -> None:
    a = banco.novo_id_sessao(1000)
    b = banco.novo_id_sessao(2000)
    assert a < b and len(a) == 13 + 1 + 6
