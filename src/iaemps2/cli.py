"""O programa de terminal. `mestre` abre a sessão sobre o jogo que está rodando e fica até o jogador encerrar."""

from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from iaemps2 import __version__, log
from iaemps2.catalogo import catalogo as cat
from iaemps2.config import Config, ConfigInvalidaError, carregar, carregar_env
from iaemps2.ponte import emulador
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.ponte.protocolo import Status

SAIDA_OK = 0
SAIDA_CONFIG = 1
SAIDA_SEM_CANAL = 2
SAIDA_RECUSADA = 3


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mestre",
        description="Mestre invisível por inteligência artificial para jogos de PlayStation 2 em emulador.",
    )
    parser.add_argument("--versao", action="store_true", help="mostra a versão e sai")
    parser.add_argument("--config", type=Path, default=None, help="caminho do config.toml")
    parser.add_argument(
        "--sondar", action="store_true", help="só sonda o canal e identifica o jogo; não abre sessão"
    )
    parser.add_argument("--tom", choices=[t.value for t in cat.Tom], default=cat.TOM_PADRAO.value)
    parser.add_argument(
        "--intensidade", choices=[i.value for i in cat.Intensidade], default=cat.INTENSIDADE_PADRAO.value
    )
    parser.add_argument(
        "--encerrar-apos",
        type=float,
        default=None,
        metavar="S",
        help="encerra a sessão sozinha após S segundos",
    )
    parser.add_argument("--sem-overlay", action="store_true", help="roda sem painel (só terminal e registro)")
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


def rodar_sessao(config: Config, args: argparse.Namespace) -> int:
    """E01 a E04: abre a sessão, roda o laço numa thread de trabalho e o overlay na principal."""
    from iaemps2.sessao.abrir import AberturaRecusadaError, abrir
    from iaemps2.sessao.ciclo import PainelSilencioso, texto_do_resumo

    tom, intensidade = cat.Tom(args.tom), cat.Intensidade(args.intensidade)
    if args.sem_overlay:
        painel_silencioso = PainelSilencioso()
        try:
            sessao = abrir(
                config,
                painel_silencioso,
                pedir_aceite=_aceite_no_terminal,
                tom=tom,
                intensidade=intensidade,
                encerrar_apos_s=args.encerrar_apos,
            )
        except AberturaRecusadaError as erro:
            print(f"sessão não aberta: {erro}")
            return SAIDA_RECUSADA
        print(
            f"sessão {sessao.sessao_id} aberta: {sessao.jogo.identificacao.titulo}, modo {sessao.jogo.modo}. Ctrl+C encerra."
        )
        try:
            sessao.rodar()
        except KeyboardInterrupt:
            sessao.gesto("encerrar")
            sessao.passo()
        print(texto_do_resumo(sessao.resumo()))
        return SAIDA_OK

    from iaemps2.sessao.overlay import Overlay, pedir_aceite

    try:
        sessao = abrir(
            config,
            PainelSilencioso(),
            pedir_aceite=pedir_aceite,
            tom=tom,
            intensidade=intensidade,
            encerrar_apos_s=args.encerrar_apos,
        )
    except AberturaRecusadaError as erro:
        print(f"sessão não aberta: {erro}")
        return SAIDA_RECUSADA
    overlay = Overlay(sessao.gesto, agora_ms=sessao.contador.agora_ms)
    overlay.painel = sessao.painel.painel  # o mesmo dado: o laço escreve, o Tk desenha
    sessao.painel = overlay
    print(f"sessão {sessao.sessao_id} aberta: {sessao.jogo.identificacao.titulo}, modo {sessao.jogo.modo}.")
    trabalho = threading.Thread(target=sessao.rodar, name="laco", daemon=True)
    trabalho.start()
    try:
        overlay.root.mainloop()
    except KeyboardInterrupt:
        sessao.gesto("encerrar")
    sessao.encerrada.wait(timeout=15)
    overlay.fechar()
    trabalho.join(timeout=5)
    print(texto_do_resumo(sessao.resumo()))
    return SAIDA_OK


def _aceite_no_terminal(texto: str) -> bool:
    print(texto)
    resposta = input("Aceitar e abrir a sessão? [s/N] ").strip().lower()
    return resposta in ("s", "sim")


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
    log.configurar()
    estado = sondar_canal(config)
    if estado is None:
        print(
            f"canal não encontrado em {config.canal.host}:{config.canal.porta}. "
            "Abra o emulador com o canal oficial ligado (Configurações, Avançado, PINE) e carregue o jogo."
        )
        return SAIDA_SEM_CANAL
    print(f"canal em {config.canal.host}:{config.canal.porta}: {estado}")
    if args.sondar or not estado.endswith("."):
        return SAIDA_OK
    return rodar_sessao(config, args)
