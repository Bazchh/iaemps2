"""Card S1-02: identificar o jogo e o modo.

Critério de aceite: dado o jogo de abertura rodando, quando a ponte identifica, então devolve serial SLUS-21134
e soma 013e349d, e o modo é "reduzido" no emulador original. (No simulador em modo próprio, "completo".)
"""

from __future__ import annotations

import pytest

from iaemps2.ponte import emulador
from iaemps2.ponte.cliente import Cliente
from iaemps2.simulador.servidor import Simulador


def test_original_e_modo_reduzido() -> None:
    with Simulador("original") as sim, Cliente(porta=sim.porta or 0) as c:
        jogo = emulador.identificar(c)
        assert jogo.identificacao.serial == "SLUS-21134" and jogo.identificacao.crc == "013e349d"
        assert jogo.modo == emulador.MODO_REDUZIDO
        assert jogo.capacidades == emulador.SEM_EXTENSAO
        assert jogo.identificado and jogo.emulador_versao.startswith("PCSX2")


def test_proprio_e_modo_completo() -> None:
    with Simulador("proprio") as sim, Cliente(porta=sim.porta or 0) as c:
        jogo = emulador.identificar(c)
        assert jogo.modo == emulador.MODO_COMPLETO
        assert jogo.capacidades.pausa and jogo.capacidades.velocidade
        assert not jogo.capacidades.resultado_estado
        assert jogo.capacidades.versao_extensao == 1


def test_serial_vazio_nao_identifica() -> None:
    with Simulador() as sim, Cliente(porta=sim.porta or 0) as c:
        sim.jogo.serial = ""
        sim.jogo.titulo = "programa caseiro"
        jogo = emulador.identificar(c)
        assert not jogo.identificado
        assert jogo.identificacao.titulo == "programa caseiro"


def test_troca_de_jogo_e_detectada_por_serial_e_soma() -> None:
    with Simulador(cenarios={"troca_serial": 1}) as sim, Cliente(porta=sim.porta or 0) as c:
        antes = emulador.identificar(c)
        c.status()
        c.status()  # a segunda consulta dispara a troca no simulador
        agora = emulador.identificar(c)
        assert emulador.trocou_de_jogo(antes, agora)
        assert agora.identificacao.serial == "SLUS-99999"


def test_mesmo_jogo_com_titulo_diferente_nao_e_troca() -> None:
    with Simulador() as sim, Cliente(porta=sim.porta or 0) as c:
        antes = emulador.identificar(c)
        sim.jogo.titulo = "Resident Evil 4 (nome traduzido)"
        agora = emulador.identificar(c)
        assert not emulador.trocou_de_jogo(antes, agora)


@pytest.mark.emulador
def test_emulador_real_e_reduzido() -> None:
    with Cliente() as c:
        jogo = emulador.identificar(c)
        assert jogo.identificacao.serial == "SLUS-21134" and jogo.identificacao.crc == "013e349d"
        assert jogo.modo == emulador.MODO_REDUZIDO
