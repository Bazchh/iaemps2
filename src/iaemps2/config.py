"""Configuração do mestre: um arquivo TOML, validado, com a chave do serviço só por variável de ambiente.

Ordem de busca do arquivo: caminho passado na linha de comando, variável IAEMPS2_CONFIG, config.toml
na pasta atual. Sem arquivo, valem os padrões abaixo, que são os do Blueprint (capítulo 5 e cards S0-01, S1-03).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

VARIAVEL_CONFIG = "IAEMPS2_CONFIG"
VARIAVEL_CHAVE = "IAEMPS2_CHAVE_SERVICO"
SLOTS_DO_JOGADOR = range(1, 11)


class Secao(BaseModel):
    """Toda seção recusa campo desconhecido: erro de digitação no TOML é erro, não silêncio."""

    model_config = ConfigDict(extra="forbid")


class Canal(Secao):
    host: str = "127.0.0.1"
    porta: int = Field(default=28011, ge=1, le=65535)
    tempo_limite_s: float = Field(default=3.0, gt=0)
    espera_jogo_s: float = Field(default=90.0, gt=0)


class Sessoes(Secao):
    pasta: str = ""

    def caminho(self) -> Path:
        if self.pasta:
            return Path(self.pasta).expanduser()
        return Path.home() / "IAEmPS2" / "sessoes"


class SlotsReservados(Secao):
    inicio: int = Field(default=90, ge=0, le=255)
    fim: int = Field(default=99, ge=0, le=255)

    @model_validator(mode="after")
    def _fora_dos_slots_do_jogador(self) -> SlotsReservados:
        if self.fim < self.inicio:
            raise ValueError("slots_reservados: fim menor que inicio")
        if any(s in SLOTS_DO_JOGADOR for s in range(self.inicio, self.fim + 1)):
            raise ValueError("slots_reservados: os slots 1 a 10 são do jogador e nunca do mestre (DC-15)")
        return self

    def todos(self) -> list[int]:
        return list(range(self.inicio, self.fim + 1))


class Emulador(Secao):
    pasta_estados: str = ""  # vazio = %LOCALAPPDATA%/Programs/PCSX2/sstates (instalação portátil do cliente)

    def caminho_estados(self) -> Path:
        if self.pasta_estados:
            return Path(self.pasta_estados).expanduser()
        base = os.environ.get("LOCALAPPDATA")
        raiz = Path(base) if base else Path.home() / "AppData" / "Local"
        return raiz / "Programs" / "PCSX2" / "sstates"


class Captura(Secao):
    largura_px: int = Field(default=640, ge=160, le=1920)
    qualidade_jpeg: int = Field(default=80, ge=30, le=95)
    limiar_diferenca: float = Field(default=0.04, ge=0, le=1)
    intervalo_ms: int = Field(default=2000, ge=250)


class Servico(Secao):
    ativo: str = "falso"
    teto_custo_sessao: float = Field(default=0.0, ge=0)


class Config(Secao):
    canal: Canal = Field(default_factory=Canal)
    sessoes: Sessoes = Field(default_factory=Sessoes)
    slots_reservados: SlotsReservados = Field(default_factory=SlotsReservados)
    emulador: Emulador = Field(default_factory=Emulador)
    captura: Captura = Field(default_factory=Captura)
    servico: Servico = Field(default_factory=Servico)

    @staticmethod
    def chave_servico() -> str | None:
        """A chave nunca sai de uma variável de ambiente; nunca é gravada nem registrada."""
        valor = os.environ.get(VARIAVEL_CHAVE, "").strip()
        return valor or None


class ConfigInvalidaError(ValueError):
    """O arquivo de configuração existe mas não serve."""


def localizar(caminho: Path | None = None) -> Path | None:
    """Devolve o arquivo de configuração a usar, ou None para valer os padrões."""
    if caminho is not None:
        return caminho
    da_variavel = os.environ.get(VARIAVEL_CONFIG, "").strip()
    if da_variavel:
        return Path(da_variavel).expanduser()
    local = Path("config.toml")
    return local if local.is_file() else None


def carregar(caminho: Path | None = None) -> Config:
    arquivo = localizar(caminho)
    if arquivo is None:
        return Config()
    if not arquivo.is_file():
        raise ConfigInvalidaError(f"configuração não encontrada: {arquivo}")
    try:
        dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as erro:
        raise ConfigInvalidaError(f"{arquivo}: TOML inválido: {erro}") from erro
    if "chave" in str(dados).lower():
        raise ConfigInvalidaError(
            f"{arquivo}: chave de serviço no TOML; ela vai só na variável {VARIAVEL_CHAVE}"
        )
    try:
        return Config.model_validate(dados)
    except ValueError as erro:
        raise ConfigInvalidaError(f"{arquivo}: {erro}") from erro
