"""O catálogo de alavancas, tons e intensidades (card S3-02; casos C01 e D01; decisões DC-15 e DC-17).

A lista fechada do que o mestre pode fazer, com faixas, disponibilidade, motivo padrão e versão. O catálogo
vai inteiro no pedido de decisão; o serviço só escolhe o que está nele. Mudou algo (alavanca indisponível,
emulador reiniciado), nasce uma versão nova, gravada. Ações de mundo (fase 2) entram como linhas iguais.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from iaemps2.ponte.emulador import Capacidades

NADA = "nada"
FALHAS_PARA_INDISPONIBILIZAR = 3


class Tom(StrEnum):
    PROTETOR = "protetor"
    IMPREVISIVEL = "imprevisivel"
    IMPLACAVEL = "implacavel"


class Intensidade(StrEnum):
    LEVE = "leve"
    MEDIA = "media"
    FORTE = "forte"


TOM_PADRAO = Tom.IMPREVISIVEL
INTENSIDADE_PADRAO = Intensidade.MEDIA

DESCRICAO_DO_TOM: dict[Tom, str] = {
    Tom.PROTETOR: "Prefere trégua: câmera lenta e recarga quando o aperto sobe; turbo só em exploração longa. Motivos acolhedores.",
    Tom.IMPREVISIVEL: "Sem preferência; varia; pode apertar ou aliviar na mesma situação. Motivos curtos e teatrais.",
    Tom.IMPLACAVEL: "Prefere apertar: turbo em combate, recarga só após morte. Nunca cruza a regra 'não derrota'. Motivos secos.",
}


@dataclass(frozen=True)
class Regras:
    """O que a intensidade fixa (DC-17)."""

    intervalo_minimo_s: int
    salvar_a_cada_s: int
    fator_de_duracao: float  # 1.0 = faixa completa; 0.5 = até a metade
    turbo: bool
    pausa_maxima_s: int


REGRAS: dict[Intensidade, Regras] = {
    Intensidade.LEVE: Regras(60, 90, 0.5, False, 3),
    Intensidade.MEDIA: Regras(30, 60, 1.0, True, 4),
    Intensidade.FORTE: Regras(15, 45, 1.0, True, 6),
}


@dataclass(frozen=True)
class Faixa:
    minimo: float
    maximo: float

    def contem(self, valor: float) -> bool:
        return self.minimo <= valor <= self.maximo

    def como_json(self) -> list[float]:
        return [self.minimo, self.maximo]


@dataclass(frozen=True)
class Alavanca:
    nome: str
    descricao: str
    parametros: dict[str, Faixa]
    motivo_padrao: str
    executa_por: str  # caso de uso: A03, A04, A05, A06, C03, H07
    precisa: str | None  # capacidade da extensão: pausa | velocidade | None
    reversao: str
    disponivel: bool = True
    falhas_seguidas: int = 0

    def como_json(self) -> dict[str, Any]:
        return {
            "alavanca": self.nome,
            "descricao": self.descricao,
            "disponivel": self.disponivel,
            "parametros": {k: v.como_json() for k, v in self.parametros.items()},
        }


def universais(regras: Regras) -> list[Alavanca]:
    """O catálogo universal da fase 1 (contrato 3 do Blueprint), já com as faixas da intensidade."""
    f = regras.fator_de_duracao
    return [
        Alavanca(
            "pausa",
            "Congela o jogo por alguns segundos: pausa dramática antes de algo acontecer.",
            {"duracao_s": Faixa(1, regras.pausa_maxima_s)},
            "Um instante de suspense.",
            "A03",
            "pausa",
            "retomar na hora",
        ),
        Alavanca(
            "camera_lenta",
            "Desacelera o jogo por alguns segundos: fôlego num aperto ou peso num momento.",
            {"escalar": Faixa(0.5, 0.8), "duracao_s": Faixa(3, round(3 + 7 * f))},
            "O tempo pesa.",
            "A04",
            "velocidade",
            "volta ao normal",
        ),
        Alavanca(
            "turbo",
            "Acelera o jogo por alguns segundos: aperta o ritmo num trecho morno.",
            {"escalar": Faixa(1.5, 2.0), "duracao_s": Faixa(3, round(3 + 7 * f))},
            "Sem tempo a perder.",
            "A04",
            "velocidade",
            "volta ao normal",
            disponivel=regras.turbo,
        ),
        Alavanca(
            "salvar_estado",
            "Guarda o momento num slot do mestre, para uma volta futura.",
            {},
            "Um ponto de volta.",
            "A05",
            None,
            "não se aplica",
        ),
        Alavanca(
            "recarregar",
            "Devolve o jogo a um momento recente guardado pelo mestre: a cena de novo.",
            {"slot": Faixa(90, 99)},
            "A cena de novo.",
            "A06",
            None,
            "recarregar o slot de volta",
        ),
        Alavanca(
            NADA,
            "Não agir: observar e deixar o jogador seguir.",
            {},
            "Nada a fazer agora.",
            "C03",
            None,
            "não se aplica",
        ),
    ]


@dataclass(frozen=True)
class Catalogo:
    versao: int
    tom: Tom
    intensidade: Intensidade
    modo: str  # completo | reduzido
    alavancas: tuple[Alavanca, ...]
    motivo_da_versao: str
    slots_com_contexto: tuple[int, ...] = field(default_factory=tuple)

    @property
    def regras(self) -> Regras:
        return REGRAS[self.intensidade]

    def alavanca(self, nome: str) -> Alavanca | None:
        return next((a for a in self.alavancas if a.nome == nome), None)

    def disponiveis(self) -> list[str]:
        return [a.nome for a in self.alavancas if a.disponivel]

    def como_json(self) -> str:
        return json.dumps(
            {
                "versao": self.versao,
                "tom": self.tom.value,
                "intensidade": self.intensidade.value,
                "modo": self.modo,
                "intervalo_minimo_s": self.regras.intervalo_minimo_s,
                "alavancas": [self._json_alavanca(a) for a in self.alavancas],
            },
            ensure_ascii=False,
        )

    def _json_alavanca(self, a: Alavanca) -> dict[str, Any]:
        dados = a.como_json()
        if a.nome == "recarregar":
            dados["parametros"] = {"slot": list(self.slots_com_contexto)}
            dados["disponivel"] = a.disponivel and bool(self.slots_com_contexto)
        return dados

    def para_o_pedido(self) -> list[dict[str, Any]]:
        """O que vai no pedido de decisão (contrato 2): nome, disponibilidade e faixas; o motivo padrão não."""
        return [self._json_alavanca(a) for a in self.alavancas]


def montar(
    capacidades: Capacidades,
    tom: Tom = TOM_PADRAO,
    intensidade: Intensidade = INTENSIDADE_PADRAO,
    slots_com_contexto: tuple[int, ...] = (),
    versao: int = 1,
    motivo: str = "abertura",
) -> Catalogo:
    """D01: lista universal, disponibilidade pelas capacidades do emulador (A07), faixas pela intensidade."""
    regras = REGRAS[intensidade]
    alavancas = []
    for a in universais(regras):
        disponivel = a.disponivel
        if a.precisa == "pausa":
            disponivel = disponivel and capacidades.pausa
        if a.precisa == "velocidade":
            disponivel = disponivel and capacidades.velocidade
        alavancas.append(replace(a, disponivel=disponivel))
    return Catalogo(versao, tom, intensidade, capacidades.modo, tuple(alavancas), motivo, slots_com_contexto)


def registrar_falha(catalogo: Catalogo, nome: str) -> tuple[Catalogo, bool]:
    """Uma falha de execução. Três seguidas tiram a alavanca do catálogo com versão nova (D01 A2, D02 E1).
    Devolve o catálogo (novo ou o mesmo) e se houve versão nova."""
    a = catalogo.alavanca(nome)
    if a is None or not a.disponivel:
        return catalogo, False
    falhas = a.falhas_seguidas + 1
    if falhas < FALHAS_PARA_INDISPONIBILIZAR:
        novas = tuple(replace(x, falhas_seguidas=falhas) if x.nome == nome else x for x in catalogo.alavancas)
        return replace(catalogo, alavancas=novas), False
    novas = tuple(
        replace(x, disponivel=False, falhas_seguidas=falhas) if x.nome == nome else x
        for x in catalogo.alavancas
    )
    return replace(
        catalogo,
        versao=catalogo.versao + 1,
        alavancas=novas,
        motivo_da_versao=f"{nome} indisponível por falhas",
    ), True


def registrar_sucesso(catalogo: Catalogo, nome: str) -> Catalogo:
    a = catalogo.alavanca(nome)
    if a is None or a.falhas_seguidas == 0:
        return catalogo
    novas = tuple(replace(x, falhas_seguidas=0) if x.nome == nome else x for x in catalogo.alavancas)
    return replace(catalogo, alavancas=novas)


def com_slots(catalogo: Catalogo, slots_com_contexto: tuple[int, ...]) -> Catalogo:
    """Os slots que têm contexto mudam a cada salvamento; não é versão nova, é estado da fila (A05)."""
    return replace(catalogo, slots_com_contexto=tuple(slots_com_contexto))


def nova_versao(catalogo: Catalogo, capacidades: Capacidades, motivo: str) -> Catalogo:
    """Emulador reiniciado ou capacidades mudaram: catálogo refeito com versão seguinte (D01 A2)."""
    return montar(
        capacidades,
        catalogo.tom,
        catalogo.intensidade,
        catalogo.slots_com_contexto,
        catalogo.versao + 1,
        motivo,
    )
