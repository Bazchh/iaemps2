"""Card S3-03: decidir, pedido, validação dupla, "nada" e motivo.

Critério de aceite: dado uma resposta gravada pedindo recarregar um slot de aperto maior que o atual, quando o
mestre valida, então a decisão é descartada por regra de mesa, gravada com origem descarte, e o ciclo vale "nada".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iaemps2.catalogo import catalogo as cat
from iaemps2.mestre import decisao as dec
from iaemps2.mestre import memoria, mestre
from iaemps2.olho.situacao import Fase, Situacao
from iaemps2.ponte.emulador import SEM_EXTENSAO, Capacidades
from iaemps2.ponte.protocolo import Status
from iaemps2.registro import banco
from iaemps2.servicos.base import ServicoError
from iaemps2.servicos.falso import ServicoFalso

COMPLETO = Capacidades(1, True, True, False)
COMBATE_3 = Situacao(
    descricao="Leon cercado por quatro aldeões, pouca vida", fase=Fase.COMBATE, aperto=3, confianca=0.8
)


def _catalogo(caps: Capacidades = COMPLETO, slots: tuple[int, ...] = (93, 94)) -> cat.Catalogo:
    return cat.com_slots(cat.montar(caps), slots)


def _decidir(
    resposta: str,
    catalogo: cat.Catalogo | None = None,
    aperto_slots: dict[int, int] | None = None,
    janela: int = 0,
) -> mestre.Decidido:
    catalogo = catalogo or _catalogo()
    servico = ServicoFalso(decisoes=[resposta])
    pedido = mestre.montar_pedido(
        catalogo=catalogo,
        situacao=COMBATE_3,
        status="rodando",
        velocidade=1.0,
        memoria=memoria.MemoriaCurta(),
        proxima_janela_ms=janela,
        jogo_titulo="Resident Evil 4",
    )
    return mestre.decidir(
        servico, pedido, catalogo, COMBATE_3, aperto_slots if aperto_slots is not None else {93: 1, 94: 4}
    )


def test_criterio_de_aceite_regra_de_mesa() -> None:
    d = _decidir('{"alavanca": "recarregar", "parametros": {"slot": 94}, "motivo": "Volta."}')
    v = d.veredito
    assert v.origem == "descarte" and v.alavanca == "nada" and not v.executa
    assert (
        v.descarte_motivo is not None and "regra de mesa" in v.descarte_motivo and "94" in v.descarte_motivo
    )


def test_recarregar_para_aperto_menor_passa() -> None:
    v = _decidir(
        '{"alavanca": "recarregar", "parametros": {"slot": 93}, "motivo": "Um fôlego: a cena de novo."}'
    ).veredito
    assert v.executa and v.alavanca == "recarregar" and v.parametros == {"slot": 93.0}
    assert v.motivo == "Um fôlego: a cena de novo." and v.motivo_origem == "servico"


def test_camera_lenta_valida() -> None:
    v = _decidir(
        '{"alavanca": "camera_lenta", "parametros": {"escalar": 0.5, "duracao_s": 5}, "motivo": "O tempo pesa."}'
    ).veredito
    assert v.executa and v.parametros == {"escalar": 0.5, "duracao_s": 5.0}


@pytest.mark.parametrize(
    ("resposta", "trecho"),
    [
        ('{"alavanca": "teleporte", "parametros": {}, "motivo": "x"}', "fora do catálogo"),
        (
            '{"alavanca": "camera_lenta", "parametros": {"escalar": 0.3, "duracao_s": 5}, "motivo": "x"}',
            "fora da faixa",
        ),
        ('{"alavanca": "camera_lenta", "parametros": {"escalar": 0.5}, "motivo": "x"}', "parâmetros"),
        (
            '{"alavanca": "camera_lenta", "parametros": {"escalar": 0.5, "duracao_s": 5, "extra": 1}, "motivo": "x"}',
            "parâmetros",
        ),
        ('{"alavanca": "recarregar", "parametros": {"slot": 97}, "motivo": "x"}', "sem contexto"),
    ],
)
def test_descartes_inteiros_nunca_aproximados(resposta: str, trecho: str) -> None:
    v = _decidir(resposta).veredito
    assert (
        v.origem == "descarte"
        and v.alavanca == "nada"
        and v.descarte_motivo is not None
        and trecho in v.descarte_motivo
    )


def test_indisponivel_e_descartada() -> None:
    v = _decidir(
        '{"alavanca": "pausa", "parametros": {"duracao_s": 2}, "motivo": "x"}',
        catalogo=_catalogo(SEM_EXTENSAO),
    ).veredito
    assert v.origem == "descarte" and v.descarte_motivo is not None and "indisponível" in v.descarte_motivo


def test_nada_e_decisao_com_motivo() -> None:
    v = _decidir(
        '{"alavanca": "nada", "parametros": {}, "motivo": "Explorando com calma; sem razão para intervir."}'
    ).veredito
    assert v.alavanca == "nada" and v.origem == "servico" and v.motivo_origem == "servico" and not v.executa
    sem = _decidir('{"alavanca": "nada", "motivo": ""}').veredito
    assert sem.motivo == "Nada a fazer agora." and sem.motivo_origem == "ausente"


def test_motivo_improprio_vira_padrao_sem_cancelar_a_acao() -> None:
    guia = _decidir(
        '{"alavanca": "camera_lenta", "parametros": {"escalar": 0.6, "duracao_s": 4}, "motivo": "Vá pela porta da esquerda."}'
    ).veredito
    assert guia.executa and guia.motivo == "O tempo pesa." and guia.motivo_origem == "padrao"
    longo = _decidir(
        json.dumps(
            {"alavanca": "camera_lenta", "parametros": {"escalar": 0.6, "duracao_s": 4}, "motivo": "a" * 121}
        )
    ).veredito
    assert longo.executa and longo.motivo_origem == "padrao"


def test_resposta_invalida_vira_nada_por_falha() -> None:
    v = _decidir("isso não é json").veredito
    assert (
        v.alavanca == "nada"
        and v.origem == "falha"
        and v.descarte_motivo is not None
        and "inválida" in v.descarte_motivo
    )
    v2 = _decidir('{"alavanca": "nada", "parametros": {}, "motivo": "x", "outro": 1}').veredito
    assert v2.origem == "falha"


def test_janela_fechada_nem_chama_o_servico() -> None:
    d = _decidir(
        '{"alavanca": "turbo", "parametros": {"escalar": 2, "duracao_s": 5}, "motivo": "x"}', janela=12000
    )
    assert d.veredito.origem == "ritmo" and d.veredito.alavanca == "nada" and d.resposta is None


def test_pedido_leva_catalogo_memoria_e_regras() -> None:
    d = _decidir('{"alavanca": "nada", "parametros": {}, "motivo": "x"}')
    texto = d.pedido.instrucao()
    assert "camera_lenta" in texto and "disponivel" in texto and "ciclos_sem_agir" in texto
    assert "dificulte, nunca derrote" in texto and "imprevisivel" in texto and "Resident Evil 4" in texto
    assert "120" in texto and "JSON" in texto


def test_falha_do_servico_sobe() -> None:
    servico = ServicoFalso(decisoes=[ServicoError("fora_do_ar", "x")])
    catalogo = _catalogo()
    pedido = mestre.montar_pedido(
        catalogo=catalogo,
        situacao=COMBATE_3,
        status="rodando",
        velocidade=1.0,
        memoria=memoria.MemoriaCurta(),
        proxima_janela_ms=0,
    )
    with pytest.raises(ServicoError):
        mestre.decidir(servico, pedido, catalogo, COMBATE_3, {})


def test_releitura_detecta_situacao_velha() -> None:
    assert dec.situacao_mudou(COMBATE_3, Status.RODANDO, COMBATE_3, Status.RODANDO) is None
    assert dec.situacao_mudou(COMBATE_3, Status.RODANDO, None, Status.PAUSADO) is not None
    menu = Situacao(descricao="menu", fase=Fase.MENU, aperto=0, confianca=1)
    assert "fase mudou" in (dec.situacao_mudou(COMBATE_3, Status.RODANDO, menu, Status.RODANDO) or "")
    calmo = Situacao(descricao="x", fase=Fase.COMBATE, aperto=1, confianca=1)
    assert "aperto" in (dec.situacao_mudou(COMBATE_3, Status.RODANDO, calmo, Status.RODANDO) or "")


def test_memoria_curta_vem_do_registro(tmp_path: Path) -> None:
    con = banco.criar(tmp_path / "s.sqlite")
    sessao = banco.abrir_sessao(
        con,
        jogo_titulo="J",
        jogo_serial="S",
        jogo_crc="0",
        jogo_versao=None,
        emulador_versao="e",
        modo="reduzido",
        tom="imprevisivel",
        intensidade="media",
        servico="falso",
        aceite_versao="1",
        config_json="{}",
    )
    c1 = banco.gravar_ciclo(con, sessao, 1, 0, "rodando", "observando")
    d1 = banco.gravar_decisao(
        con,
        {
            "ciclo_id": c1,
            "catalogo_versao": 1,
            "alavanca": "turbo",
            "parametros_json": "{}",
            "motivo": "Sem tempo a perder.",
            "motivo_origem": "servico",
            "origem": "servico",
            "pedido_bruto": "{}",
        },
    )
    i1 = banco.gravar_intervencao(
        con,
        {
            "decisao_id": d1,
            "alavanca": "turbo",
            "parametros_json": "{}",
            "origem": "mestre",
            "estado_antes_json": "{}",
            "comando_ms": 1000,
            "reversivel": 1,
        },
    )
    banco.preencher_uma_vez(con, "intervencoes", i1, {"resultado": "confirmada"})
    banco.gravar_marco(con, c1, "morte")
    # o jogador reverteu
    d2 = banco.gravar_decisao(
        con,
        {
            "ciclo_id": c1,
            "catalogo_versao": 1,
            "alavanca": "turbo",
            "parametros_json": "{}",
            "motivo": "",
            "motivo_origem": "ausente",
            "origem": "servico",
            "pedido_bruto": "{}",
        },
    )
    i2 = banco.gravar_intervencao(
        con,
        {
            "decisao_id": d2,
            "alavanca": "turbo",
            "parametros_json": "{}",
            "origem": "reversao_jogador",
            "estado_antes_json": "{}",
            "comando_ms": 2000,
            "reversivel": 0,
        },
    )
    banco.preencher_uma_vez(con, "intervencoes", i1, {"revertida_por": i2})
    for n in (2, 3, 4):
        banco.gravar_ciclo(
            con, sessao, n, n * 1000, "rodando", "observando", lacuna="janela ausente" if n == 3 else None
        )
    m = memoria.reconstruir(con, sessao, agora_ms=5000)
    assert m.ultimas_intervencoes[0]["alavanca"] == "turbo" and m.ultimas_intervencoes[0]["revertida"] is True
    assert m.ultimas_intervencoes[0]["ha_ms"] == 4000 and m.marcos[0]["tipo"] == "morte"
    assert m.revertidas_pelo_jogador == ["turbo"] and m.ciclos_sem_agir == 3 and m.lacunas == 1
    assert set(m.como_json()) == {
        "ultimas_intervencoes",
        "marcos",
        "ciclos_sem_agir",
        "revertidas_pelo_jogador",
        "lacunas",
    }
    con.close()
