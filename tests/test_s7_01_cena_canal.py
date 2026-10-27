"""Card S7-01: assinaturas pelo canal, regras com forma e capacidade de cena, contra o simulador.

Critério (parte automática): dado o canal em modo próprio, quando a ponte pede a lista, então recebe as
assinaturas do último quadro com hash de textura e de forma; uma regra de esconder por forma conta só os
quadros em que aquele pedaço foi desenhado; a máscara de capacidades anuncia a cena.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iaemps2.ponte.cliente import REGRA_ESCONDER, REGRA_QUADRADO, Cliente, ComandoFalhouError
from iaemps2.ponte.emulador import identificar
from iaemps2.simulador.servidor import CENA_DE_MENTIRA, Simulador


def test_lista_regras_e_estatisticas_no_simulador(tmp_path: Path) -> None:
    agora = [0.0]
    with Simulador("proprio", pasta_estados=tmp_path, relogio=lambda: agora[0]) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        caps = identificar(c).capacidades
        assert caps.cena and caps.pausa and caps.velocidade

        quadro, lista = c.cena_lista()
        assert quadro == 1 and len(lista) == len(CENA_DE_MENTIRA)
        a = lista[0]
        assert (a.hash_textura, a.hash_forma, a.vertices) == (0x1111, 0xAAAA, 64)
        assert (a.x0, a.y0, a.x1, a.y1) == (100, 100, 200, 180) and a.area == 100 * 80
        assert a.qualifica and not a.fallback
        assert lista[2].fallback and not lista[2].qualifica

        # esconder por material e por pedaço
        id_material = c.cena_regra(REGRA_ESCONDER, hash_textura=0x1111, duracao_ms=0)
        id_pedaco = c.cena_regra(REGRA_ESCONDER, hash_textura=0x1111, hash_forma=0xBBBB, duracao_ms=0)
        id_nada = c.cena_regra(REGRA_ESCONDER, hash_textura=0x9999, duracao_ms=0)
        for _ in range(5):
            c.cena_lista()  # cada lista é um quadro no simulador
        assert c.cena_estatisticas(id_material).quadros_aplicada == 5
        assert c.cena_estatisticas(id_pedaco).quadros_aplicada == 5
        est = c.cena_estatisticas(id_nada)
        assert est.quadros_total == 5 and est.quadros_aplicada == 0
        assert est.camada_quadros == 6 and est.desenhos_ultimo_quadro == len(CENA_DE_MENTIRA)

        # prazo: a regra some sozinha
        id_prazo = c.cena_regra(REGRA_QUADRADO, retangulo=(10, 10, 50, 50), z=500_000, duracao_ms=2_000)
        c.cena_lista()
        assert c.cena_estatisticas(id_prazo).regra_existe
        agora[0] += 3
        c.cena_lista()
        assert not c.cena_estatisticas(id_prazo).regra_existe

        # limpar
        c.cena_limpar(id_material)
        assert not c.cena_estatisticas(id_material).regra_existe
        c.cena_limpar(0)
        assert not c.cena_estatisticas(id_pedaco).regra_existe

        # tipo desconhecido falha
        with pytest.raises(ComandoFalhouError):
            c.cena_regra(7, hash_textura=1)
        c.fechar()


def test_modo_original_nao_tem_cena(tmp_path: Path) -> None:
    with Simulador("original", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        assert not identificar(c).capacidades.cena
        with pytest.raises(ComandoFalhouError):
            c.cena_lista()
        c.fechar()
