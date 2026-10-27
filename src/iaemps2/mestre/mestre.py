"""O mestre decide (card S3-03; caso C02): monta o pedido, pede ao serviço, confere.

O serviço escolhe; a plataforma confere contra o catálogo (aqui) e contra a situação atual (quem executa).
Resposta inválida é tratada como "nada" com origem 'falha', nunca inventada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from iaemps2.catalogo.catalogo import DESCRICAO_DO_TOM, NADA, Catalogo, Tom
from iaemps2.mestre.decisao import DecisaoInvalidaError, Veredito, conferir, validar_resposta
from iaemps2.mestre.memoria import MemoriaCurta
from iaemps2.olho.situacao import Situacao
from iaemps2.servicos.base import Resposta, Servico

JANELA_DA_MORTE_MS = 180_000  # morte mais velha que isso não pede recarga
LIMITE_MOTIVO = 120


@dataclass(frozen=True)
class PedidoDecidir:
    """Contrato 2 do Blueprint: o que vai ao serviço para virar decisão."""

    tom: str
    intensidade: str
    situacao: dict[str, Any]
    estado: dict[str, Any]  # status, velocidade
    catalogo: list[dict[str, Any]]
    memoria: dict[str, Any]
    proxima_janela_ms: int
    jogo_titulo: str = ""

    def instrucao(self) -> str:
        return (
            "Você é o mestre invisível de um jogo de PlayStation 2: um diretor que molda o ritmo da partida "
            "sem jogar por ninguém. Dada a situação, escolha UMA alavanca do catálogo, ou 'nada', com "
            "parâmetros dentro das faixas, e um motivo em UMA frase de até "
            f"{LIMITE_MOTIVO} caracteres, em português do Brasil, que explique sem instruir o jogador e "
            "sem revelar o que ele ainda não viu. Responda SÓ com JSON, sem cerca de código, exatamente: "
            '{"alavanca": nome, "parametros": {nome: valor}, "motivo": frase}. '
            "Regras de mesa: dificulte, nunca derrote; não agir é uma escolha válida e frequente; não repita a "
            "mesma alavanca várias vezes seguidas; respeite o que o jogador desfez. "
            f"Tom '{self.tom}': {DESCRICAO_DO_TOM[Tom(self.tom)]} Intensidade: {self.intensidade}. "
            + (f"Jogo: {self.jogo_titulo}. " if self.jogo_titulo else "")
            + "Situação: "
            + json.dumps(self.situacao, ensure_ascii=False)
            + ". Estado do emulador: "
            + json.dumps(self.estado, ensure_ascii=False)
            + ". Catálogo (só o disponível pode ser escolhido; faixas são [mínimo, máximo]): "
            + json.dumps(self.catalogo, ensure_ascii=False)
            + ". Memória recente: "
            + json.dumps(self.memoria, ensure_ascii=False)
            + self._aviso_de_morte()
            + (
                f". Próxima janela de intervenção em {self.proxima_janela_ms} ms: se for maior que zero, escolha 'nada'."
                if self.proxima_janela_ms > 0
                else "."
            )
        )

    def _aviso_de_morte(self) -> str:
        """Morte recente com a cena de volta e um estado guardado: recarregar é a resposta esperada; no tom
        implacável, obrigatória. Sem isso o serviço ignorava a morte e só mexia na velocidade."""
        mortes = [m["ha_ms"] for m in self.memoria.get("marcos", []) if m.get("tipo") == "morte"]
        recarregar = next((a for a in self.catalogo if a.get("alavanca") == "recarregar"), None)
        if (
            not mortes
            or min(mortes) > JANELA_DA_MORTE_MS
            or not recarregar
            or not recarregar.get("disponivel")
        ):
            return ""
        if self.tom == Tom.IMPLACAVEL.value:
            return (
                f". O jogador morreu há {min(mortes) // 1000} s e a cena voltou: no tom implacável você DEVE escolher"
                " 'recarregar' agora, com o motivo seco"
            )
        return (
            f". O jogador morreu há {min(mortes) // 1000} s e a cena voltou: 'recarregar' um estado guardado é a"
            " resposta esperada, salvo motivo forte"
        )


@dataclass(frozen=True)
class Decidido:
    veredito: Veredito
    pedido: PedidoDecidir
    resposta: Resposta | None
    pedido_bruto: str = field(repr=False, default="")


def montar_pedido(
    *,
    catalogo: Catalogo,
    situacao: Situacao,
    status: str,
    velocidade: float,
    memoria: MemoriaCurta,
    proxima_janela_ms: int,
    jogo_titulo: str = "",
) -> PedidoDecidir:
    return PedidoDecidir(
        tom=catalogo.tom.value,
        intensidade=catalogo.intensidade.value,
        situacao=situacao.model_dump(mode="json"),
        estado={"status": status, "velocidade": velocidade},
        catalogo=catalogo.para_o_pedido(),
        memoria=memoria.como_json(),
        proxima_janela_ms=proxima_janela_ms,
        jogo_titulo=jogo_titulo,
    )


def decidir(
    servico: Servico,
    pedido: PedidoDecidir,
    catalogo: Catalogo,
    situacao: Situacao,
    aperto_dos_slots: dict[int, int],
) -> Decidido:
    """C02 passos 1 a 3. A releitura (passo 4) é de quem executa, com o emulador na mão."""
    if pedido.proxima_janela_ms > 0:
        return Decidido(
            Veredito(NADA, {}, f"Próxima janela em {pedido.proxima_janela_ms // 1000} s.", "padrao", "ritmo"),
            pedido,
            None,
            pedido.instrucao(),
        )
    resposta = servico.decidir(pedido)
    try:
        decisao = validar_resposta(resposta.texto)
    except DecisaoInvalidaError as erro:
        return Decidido(
            Veredito(NADA, {}, "", "ausente", "falha", f"resposta inválida: {erro}"),
            pedido,
            resposta,
            pedido.instrucao(),
        )
    return Decidido(
        conferir(decisao, catalogo, situacao, aperto_dos_slots), pedido, resposta, pedido.instrucao()
    )
