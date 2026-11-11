"""Ações de mundo declaradas no perfil de memória do jogo (card S8-03; casos H05 e H07; RN-01 a RN-04).

Uma ação de mundo é uma alavanca com parâmetros, igual às universais: variável alvo, operação, faixa por
intensidade, duração, volta e proibições. O perfil declara; a plataforma confere ao carregar (toda ação tem
volta, nenhuma pode derrotar o jogador sozinha, toda ação aponta para uma capacidade provada do catálogo do
S9-03) e recusa o que não passa. O catálogo só recebe o que passou; o perfil de outro jogo, ou de outra versão,
não entra.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from iaemps2.catalogo.catalogo import Alavanca, Faixa, Intensidade, Regras

PISO_DE_VIDA = (
    300  # abaixo disso a função de dano do jogo já não deixa a vida cair a zero sem sorte; nunca descer
)
INTENSIDADES = ("leve", "media", "forte")


class AcaoInvalidaError(ValueError):
    """A ação declarada no perfil não passa nas regras de mesa: não entra no catálogo."""


class Secao(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Alvo(Secao):
    """Onde a variável mora. 'fixo' = endereço estático; 'ponteiro' = endereço de um ponteiro mais um
    deslocamento; 'entidade' = vaga do vetor de personagens escolhida por regra, mais um deslocamento."""

    modo: Literal["fixo", "ponteiro", "entidade"]
    endereco: int = Field(ge=0, le=0x01FFFFFF)
    deslocamento: int = Field(default=0, ge=0, le=0xFFFF)
    tipo: Literal["u8", "u16", "s16", "u32"] = "s16"
    escala: int = Field(default=1, ge=1)  # valor real = bruto / escala (munição guarda balas × 8)
    regra: Literal["", "inimigo_mais_proximo"] = ""


class Faixas(Secao):
    leve: tuple[float, float]
    media: tuple[float, float]
    forte: tuple[float, float]

    def faixa(self, intensidade: Intensidade) -> Faixa:
        a, b = getattr(self, intensidade.value)
        return Faixa(a, b)


class Proibicoes(Secao):
    so_em_jogo: bool = True  # nunca em menu, vídeo, carregamento, morte ou tela de sistema (RN-03)
    fases: tuple[str, ...] = ()  # vazio = qualquer fase de jogo; senão só nestas (ex.: combate)
    piso: int = Field(default=0, ge=0)  # o valor nunca fica abaixo disto (RN-01: não derrota)
    nunca_sobe: bool = True  # ação de tirar: alvo acima do atual é descarte


class AcaoDeMundo(Secao):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    nome: str = Field(min_length=1, max_length=80)
    descricao: str = Field(min_length=1, max_length=200)
    capacidade: str = Field(min_length=1)  # id no bloco capacidades do perfil; tem de estar 'provada'
    alvo: Alvo
    operacao: Literal["fixar_fracao_da_maxima", "fixar_fracao_do_atual"]
    maxima: Alvo | None = None  # onde ler a máxima (fixar_fracao_da_maxima)
    fracao: Faixas
    duracao_s: Faixas
    volta: Literal["devolver_o_tirado"]  # a única volta que sobrevive a dano no meio do prazo
    proibicoes: Proibicoes = Field(default_factory=Proibicoes)
    motivo_padrao: str = Field(min_length=1, max_length=120)
    ativa: bool = True

    def alavanca(self, regras: Regras, intensidade: Intensidade) -> Alavanca:
        duracao = self.duracao_s.faixa(intensidade)
        return Alavanca(
            self.id,
            self.descricao,
            {
                "fracao": self.fracao.faixa(intensidade),
                "duracao_s": Faixa(
                    duracao.minimo,
                    round(duracao.minimo + (duracao.maximo - duracao.minimo) * regras.fator_de_duracao),
                ),
            },
            self.motivo_padrao,
            "H07",
            None,
            "devolve o que tirou no prazo; o jogador desfaz antes",
            mundo=self,
        )


@dataclass(frozen=True)
class Carga:
    acoes: tuple[AcaoDeMundo, ...]
    recusadas: tuple[tuple[str, str], ...]  # (id, motivo)
    origem: str  # arquivo, ou por que não há ações


def conferir(acao: AcaoDeMundo, capacidades: dict[str, str]) -> None:
    """Regras de mesa do H05: volta declarada, capacidade provada, faixas dentro de 0..1 e crescentes, piso."""
    estado = capacidades.get(acao.capacidade)
    if estado is None:
        raise AcaoInvalidaError(f"{acao.id}: capacidade '{acao.capacidade}' não está no catálogo do jogo")
    if estado != "provada":
        raise AcaoInvalidaError(f"{acao.id}: capacidade '{acao.capacidade}' está '{estado}', não 'provada'")
    for nome, faixas in (("fracao", acao.fracao), ("duracao_s", acao.duracao_s)):
        for intensidade in INTENSIDADES:
            a, b = getattr(faixas, intensidade)
            if not a <= b:
                raise AcaoInvalidaError(f"{acao.id}: {nome}.{intensidade} tem mínimo acima do máximo")
            if nome == "fracao" and not (a > 0 and b <= 1):
                raise AcaoInvalidaError(f"{acao.id}: fracao.{intensidade} fora de (0, 1]")
            if nome == "duracao_s" and not (a >= 1 and b <= 120):
                raise AcaoInvalidaError(f"{acao.id}: duracao_s.{intensidade} fora de [1, 120]")
    if acao.operacao == "fixar_fracao_da_maxima" and acao.maxima is None:
        raise AcaoInvalidaError(f"{acao.id}: fixar_fracao_da_maxima exige onde ler a máxima")
    if acao.alvo.modo == "entidade" and not acao.alvo.regra:
        raise AcaoInvalidaError(f"{acao.id}: alvo por entidade exige a regra de escolha")
    if acao.id == "vida_do_jogador" and acao.proibicoes.piso < PISO_DE_VIDA:
        raise AcaoInvalidaError(f"{acao.id}: piso {acao.proibicoes.piso} abaixo de {PISO_DE_VIDA} (RN-01)")


def carregar_perfil(caminho: Path, serial: str, crc: str) -> Carga:
    """Lê o perfil do jogo e devolve as ações que passam. Serial ou soma diferente: nenhuma ação (H06)."""
    if not caminho.is_file():
        return Carga((), (), f"sem perfil em {caminho}")
    perfil = json.loads(caminho.read_text(encoding="utf-8"))
    jogo = perfil.get("jogo", {})
    if jogo.get("serial") != serial or str(jogo.get("crc", "")).lower() != crc.lower():
        return Carga((), (), f"perfil de {jogo.get('serial')} {jogo.get('crc')}, não de {serial} {crc}")
    capacidades = {c["id"]: c["estado"] for c in perfil.get("capacidades", {}).get("lista", [])}
    aceitas: list[AcaoDeMundo] = []
    recusadas: list[tuple[str, str]] = []
    for dados in perfil.get("acoes_de_mundo", []):
        try:
            acao = AcaoDeMundo.model_validate(dados)
        except ValidationError as erro:
            recusadas.append((str(dados.get("id", "?")), "; ".join(e["msg"] for e in erro.errors())))
            continue
        if not acao.ativa:
            recusadas.append((acao.id, "desligada no perfil"))
            continue
        try:
            conferir(acao, capacidades)
        except AcaoInvalidaError as erro:
            recusadas.append((acao.id, str(erro)))
            continue
        aceitas.append(acao)
    return Carga(tuple(aceitas), tuple(recusadas), str(caminho))


def localizar(pasta: Path, serial: str) -> Path:
    return pasta / f"{serial}.json"
