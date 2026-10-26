"""Card S3-02: catálogo, tons e intensidades.

Critério de aceite: dado o modo reduzido e intensidade leve, quando o catálogo é montado, então pausa,
câmera lenta e turbo estão indisponíveis, o intervalo é 60 s e a versão 1 está gravada.
"""

from __future__ import annotations

import json

from iaemps2.catalogo import catalogo as cat
from iaemps2.ponte.emulador import SEM_EXTENSAO, Capacidades

COMPLETO = Capacidades(versao_extensao=1, pausa=True, velocidade=True, resultado_estado=False)


def test_criterio_de_aceite_reduzido_leve() -> None:
    c = cat.montar(SEM_EXTENSAO, intensidade=cat.Intensidade.LEVE)
    assert c.versao == 1 and c.modo == "reduzido" and c.motivo_da_versao == "abertura"
    assert c.regras.intervalo_minimo_s == 60
    for nome in ("pausa", "camera_lenta", "turbo"):
        a = c.alavanca(nome)
        assert a is not None and not a.disponivel
    assert c.disponiveis() == ["salvar_estado", "recarregar", "nada"]
    dados = json.loads(c.como_json())
    assert dados["versao"] == 1 and dados["intervalo_minimo_s"] == 60


def test_completo_media_tem_tudo() -> None:
    c = cat.montar(COMPLETO)
    assert c.modo == "completo" and c.tom is cat.TOM_PADRAO and c.intensidade is cat.INTENSIDADE_PADRAO
    assert c.disponiveis() == ["pausa", "camera_lenta", "turbo", "salvar_estado", "recarregar", "nada"]
    assert c.regras.intervalo_minimo_s == 30


def test_intensidade_muda_as_faixas() -> None:
    leve = cat.montar(COMPLETO, intensidade=cat.Intensidade.LEVE)
    forte = cat.montar(COMPLETO, intensidade=cat.Intensidade.FORTE)
    lenta_leve = leve.alavanca("camera_lenta")
    lenta_forte = forte.alavanca("camera_lenta")
    assert lenta_leve is not None and lenta_forte is not None
    assert lenta_leve.parametros["duracao_s"].maximo < lenta_forte.parametros["duracao_s"].maximo
    turbo_leve = leve.alavanca("turbo")
    assert turbo_leve is not None and not turbo_leve.disponivel  # leve não tem turbo mesmo no completo
    pausa_forte = forte.alavanca("pausa")
    assert pausa_forte is not None and pausa_forte.parametros["duracao_s"].maximo == 6


def test_faixa_contem() -> None:
    f = cat.Faixa(0.5, 0.8)
    assert f.contem(0.5) and f.contem(0.8) and not f.contem(0.81)


def test_recarregar_so_com_slot_de_contexto() -> None:
    c = cat.montar(SEM_EXTENSAO)
    pedido = {a["alavanca"]: a for a in c.para_o_pedido()}
    assert pedido["recarregar"]["disponivel"] is False and pedido["recarregar"]["parametros"]["slot"] == []
    c2 = cat.com_slots(c, (93, 94))
    pedido2 = {a["alavanca"]: a for a in c2.para_o_pedido()}
    assert pedido2["recarregar"]["disponivel"] is True and pedido2["recarregar"]["parametros"]["slot"] == [
        93,
        94,
    ]
    assert c2.versao == c.versao  # slot não é versão nova


def test_pedido_leva_disponibilidade_mas_nao_motivo_padrao() -> None:
    c = cat.montar(SEM_EXTENSAO)
    for item in c.para_o_pedido():
        assert set(item) == {"alavanca", "descricao", "disponivel", "parametros"}
    pausa = next(i for i in c.para_o_pedido() if i["alavanca"] == "pausa")
    assert pausa["disponivel"] is False  # continua na lista, marcada (Blueprint, cap. 5)


def test_tres_falhas_seguidas_tiram_a_alavanca_com_versao_nova() -> None:
    c = cat.montar(COMPLETO)
    c, nova = cat.registrar_falha(c, "camera_lenta")
    assert not nova and c.versao == 1
    c, nova = cat.registrar_falha(c, "camera_lenta")
    assert not nova
    c = cat.registrar_sucesso(c, "camera_lenta")  # um sucesso zera
    c, _ = cat.registrar_falha(c, "camera_lenta")
    c, _ = cat.registrar_falha(c, "camera_lenta")
    c, nova = cat.registrar_falha(c, "camera_lenta")
    assert nova and c.versao == 2 and "camera_lenta" not in c.disponiveis()
    assert "indisponível" in c.motivo_da_versao
    c2, nova2 = cat.registrar_falha(c, "camera_lenta")  # já indisponível: nada muda
    assert not nova2 and c2 is c


def test_nova_versao_por_emulador_reiniciado() -> None:
    c = cat.montar(SEM_EXTENSAO, tom=cat.Tom.PROTETOR, intensidade=cat.Intensidade.FORTE)
    c2 = cat.nova_versao(c, COMPLETO, "emulador reiniciado")
    assert c2.versao == 2 and c2.modo == "completo" and c2.tom is cat.Tom.PROTETOR
    assert c2.intensidade is cat.Intensidade.FORTE and "pausa" in c2.disponiveis()


def test_tons_e_intensidades_da_dc17() -> None:
    assert [t.value for t in cat.Tom] == ["protetor", "imprevisivel", "implacavel"]
    assert [i.value for i in cat.Intensidade] == ["leve", "media", "forte"]
    assert [cat.REGRAS[i].intervalo_minimo_s for i in cat.Intensidade] == [60, 30, 15]
    assert [cat.REGRAS[i].salvar_a_cada_s for i in cat.Intensidade] == [90, 60, 45]
    assert all(cat.DESCRICAO_DO_TOM[t] for t in cat.Tom)
