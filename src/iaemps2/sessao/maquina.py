"""A máquina de estados da sessão (card S3-01; Blueprint, capítulo 4).

Uma função pura recebe o estado atual e um evento e devolve o novo estado e os efeitos. Nenhum outro lugar
do código muda o estado da sessão. A tabela abaixo é a do Blueprint, inteira; qualquer par fora dela é
recusado com TransicaoInvalidaError e nada é gravado. Sem rede, sem emulador, sem relógio: só estado e evento.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Estado(StrEnum):
    ABRINDO = "abrindo"
    OBSERVANDO = "observando"
    DECIDINDO = "decidindo"
    EXECUTANDO = "executando"
    BLOQUEADA = "bloqueada"
    PAUSADA_JOGADOR = "pausada_jogador"
    SILENCIADA = "silenciada"
    ENCERRADA = "encerrada"


class Evento(StrEnum):
    PRONTO = "pronto"
    CAPTURA_SEM_MUDANCA = "captura_sem_mudanca"
    SITUACAO_OK = "situacao_ok"
    SITUACAO_FORA_DE_JOGO = "situacao_fora_de_jogo"
    SITUACAO_INVALIDA = "situacao_invalida"
    DECISAO_VALIDADA = "decisao_validada"
    DECISAO_NADA = "decisao_nada"
    DECISAO_DESCARTADA = "decisao_descartada"
    INTERVALO_NAO_VENCEU = "intervalo_nao_venceu"
    EXECUCAO_CONFIRMADA = "execucao_confirmada"
    EXECUCAO_FALHOU = "execucao_falhou"
    SITUACAO_MUDOU = "situacao_mudou"
    JOGADOR_PAUSOU = "jogador_pausou"
    JOGADOR_RETOMOU = "jogador_retomou"
    JOGADOR_REVERTEU = "jogador_reverteu"
    JOGADOR_ENCERROU = "jogador_encerrou"
    FALHA_SERVICO = "falha_servico"
    FALHA_EMULADOR = "falha_emulador"
    FALHA_REGISTRO = "falha_registro"
    RECUPEROU = "recuperou"
    FALHA_PROLONGADA = "falha_prolongada"  # acima do limite de falhas seguidas: o mestre se pausa
    CENA_VOLTOU = "cena_voltou"


class Efeito(StrEnum):
    """O que acontece junto com a transição. A sessão executa; a máquina só nomeia."""

    GRAVAR_SESSAO_E_CATALOGO = "gravar_sessao_e_catalogo"
    ABRIR_OVERLAY = "abrir_overlay"
    INICIAR_CICLO = "iniciar_ciclo"
    GRAVAR_CICLO_POUPADO = "gravar_ciclo_poupado"
    GRAVAR_SITUACAO = "gravar_situacao"
    MONTAR_PEDIDO_DECISAO = "montar_pedido_decisao"
    GRAVAR_MARCO_SE_MORTE = "gravar_marco_se_morte"
    CONGELAR_INTERVALO = "congelar_intervalo"
    DESCONGELAR_INTERVALO = "descongelar_intervalo"
    GRAVAR_CICLO_SEM_SITUACAO = "gravar_ciclo_sem_situacao"
    GRAVAR_DECISAO = "gravar_decisao"
    OVERLAY_DISCRETO = "overlay_discreto"
    INFORMAR_PROXIMA_JANELA = "informar_proxima_janela"
    RELER_E_GRAVAR_ESTADO_ANTES = "reler_e_gravar_estado_antes"
    GRAVAR_INTERVENCAO_DESCARTADA = "gravar_intervencao_descartada"
    GRAVAR_ESTADO_DEPOIS = "gravar_estado_depois"
    MOSTRAR_ACAO_E_MOTIVO = "mostrar_acao_e_motivo"
    MARCAR_REVERSIVEL = "marcar_reversivel"
    ZERAR_INTERVALO = "zerar_intervalo"
    GRAVAR_FALHA_ALAVANCA = "gravar_falha_alavanca"
    GRAVAR_MARCO_MUDANCA_FASE = "gravar_marco_mudanca_fase"
    ENCERRAR_ACOES_COM_DURACAO = "encerrar_acoes_com_duracao"
    GRAVAR_MARCO = "gravar_marco"
    OVERLAY_MESTRE_PAUSADO = "overlay_mestre_pausado"
    CANCELAR_EXECUCAO = "cancelar_execucao"
    GRAVAR_INTERVENCAO_CANCELADA = "gravar_intervencao_cancelada"
    RECONSTRUIR_MEMORIA_E_CATALOGO = "reconstruir_memoria_e_catalogo"
    REINICIAR_INTERVALO = "reiniciar_intervalo"
    EXECUTAR_REVERSAO = "executar_reversao"
    GRAVAR_REVERSAO = "gravar_reversao"
    CONTAR_COMO_INTERVENCAO = "contar_como_intervencao"
    GRAVAR_FALHA_VISIVEL = "gravar_falha_visivel"
    OVERLAY_DESTAQUE = "overlay_destaque"
    TENTAR_RECONECTAR = "tentar_reconectar"
    AVISAR_SEM_REGISTRO = "avisar_sem_registro"
    GRAVAR_VOLTA = "gravar_volta"
    INTERVALO_COMO_VENCIDO = "intervalo_como_vencido"
    ESTADO_FINAL_EM_SLOT = "estado_final_em_slot"
    MONTAR_RESUMO = "montar_resumo"
    FECHAR_ARQUIVO = "fechar_arquivo"
    MARCAR_QUEDA_DO_EMULADOR = "marcar_queda_do_emulador"


@dataclass(frozen=True)
class Resultado:
    proximo: Estado
    efeitos: tuple[Efeito, ...]


class TransicaoInvalidaError(RuntimeError):
    def __init__(self, atual: Estado, evento: Evento) -> None:
        super().__init__(f"transicao_invalida: {atual} + {evento}")
        self.atual = atual
        self.evento = evento


MESMO = "mesmo"  # o novo estado é o atual (reversão do jogador)
ATIVOS = (Estado.OBSERVANDO, Estado.DECIDINDO, Estado.EXECUTANDO, Estado.BLOQUEADA)
NAO_ENCERRADA = tuple(e for e in Estado if e != Estado.ENCERRADA)

E = Efeito
# (estados de origem, evento) -> (destino, efeitos). A ordem das linhas é a do Blueprint, capítulo 4.
_LINHAS: list[tuple[tuple[Estado, ...], Evento, Estado | str, tuple[Efeito, ...]]] = [
    (
        (Estado.ABRINDO,),
        Evento.PRONTO,
        Estado.OBSERVANDO,
        (E.GRAVAR_SESSAO_E_CATALOGO, E.ABRIR_OVERLAY, E.INICIAR_CICLO),
    ),
    ((Estado.OBSERVANDO,), Evento.CAPTURA_SEM_MUDANCA, Estado.OBSERVANDO, (E.GRAVAR_CICLO_POUPADO,)),
    (
        (Estado.OBSERVANDO,),
        Evento.SITUACAO_OK,
        Estado.DECIDINDO,
        (E.GRAVAR_SITUACAO, E.MONTAR_PEDIDO_DECISAO),
    ),
    (
        (Estado.OBSERVANDO,),
        Evento.SITUACAO_FORA_DE_JOGO,
        Estado.BLOQUEADA,
        (E.GRAVAR_SITUACAO, E.GRAVAR_MARCO_SE_MORTE, E.CONGELAR_INTERVALO),
    ),
    ((Estado.OBSERVANDO,), Evento.SITUACAO_INVALIDA, Estado.OBSERVANDO, (E.GRAVAR_CICLO_SEM_SITUACAO,)),
    ((Estado.DECIDINDO,), Evento.DECISAO_NADA, Estado.OBSERVANDO, (E.GRAVAR_DECISAO, E.OVERLAY_DISCRETO)),
    ((Estado.DECIDINDO,), Evento.DECISAO_DESCARTADA, Estado.OBSERVANDO, (E.GRAVAR_DECISAO,)),
    (
        (Estado.DECIDINDO,),
        Evento.INTERVALO_NAO_VENCEU,
        Estado.OBSERVANDO,
        (E.GRAVAR_DECISAO, E.INFORMAR_PROXIMA_JANELA),
    ),
    ((Estado.DECIDINDO,), Evento.DECISAO_VALIDADA, Estado.EXECUTANDO, (E.RELER_E_GRAVAR_ESTADO_ANTES,)),
    ((Estado.EXECUTANDO,), Evento.SITUACAO_MUDOU, Estado.OBSERVANDO, (E.GRAVAR_INTERVENCAO_DESCARTADA,)),
    (
        (Estado.EXECUTANDO,),
        Evento.EXECUCAO_CONFIRMADA,
        Estado.OBSERVANDO,
        (E.GRAVAR_ESTADO_DEPOIS, E.MOSTRAR_ACAO_E_MOTIVO, E.MARCAR_REVERSIVEL, E.ZERAR_INTERVALO),
    ),
    ((Estado.EXECUTANDO,), Evento.EXECUCAO_FALHOU, Estado.OBSERVANDO, (E.GRAVAR_FALHA_ALAVANCA,)),
    (
        (Estado.BLOQUEADA,),
        Evento.CENA_VOLTOU,
        Estado.OBSERVANDO,
        (E.DESCONGELAR_INTERVALO, E.GRAVAR_MARCO_MUDANCA_FASE),
    ),
    ((Estado.BLOQUEADA,), Evento.CAPTURA_SEM_MUDANCA, Estado.BLOQUEADA, (E.GRAVAR_CICLO_POUPADO,)),
    (
        (Estado.BLOQUEADA,),
        Evento.SITUACAO_FORA_DE_JOGO,
        Estado.BLOQUEADA,
        (E.GRAVAR_SITUACAO, E.GRAVAR_MARCO_SE_MORTE),
    ),
    # refinamento do S3-06: situação inválida em tela fora de jogo continua bloqueada
    ((Estado.BLOQUEADA,), Evento.SITUACAO_INVALIDA, Estado.BLOQUEADA, (E.GRAVAR_CICLO_SEM_SITUACAO,)),
    (
        (Estado.OBSERVANDO, Estado.DECIDINDO, Estado.BLOQUEADA),
        Evento.JOGADOR_PAUSOU,
        Estado.PAUSADA_JOGADOR,
        (E.ENCERRAR_ACOES_COM_DURACAO, E.GRAVAR_MARCO, E.OVERLAY_MESTRE_PAUSADO),
    ),
    (
        (Estado.EXECUTANDO,),
        Evento.JOGADOR_PAUSOU,
        Estado.PAUSADA_JOGADOR,
        (E.CANCELAR_EXECUCAO, E.GRAVAR_INTERVENCAO_CANCELADA, E.OVERLAY_MESTRE_PAUSADO),
    ),
    (
        (Estado.PAUSADA_JOGADOR,),
        Evento.JOGADOR_RETOMOU,
        Estado.OBSERVANDO,
        (E.RECONSTRUIR_MEMORIA_E_CATALOGO, E.REINICIAR_INTERVALO, E.GRAVAR_MARCO),
    ),
    (
        (Estado.OBSERVANDO, Estado.BLOQUEADA, Estado.PAUSADA_JOGADOR, Estado.SILENCIADA),
        Evento.JOGADOR_REVERTEU,
        MESMO,
        (E.EXECUTAR_REVERSAO, E.GRAVAR_REVERSAO, E.CONTAR_COMO_INTERVENCAO),
    ),
    (
        (Estado.OBSERVANDO, Estado.DECIDINDO, Estado.BLOQUEADA),
        Evento.FALHA_SERVICO,
        Estado.SILENCIADA,
        (E.GRAVAR_FALHA_VISIVEL, E.OVERLAY_DESTAQUE),
    ),
    (ATIVOS, Evento.FALHA_EMULADOR, Estado.SILENCIADA, (E.GRAVAR_FALHA_VISIVEL, E.TENTAR_RECONECTAR)),
    (
        ATIVOS,
        Evento.FALHA_REGISTRO,
        Estado.PAUSADA_JOGADOR,
        (E.AVISAR_SEM_REGISTRO, E.OVERLAY_MESTRE_PAUSADO),
    ),
    (
        (Estado.SILENCIADA,),
        Evento.RECUPEROU,
        Estado.OBSERVANDO,
        (E.GRAVAR_VOLTA, E.INTERVALO_COMO_VENCIDO, E.INICIAR_CICLO),
    ),
    (
        (Estado.SILENCIADA,),
        Evento.FALHA_PROLONGADA,
        Estado.PAUSADA_JOGADOR,
        (E.GRAVAR_FALHA_VISIVEL, E.GRAVAR_MARCO, E.OVERLAY_MESTRE_PAUSADO),
    ),
    (
        (Estado.SILENCIADA,),
        Evento.FALHA_EMULADOR,
        Estado.ENCERRADA,
        (E.MARCAR_QUEDA_DO_EMULADOR, E.MONTAR_RESUMO, E.FECHAR_ARQUIVO),
    ),
    (
        NAO_ENCERRADA,
        Evento.JOGADOR_ENCERROU,
        Estado.ENCERRADA,
        (E.ENCERRAR_ACOES_COM_DURACAO, E.ESTADO_FINAL_EM_SLOT, E.MONTAR_RESUMO, E.FECHAR_ARQUIVO),
    ),
]

TABELA: dict[tuple[Estado, Evento], tuple[Estado | str, tuple[Efeito, ...]]] = {}
for _origens, _evento, _destino, _efeitos in _LINHAS:
    for _origem in _origens:
        if (_origem, _evento) in TABELA:
            raise RuntimeError(f"tabela ambígua: {_origem} + {_evento}")
        TABELA[(_origem, _evento)] = (_destino, _efeitos)


def transicao(atual: Estado, evento: Evento) -> Resultado:
    """A única porta. Par fora da tabela: TransicaoInvalidaError, e quem chamou não grava nada."""
    linha = TABELA.get((atual, evento))
    if linha is None:
        raise TransicaoInvalidaError(atual, evento)
    destino, efeitos = linha
    proximo = atual if destino == MESMO else Estado(destino)
    return Resultado(proximo, efeitos)


def pares_validos() -> list[tuple[Estado, Evento]]:
    return sorted(TABELA)


def pares_invalidos() -> list[tuple[Estado, Evento]]:
    return sorted((e, v) for e in Estado for v in Evento if (e, v) not in TABELA)
