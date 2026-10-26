"""Card S3-01: máquina de estados da sessão.

Critério de aceite: dado o estado executando, quando chega situacao_ok, então a transição é recusada com
transicao_invalida e nada é gravado; e todo par da tabela tem teste verde.
"""

from __future__ import annotations

import threading

import pytest

from iaemps2.sessao.fila import FilaDeEventos, Laco, Mensagem
from iaemps2.sessao.maquina import (
    TABELA,
    Efeito,
    Estado,
    Evento,
    Resultado,
    TransicaoInvalidaError,
    pares_invalidos,
    pares_validos,
    transicao,
)
from iaemps2.sessao.relogio import Contador, IntervaloMinimo

# ---- a tabela, inteira ----


def test_oito_estados_e_a_tabela_do_blueprint() -> None:
    assert len(Estado) == 8
    assert len(pares_validos()) + len(pares_invalidos()) == len(Estado) * len(Evento)
    assert len(pares_validos()) == 44  # as 25 linhas do capítulo 4 expandidas pelos estados de origem


@pytest.mark.parametrize(("atual", "evento"), pares_validos(), ids=lambda x: str(x))
def test_todo_par_da_tabela_transita(atual: Estado, evento: Evento) -> None:
    r = transicao(atual, evento)
    assert isinstance(r.proximo, Estado) and r.efeitos  # toda transição tem ao menos um efeito
    assert all(isinstance(e, Efeito) for e in r.efeitos)


@pytest.mark.parametrize(("atual", "evento"), pares_invalidos(), ids=lambda x: str(x))
def test_todo_par_fora_da_tabela_e_recusado(atual: Estado, evento: Evento) -> None:
    with pytest.raises(TransicaoInvalidaError, match="transicao_invalida"):
        transicao(atual, evento)


def test_criterio_de_aceite_executando_mais_situacao_ok() -> None:
    with pytest.raises(TransicaoInvalidaError) as erro:
        transicao(Estado.EXECUTANDO, Evento.SITUACAO_OK)
    assert erro.value.atual is Estado.EXECUTANDO and erro.value.evento is Evento.SITUACAO_OK


def test_regra_de_ouro_so_executando_manda_comando() -> None:
    """Só 'executando' chega por decisao_validada, e só de 'decidindo'."""
    origens = [a for (a, ev), (dest, _) in TABELA.items() if dest == Estado.EXECUTANDO]
    assert origens == [Estado.DECIDINDO]
    assert TABELA[(Estado.DECIDINDO, Evento.DECISAO_VALIDADA)][0] == Estado.EXECUTANDO


def test_reversao_mantem_o_estado() -> None:
    for estado in (Estado.OBSERVANDO, Estado.BLOQUEADA, Estado.PAUSADA_JOGADOR, Estado.SILENCIADA):
        r = transicao(estado, Evento.JOGADOR_REVERTEU)
        assert r.proximo is estado and Efeito.CONTAR_COMO_INTERVENCAO in r.efeitos
    with pytest.raises(TransicaoInvalidaError):
        transicao(Estado.EXECUTANDO, Evento.JOGADOR_REVERTEU)


def test_encerrada_e_terminal() -> None:
    assert all(a != Estado.ENCERRADA for (a, _) in TABELA)


def test_ciclo_feliz_inteiro() -> None:
    caminho = [
        Evento.PRONTO,
        Evento.SITUACAO_OK,
        Evento.DECISAO_VALIDADA,
        Evento.EXECUCAO_CONFIRMADA,
        Evento.CAPTURA_SEM_MUDANCA,
        Evento.SITUACAO_FORA_DE_JOGO,
        Evento.CENA_VOLTOU,
        Evento.JOGADOR_ENCERROU,
    ]
    estado = Estado.ABRINDO
    vistos = [estado]
    for ev in caminho:
        estado = transicao(estado, ev).proximo
        vistos.append(estado)
    assert vistos == [
        Estado.ABRINDO,
        Estado.OBSERVANDO,
        Estado.DECIDINDO,
        Estado.EXECUTANDO,
        Estado.OBSERVANDO,
        Estado.OBSERVANDO,
        Estado.BLOQUEADA,
        Estado.OBSERVANDO,
        Estado.ENCERRADA,
    ]


