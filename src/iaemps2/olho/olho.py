"""O olho inteiro (cards S2-01 a S2-03): da captura à situação validada, com as métricas.

Um ciclo de observação: capturar, comparar, e, se houver mudança, pedir ao serviço a situação e validar.
Resposta fora do formato: tenta uma vez mais com a mesma captura; persistindo, o ciclo fica sem situação.
"""

from __future__ import annotations

from dataclasses import dataclass

from iaemps2.olho.captura import Captura
from iaemps2.olho.diferenca import Veredito
from iaemps2.olho.situacao import Situacao, SituacaoInvalidaError, suspeita, validar
from iaemps2.ponte.protocolo import Status
from iaemps2.servicos.base import PedidoDescrever, Resposta, Servico


@dataclass(frozen=True)
class Observacao:
    captura: Captura
    veredito: Veredito
    situacao: Situacao | None
    resposta: Resposta | None
    suspeita: str | None
    tentativas: int
    invalida_motivo: str | None


def descrever(
    servico: Servico,
    captura: Captura,
    veredito: Veredito,
    *,
    jogo_titulo: str,
    jogo_serial: str,
    status: Status,
    velocidade: float = 1.0,
    ultima_alavanca: str | None = None,
    ultima_alavanca_ha_ms: int | None = None,
    anterior: Situacao | None = None,
) -> Observacao:
    """Pede a situação ao serviço e valida. Só chama o serviço se o veredito liberou a captura."""
    if not veredito.enviar:
        return Observacao(captura, veredito, None, None, None, 0, None)
    pedido = PedidoDescrever(
        jogo_titulo=jogo_titulo,
        jogo_serial=jogo_serial,
        status=status.name.lower(),
        velocidade=velocidade,
        ultima_alavanca=ultima_alavanca,
        ultima_alavanca_ha_ms=ultima_alavanca_ha_ms,
        situacao_anterior=anterior.model_dump(mode="json") if anterior else None,
        captura_jpeg=captura.jpeg,
    )
    ultimo_erro: str | None = None
    resposta: Resposta | None = None
    for tentativa in (1, 2):
        resposta = servico.descrever(pedido)
        try:
            situacao = validar(resposta.texto)
        except SituacaoInvalidaError as erro:
            ultimo_erro = str(erro)
            continue
        return Observacao(captura, veredito, situacao, resposta, suspeita(situacao, status), tentativa, None)
    return Observacao(captura, veredito, None, resposta, None, 2, ultimo_erro)
