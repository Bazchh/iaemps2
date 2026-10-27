"""Card S8-01: vigia de memória pelo canal, contra o simulador.

Critério (parte automática): dado o canal em modo próprio, quando a ponte vigia uma faixa e algo escreve nela,
então a leitura devolve uma entrada por instrução com endereço, valor, contagem e registradores; a leitura com
zerar esvazia a tabela; o prazo remove o vigia sozinho; a máscara de capacidades anuncia o vigia.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import VIGIA_ESCRITA, VIGIA_LEITURA, Cliente, ComandoFalhouError
from iaemps2.ponte.emulador import identificar
from iaemps2.simulador.servidor import Simulador


def escrever(c: Cliente, codigo: p.Codigo, endereco: int, valor: int) -> None:
    formato = {p.Codigo.WRITE8: "<IB", p.Codigo.WRITE16: "<IH", p.Codigo.WRITE32: "<II"}[codigo]
    c.pedir(p.comando(codigo, struct.pack(formato, endereco, valor)))


def test_vigia_grava_escritas_por_instrucao(tmp_path: Path) -> None:
    agora = [0.0]
    with Simulador("proprio", pasta_estados=tmp_path, relogio=lambda: agora[0]) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        assert identificar(c).capacidades.vigia

        estado, itens = c.vigia_ler()
        assert not estado.ativo and itens == []

        c.vigia_definir(0x1000, 0x1010, VIGIA_ESCRITA, duracao_ms=5000)
        escrever(c, p.Codigo.WRITE16, 0x1004, 1200)
        escrever(c, p.Codigo.WRITE16, 0x1004, 1048)
        escrever(c, p.Codigo.WRITE32, 0x100C, 7)
        escrever(c, p.Codigo.WRITE8, 0x2000, 1)  # fora da faixa: não conta

        estado, itens = c.vigia_ler()
        assert estado.ativo and (estado.inicio, estado.fim) == (0x1000, 0x1010)
        assert estado.acessos_total == 3 and estado.instrucoes == 2 and estado.descartados == 0
        assert 0 < estado.restante_ms <= 5000
        por_endereco = {a.primeiro_endereco: a for a in itens}
        vida = por_endereco[0x1004]
        assert vida.escrita and vida.bits == 16 and vida.contagem == 2 and vida.ultimo_valor == 1048
        assert vida.base == 4 and vida.registradores[4] + vida.deslocamento == 0x1004
        assert por_endereco[0x100C].bits == 32 and por_endereco[0x100C].ultimo_valor == 7

        # zerar: a tabela volta vazia, o vigia continua
        _, itens = c.vigia_ler(zerar=True)
        assert len(itens) == 2
        estado, itens = c.vigia_ler()
        assert estado.ativo and itens == [] and estado.acessos_total == 0

        # prazo: passou, o vigia some sozinho
        agora[0] = 6.0
        estado, _ = c.vigia_ler()
        assert not estado.ativo

        # limpar explícito
        c.vigia_definir(0x1000, 0x1010, VIGIA_LEITURA)
        escrever(c, p.Codigo.WRITE16, 0x1004, 1)  # só leitura vigiada: escrita não conta
        estado, itens = c.vigia_ler()
        assert estado.ativo and itens == []
        c.vigia_limpar()
        estado, _ = c.vigia_ler()
        assert not estado.ativo


def test_vigia_recusa_faixa_invalida(tmp_path: Path) -> None:
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        with pytest.raises(ComandoFalhouError):
            c.vigia_definir(0x2000, 0x1000)
        with pytest.raises(ComandoFalhouError):
            c.vigia_definir(0x1000, 0x2000, condicao=0)


def test_vigia_nao_existe_no_emulador_original(tmp_path: Path) -> None:
    with Simulador("original", pasta_estados=tmp_path) as sim:
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        assert not identificar(c).capacidades.vigia
        with pytest.raises(ComandoFalhouError):
            c.vigia_ler()