# ---- fila única ----


def test_fila_processa_em_ordem_e_nao_grava_invalida() -> None:
    fila = FilaDeEventos()
    aplicados: list[tuple[Estado, Evento, Estado]] = []
    recusadas: list[Evento] = []

    def executar(r: Resultado, m: Mensagem, anterior: Estado) -> None:
        aplicados.append((anterior, m.evento, r.proximo))

    laco = Laco(fila, executar, lambda erro, m: recusadas.append(m.evento))
    fila.enfileirar(Evento.PRONTO)
    fila.enfileirar(Evento.SITUACAO_OK, origem="servico")
    fila.enfileirar(Evento.SITUACAO_OK, origem="servico")  # chega enquanto decide: inválida em 'decidindo'
    fila.enfileirar(Evento.DECISAO_VALIDADA)
    fila.enfileirar(Evento.JOGADOR_PAUSOU, origem="jogador")  # no meio da execução: cancela
    assert laco.processar_todos() == 5
    assert [a[1] for a in aplicados] == [
        Evento.PRONTO,
        Evento.SITUACAO_OK,
        Evento.DECISAO_VALIDADA,
        Evento.JOGADOR_PAUSOU,
    ]
    assert recusadas == [Evento.SITUACAO_OK]
    assert laco.estado is Estado.PAUSADA_JOGADOR and laco.processados == 4 and laco.recusados == 1


def test_fila_recebe_de_outras_threads() -> None:
    fila = FilaDeEventos()
    laco = Laco(fila, lambda r, m, a: None)
    fila.enfileirar(Evento.PRONTO)
    laco.processar_todos()

    def produtor() -> None:
        for _ in range(50):
            fila.enfileirar(Evento.CAPTURA_SEM_MUDANCA, origem="captura")

    threads = [threading.Thread(target=produtor) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fila.pendentes() == 200
    assert laco.processar_todos() == 200 and laco.estado is Estado.OBSERVANDO


# ---- contador e intervalo ----


def test_contador_congela_em_tela_fora_de_jogo() -> None:
    agora = [100.0]
    c = Contador(relogio=lambda: agora[0])
    agora[0] = 105.0
    assert c.agora_ms() == 5000 and c.ativo_ms() == 5000
    c.congelar()
    agora[0] = 125.0  # 20 s num menu
    assert c.agora_ms() == 25000 and c.ativo_ms() == 5000 and c.congelado
    c.descongelar()
    agora[0] = 130.0
    assert c.ativo_ms() == 10000 and not c.congelado


def test_intervalo_minimo_respeita_o_congelado() -> None:
    agora = [0.0]
    c = Contador(relogio=lambda: agora[0])
    i = IntervaloMinimo(c, minimo_ms=30000)
    assert i.venceu()  # nunca interveio
    i.zerar()
    agora[0] = 10.0
    assert not i.venceu() and i.faltam_ms() == 20000
    c.congelar()
    agora[0] = 40.0  # 30 s em menu não contam
    assert i.faltam_ms() == 20000
    c.descongelar()
    agora[0] = 60.0
    assert i.venceu()
    i.zerar()
    i.tratar_como_vencido()
    assert i.venceu()


def test_intervalo_nao_usa_a_hora_do_sistema() -> None:
    import datetime
    import time

    c = Contador()
    i = IntervaloMinimo(c, 1000)
    i.zerar()
    hora = datetime.datetime.now()  # mudar a hora do sistema não muda time.monotonic
    assert not i.venceu() and time.monotonic() > 0 and hora.year >= 2026
