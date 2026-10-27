"""O aviso do que sai da máquina (card S3-05; caso E02; decisão DC-19).

Texto versionado. O aceite fica na configuração da máquina, com data, versão do texto e serviço; deixa de
ser perguntado enquanto os dois forem os mesmos. Cada sessão também grava o aceite na própria tabela.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

VERSAO_AVISO = "1"
TECLA_PAUSA = "Ctrl+Alt+P"

TEXTO_AVISO = (
    "Para o mestre enxergar o jogo, ele manda capturas da tela para fora.\n\n"
    "O que sai da sua máquina: imagens reduzidas da área do jogo, uma a cada poucos segundos quando a cena "
    "muda, e um resumo em texto do estado da partida (jogo, se está rodando, última ação do mestre).\n\n"
    'Para onde: o serviço de linguagem configurado, chamado "{servico}".\n\n'
    "O que nunca sai: o arquivo do jogo, a BIOS, os seus saves, qualquer coisa fora da janela do jogo.\n\n"
    f"Você pode pausar o mestre a qualquer momento com {TECLA_PAUSA}, e com a captura desligada nada sai. "
    "Este aviso volta a aparecer se o serviço mudar."
)


def texto(servico: str) -> str:
    return TEXTO_AVISO.format(servico=servico)


@dataclass(frozen=True)
class Aceite:
    aceito_em_utc: str
    aviso_versao: str
    servico: str
    aceito: bool


def arquivo_de_aceite(pasta: Path) -> Path:
    return pasta / "aceite.json"


def ler(pasta: Path) -> Aceite | None:
    caminho = arquivo_de_aceite(pasta)
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return Aceite(
            str(dados["aceito_em_utc"]),
            str(dados["aviso_versao"]),
            str(dados["servico"]),
            bool(dados["aceito"]),
        )
    except (ValueError, KeyError, TypeError):
        return None


def precisa_perguntar(pasta: Path, servico: str, versao: str = VERSAO_AVISO) -> bool:
    """Primeira vez, texto novo, serviço trocado ou recusa anterior: pergunta de novo (E02 A1)."""
    aceite = ler(pasta)
    if aceite is None or not aceite.aceito:
        return True
    return aceite.aviso_versao != versao or aceite.servico != servico


def registrar(pasta: Path, servico: str, aceito: bool, versao: str = VERSAO_AVISO) -> Aceite:
    pasta.mkdir(parents=True, exist_ok=True)
    aceite = Aceite(datetime.now(UTC).isoformat(timespec="seconds"), versao, servico, aceito)
    arquivo_de_aceite(pasta).write_text(
        json.dumps(aceite.__dict__, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return aceite
