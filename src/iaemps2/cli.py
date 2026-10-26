"""O programa de terminal. Até o card S1-02: versão, e sondar o canal até o jogo rodar, identificando jogo e modo."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from iaemps2 import __version__
from iaemps2.config import Config, ConfigInvalidaError, carregar, carregar_env
from iaemps2.ponte import emulador
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.ponte.protocolo import Status

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


def sondar_canal(config: Config) -> str | None:
    """Conecta ao canal oficial, espera o jogo rodar e devolve uma linha de estado; None se não há canal."""
    cliente = Cliente(config.canal.host, config.canal.porta, config.canal.tempo_limite_s)
    try:
        cliente.conectar()
        versao = cliente.versao()
        status = cliente.esperar_jogo(limite_s=config.canal.espera_jogo_s)
        if status != Status.RODANDO:
            return f"{versao}: nenhum jogo rodando (status {status.name.lower()}) após {config.canal.espera_jogo_s:.0f} s."
        jogo = emulador.identificar(cliente)
        ident = jogo.identificacao
        quem = f"{ident.titulo} ({ident.serial}, {ident.crc}, versão {ident.versao_jogo})"
        if not jogo.identificado:
            quem = f"{ident.titulo} (sem serial: não identificado)"
        return f"{versao}: {quem}, rodando, modo {jogo.modo}."
    except CanalError as erro:
        if erro.classe == "porta_fechada":
            return None
        return f"canal com problema ({erro.classe}): {erro.detalhe}"
    except ComandoFalhouError as erro:
        return f"o emulador recusou um comando: {erro}"
    finally:
        cliente.fechar()


def principal(argv: Sequence[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    if args.versao:
        print(f"mestre {__version__}")
        return SAIDA_OK
    carregar_env()
    try:
        config = carregar(args.config)
    except ConfigInvalidaError as erro:
        print(f"configuração inválida: {erro}", file=sys.stderr)
        return SAIDA_CONFIG
    estado = sondar_canal(config)
    if estado is None:
        print(
            f"canal não encontrado em {config.canal.host}:{config.canal.porta}. "
            "Abra o emulador com o canal oficial ligado (Configurações, Avançado, PINE) e carregue o jogo."
        )
        return SAIDA_SEM_CANAL
    print(f"canal em {config.canal.host}:{config.canal.porta}: {estado}")
    return SAIDA_OK
