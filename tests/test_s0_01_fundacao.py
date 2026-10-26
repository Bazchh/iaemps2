"""Card S0-01: repositório, pacotes e configuração.

Critério de aceite: dado um clone limpo, quando se instala e roda o ponto de entrada sem emulador,
então ele sobe, informa "canal não encontrado" e encerra limpo, sem traceback.
"""

from __future__ import annotations

import importlib
import socket
from pathlib import Path
from typing import Any

import pytest

from iaemps2 import __version__, cli, config

PACOTES = ["ponte", "olho", "mestre", "catalogo", "sessao", "registro", "servicos", "simulador", "bancada"]


def test_os_nove_pacotes_existem() -> None:
    for nome in PACOTES:
        importlib.import_module(f"iaemps2.{nome}")


def test_versao(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.principal(["--versao"]) == cli.SAIDA_OK
    assert capsys.readouterr().out.strip() == f"mestre {__version__}"


def test_sem_emulador_encerra_limpo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def recusa(*_a: Any, **_k: Any) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(socket, "create_connection", recusa)
    monkeypatch.chdir(tmp_path)  # sem config.toml por perto
    monkeypatch.delenv(config.VARIAVEL_CONFIG, raising=False)
    assert cli.principal([]) == cli.SAIDA_SEM_CANAL
    saida = capsys.readouterr()
    assert "canal não encontrado em 127.0.0.1:28011" in saida.out
    assert "Traceback" not in saida.err


def test_padroes_da_config() -> None:
    c = config.Config()
    assert c.canal.porta == 28011
    assert c.slots_reservados.todos() == list(range(90, 100))
    assert c.captura.largura_px == 640
    assert c.servico.ativo == "falso"
    assert c.sessoes.caminho().name == "sessoes"


def test_config_de_arquivo(tmp_path: Path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text(
        "[canal]\nporta = 28012\n[slots_reservados]\ninicio = 95\nfim = 99\n", encoding="utf-8"
    )
    c = config.carregar(arquivo)
    assert c.canal.porta == 28012
    assert c.slots_reservados.todos() == [95, 96, 97, 98, 99]


def test_slots_do_jogador_sao_recusados(tmp_path: Path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("[slots_reservados]\ninicio = 5\nfim = 12\n", encoding="utf-8")
    with pytest.raises(config.ConfigInvalidaError, match="DC-15"):
        config.carregar(arquivo)


def test_chave_no_toml_e_recusada(tmp_path: Path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text('[servico]\nativo = "falso"\nchave = "abc"\n', encoding="utf-8")
    with pytest.raises(config.ConfigInvalidaError, match=config.VARIAVEL_CHAVE):
        config.carregar(arquivo)


def test_campo_desconhecido_e_recusado(tmp_path: Path) -> None:
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("[canal]\nportas = 1\n", encoding="utf-8")
    with pytest.raises(config.ConfigInvalidaError):
        config.carregar(arquivo)


def test_chave_vem_so_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(config.VARIAVEL_CHAVE, raising=False)
    assert config.Config.chave_servico() is None
    monkeypatch.setenv(config.VARIAVEL_CHAVE, "  x  ")
    assert config.Config.chave_servico() == "x"
