"""Card S0-04: integração contínua e log estruturado.

Critério de aceite: dado um push que quebra um cenário do simulador, quando o CI roda, então o build falha
e aponta o cenário; e nenhuma variável de serviço existe no ambiente do CI. A primeira metade é provada
no próprio GitHub; a segunda, aqui, em todo ambiente que não declare testes reais.
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path

import pytest

from iaemps2 import log
from iaemps2.config import VARIAVEL_CHAVE


def test_sem_chave_de_servico_no_ambiente_de_teste() -> None:
    if os.environ.get("IAEMPS2_TESTES_REAIS") == "1":
        pytest.skip("ambiente com testes reais pode ter chave")
    assert not os.environ.get(VARIAVEL_CHAVE), "chave de serviço no ambiente dos testes"


def test_fluxo_de_ci_roda_lint_tipos_e_testes() -> None:
    ci = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    texto = ci.read_text(encoding="utf-8")
    for passo in ("ruff check .", "ruff format --check .", "mypy", "pytest", "mestre --versao"):
        assert passo in texto, passo
    assert VARIAVEL_CHAVE not in texto


def test_linha_de_log_e_json_com_sessao_e_ciclo() -> None:
    saida = io.StringIO()
    log.configurar(saida)
    with log.contexto(sessao="0000000001000-abcdef", ciclo=12):
        log.evento("captura.enviada", bytes=46000, motivo="mudanca")
    linha = json.loads(saida.getvalue().strip())
    assert linha["evento"] == "captura.enviada"
    assert linha["sessao"] == "0000000001000-abcdef" and linha["ciclo"] == 12
    assert linha["bytes"] == 46000 and linha["motivo"] == "mudanca"
    assert linha["nivel"] == "info" and linha["ts"].endswith("+00:00")


def test_contexto_e_restaurado() -> None:
    saida = io.StringIO()
    log.configurar(saida)
    with log.contexto(sessao="s1"):
        with log.contexto(ciclo=3):
            log.evento("dentro")
        log.evento("fora_do_ciclo")
    log.evento("fora_da_sessao")
    linhas = [json.loads(linha) for linha in saida.getvalue().splitlines()]
    assert (linhas[0]["sessao"], linhas[0]["ciclo"]) == ("s1", 3)
    assert (linhas[1]["sessao"], linhas[1]["ciclo"]) == ("s1", None)
    assert (linhas[2]["sessao"], linhas[2]["ciclo"]) == (None, None)


def test_falha_sai_como_erro_com_excecao() -> None:
    saida = io.StringIO()
    logger = log.configurar(saida)
    try:
        raise ConnectionRefusedError("porta fechada")
    except ConnectionRefusedError:
        logger.exception("emulador.canal_caido", extra={"campos": {"porta": 28011}})
    linha = json.loads(saida.getvalue().strip())
    assert linha["nivel"] == "error" and linha["porta"] == 28011
    assert "ConnectionRefusedError" in linha["erro"]


def test_campo_com_nome_de_segredo_e_recusado() -> None:
    log.configurar(io.StringIO())
    with pytest.raises(log.CampoProibidoError):
        log.evento("servico.chamada", chave_servico="x")
    with pytest.raises(log.CampoProibidoError):
        log.evento("servico.chamada", api_token="x")


def test_nivel_de_log_respeitado() -> None:
    saida = io.StringIO()
    log.configurar(saida, nivel=logging.WARNING)
    log.evento("ignorado")
    log.falha("gravado")
    assert saida.getvalue().count("\n") == 1
