"""O programa de terminal. Na fundação (card S0-01) só responde com a versão e procura o canal do emulador."""

from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Sequence
from pathlib import Path

from iaemps2 import __version__
from iaemps2.config import Config, ConfigInvalidaError, carregar

SAIDA_OK = 0
SAIDA_CONFIG = 1
SAIDA_SEM_CANAL = 2


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mestre",
        description="Mestre invisível por inteligência artificial para jogos de PlayStation 2 em emulador.",
    )
    parser.add_argument("--versao", action="store_true", help="mostra a versão e sai")
    parser.add_argument("--config", type=Path, default=None, help="caminho do config.toml")
    return parser


def canal_responde(config: Config) -> bool:
    """Tenta abrir o socket do canal oficial. Só diz se alguém escuta; o protocolo é do card S1-01."""
    try:
        with socket.create_connection(
            (config.canal.host, config.canal.porta), timeout=config.canal.tempo_limite_s
        ):
            return True
    except OSError:
        return False


def principal(argv: Sequence[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    if args.versao:
        print(f"mestre {__version__}")
        return SAIDA_OK
    try:
        config = carregar(args.config)
    except ConfigInvalidaError as erro:
        print(f"configuração inválida: {erro}", file=sys.stderr)
        return SAIDA_CONFIG
    if not canal_responde(config):
        print(
            f"canal não encontrado em {config.canal.host}:{config.canal.porta}. "
            "Abra o emulador com o canal oficial ligado (Configurações, Avançado, PINE) e carregue o jogo."
        )
        return SAIDA_SEM_CANAL
    print(f"canal encontrado em {config.canal.host}:{config.canal.porta}. A ponte entra no card S1-01.")
    return SAIDA_OK
