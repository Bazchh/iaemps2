"""Card S2-03: descrever, adaptador do serviço e formato fechado.

Critério de aceite: dado uma resposta gravada com fase fora da lista, quando o olho valida, então a situação é
inválida, o ciclo fica sem situação e nada é inventado; e uma captura real do jogo de abertura devolve fase e
aperto válidos (teste marcado `servico`).
"""

from __future__ import annotations

import pytest
from PIL import Image

from iaemps2.olho import captura as cap
from iaemps2.olho import situacao as sit
from iaemps2.olho.diferenca import Veredito
from iaemps2.olho.olho import descrever
from iaemps2.ponte.protocolo import Status
from iaemps2.servicos import criar
from iaemps2.servicos.base import ServicoError
from iaemps2.servicos.falso import ServicoFalso

VALIDA = '{"descricao": "Leon cercado por quatro aldeões numa casa, pouca vida", "fase": "combate", "aperto": 3, "confianca": 0.8}'


def _captura() -> cap.Captura:
    return cap.preparar(Image.new("RGB", (640, 360), (30, 30, 30)), cap.Retangulo(0, 0, 640, 360), 640, 70)


def _descrever(servico: ServicoFalso, status: Status = Status.RODANDO, anterior: sit.Situacao | None = None):  # type: ignore[no-untyped-def]
    return descrever(
        servico,
        _captura(),
        Veredito(True, "mudanca", 0.3),
        jogo_titulo="Resident Evil 4",
        jogo_serial="SLUS-21134",
        status=status,
        anterior=anterior,
    )


def test_resposta_valida_vira_situacao() -> None:
    s = sit.validar(VALIDA)
    assert s.fase is sit.Fase.COMBATE and s.aperto == 3 and s.confianca == 0.8 and s.em_jogo
    assert s.descricao.startswith("Leon cercado")


def test_fase_fora_da_lista_e_invalida_e_nada_e_inventado() -> None:
    servico = ServicoFalso([VALIDA.replace("combate", "cutscene"), VALIDA.replace("combate", "cutscene")])
    obs = _descrever(servico)
    assert obs.situacao is None and obs.tentativas == 2
    assert obs.invalida_motivo is not None and "fase" in obs.invalida_motivo
    assert len(servico.pedidos) == 2  # tentou uma vez mais com a mesma captura


def test_segunda_tentativa_valida_salva_o_ciclo() -> None:
    servico = ServicoFalso(["isso não é json", VALIDA])
    obs = _descrever(servico)
    assert obs.situacao is not None and obs.tentativas == 2 and obs.invalida_motivo is None


@pytest.mark.parametrize(
    "ruim",
    [
        '{"descricao": "x", "fase": "combate", "aperto": 5, "confianca": 0.5}',  # aperto fora
        '{"descricao": "x", "fase": "combate", "aperto": 1, "confianca": 1.5}',  # confiança fora
        '{"descricao": "x", "fase": "combate", "aperto": 1}',  # campo a menos
        '{"descricao": "x", "fase": "combate", "aperto": 1, "confianca": 0.5, "extra": 1}',  # campo a mais
        '{"descricao": "", "fase": "combate", "aperto": 1, "confianca": 0.5}',  # vazia
        '{"descricao": "' + "a" * 161 + '", "fase": "combate", "aperto": 1, "confianca": 0.5}',  # longa
        "[1, 2]",
        "",
    ],
)
def test_respostas_fora_do_contrato(ruim: str) -> None:
    with pytest.raises(sit.SituacaoInvalidaError):
        sit.validar(ruim)


def test_cerca_de_codigo_e_tolerada() -> None:
    assert sit.validar("```json\n" + VALIDA + "\n```").fase is sit.Fase.COMBATE


def test_descricao_vira_uma_linha() -> None:
    quebra_escapada = "\\n"  # dentro do JSON: os dois caracteres barra e n
    com_quebra = VALIDA.replace("Leon cercado", "Leon" + quebra_escapada + "  cercado")
    s = sit.validar(com_quebra)
    assert "\n" not in s.descricao and "Leon cercado" in s.descricao


def test_suspeita_quando_combate_com_emulador_pausado() -> None:
    obs = _descrever(ServicoFalso([VALIDA]), status=Status.PAUSADO)
    assert obs.situacao is not None and obs.suspeita is not None and "pausado" in obs.suspeita
    assert _descrever(ServicoFalso([VALIDA])).suspeita is None


def test_fora_de_jogo_bloqueia_e_morte_e_marco_uma_vez() -> None:
    menu = sit.validar(VALIDA.replace("combate", "menu"))
    morte = sit.validar(VALIDA.replace("combate", "morte"))
    combate = sit.validar(VALIDA)
    assert sit.bloqueia_intervencao(menu) and sit.bloqueia_intervencao(morte)
    assert not sit.bloqueia_intervencao(combate)
    assert sit.e_marco_de_morte(combate, morte) and sit.e_marco_de_morte(None, morte)
    assert not sit.e_marco_de_morte(morte, morte)


def test_captura_poupada_nao_chama_o_servico() -> None:
    servico = ServicoFalso([VALIDA])
    obs = descrever(
        servico,
        _captura(),
        Veredito(False, "sem_mudanca", 0.0),
        jogo_titulo="J",
        jogo_serial="S",
        status=Status.RODANDO,
    )
    assert obs.situacao is None and obs.resposta is None and servico.pedidos == []


def test_pedido_leva_contexto_e_situacao_anterior() -> None:
    servico = ServicoFalso([VALIDA])
    anterior = sit.validar(VALIDA.replace("combate", "exploracao"))
    _descrever(servico, anterior=anterior)
    pedido = servico.pedidos[0]
    assert pedido.situacao_anterior == {
        "descricao": anterior.descricao,
        "fase": "exploracao",
        "aperto": 3,
        "confianca": 0.8,
    }
    texto = pedido.instrucao()
    assert "exploracao, combate, menu, video, carregamento, morte, sistema" in texto
    assert "SLUS-21134" in texto and "160" in texto and "JSON" in texto


def test_falha_do_servico_sobe_com_classe() -> None:
    servico = ServicoFalso([ServicoError("limite", "cota")])
    with pytest.raises(ServicoError) as erro:
        _descrever(servico)
    assert erro.value.classe == "limite"


def test_criar_adaptador() -> None:
    assert criar("falso").nome == "falso"
    with pytest.raises(ServicoError):
        criar("inexistente")


def test_provedor_real_sem_chave_e_fora_do_ar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IAEMPS2_CHAVE_SERVICO", raising=False)
    with pytest.raises(ServicoError) as erro:
        criar("provedor_g")
    assert erro.value.classe == "fora_do_ar" and "chave" in erro.value.detalhe


@pytest.mark.servico
@pytest.mark.emulador
def test_servico_real_descreve_a_captura_real() -> None:
    from iaemps2.olho.captura import Capturador
    from iaemps2.olho.diferenca import Comparador

    servico = criar("provedor_g")
    captura = Capturador().capturar()
    obs = descrever(
        servico,
        captura,
        Comparador().avaliar(captura),
        jogo_titulo="Resident Evil 4",
        jogo_serial="SLUS-21134",
        status=Status.RODANDO,
    )
    assert obs.situacao is not None, obs.invalida_motivo
    assert obs.situacao.fase in sit.Fase and 0 <= obs.situacao.aperto <= 4
    assert obs.resposta is not None and obs.resposta.latencia_ms > 0
