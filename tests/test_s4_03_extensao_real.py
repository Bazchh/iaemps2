"""Cards S4-02 e S4-03 contra o emulador REAL (pulado sem IAEMPS2_TESTES_REAIS=1).

Precisa de uma instância só do emulador na porta 28011 com o jogo de abertura rodando. Com o binário
próprio, prova a extensão inteira, inclusive o vigia com o cliente morto. Com o original instalado,
prova que 0x80 falha e os códigos originais seguem iguais (regressão).

Critério S4-02: capacidades devolvem versão 1 e máscara 3; no original, falha.
Critério S4-03: câmera lenta de 5 s pedida pelo canal, cliente morto no segundo 2, o jogo volta ao
normal no segundo 5 sozinho, e a consulta de velocidade confirma.
"""

from __future__ import annotations

import struct
import time

import pytest

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente, ComandoFalhouError
from iaemps2.ponte.emulador import identificar

pytestmark = pytest.mark.emulador


def _codigos_originais(c: Cliente) -> None:
    assert c.status() == p.Status.RODANDO
    ident = identificar(c).identificacao
    assert ident.serial and ident.crc and ident.titulo
    corpo = c.pedir(
        p.comando(p.Codigo.READ8, struct.pack("<I", 0)) + p.comando(p.Codigo.READ32, struct.pack("<I", 0x100))
    )
    assert len(corpo) == 5
    assert len(c.pedir(p.comando(p.Codigo.READ64, struct.pack("<I", 0x1000)))) == 8
    assert len(c.pedir(p.comando(p.Codigo.READ32, struct.pack("<I", 0x01FFFFF0)))) == 4


def test_extensao_ou_regressao_no_emulador_real() -> None:
    c = Cliente(porta=28011)
    c.conectar()
    versao = c.versao()
    jogo = identificar(c)
    _codigos_originais(c)

    if jogo.modo == "reduzido":
        with pytest.raises(ComandoFalhouError):
            c.pedir(p.comando(p.Codigo.EXT_CAPABILITIES))
        assert "+iaemps2" not in versao
        c.fechar()
        return

    # S4-02
    assert "+iaemps2-ext1" in versao
    assert struct.unpack("<HI", c.pedir(p.comando(p.Codigo.EXT_CAPABILITIES))) == (1, 3)

    # S4-03: pausa confirmada pelo status
    c.pausar(True)
    time.sleep(0.5)
    assert c.status() == p.Status.PAUSADO
    c.pausar(False)
    time.sleep(0.5)
    assert c.status() == p.Status.RODANDO

    # argumentos inválidos são recusados e não mudam nada
    for args in [(7, 0.5, 1000), (1, 0.0, 1000), (2, -1.0, 1000)]:
        with pytest.raises(ComandoFalhouError):
            c.pedir(p.comando(p.Codigo.EXT_SET_SPEED, struct.pack("<BfI", *args)))
    v = c.velocidade_atual()
    assert v.modo == p.ModoVelocidade.NORMAL and v.alvo == pytest.approx(1.0)

    # escalar novo no mesmo modo pega; modo 0 volta agora
    c.velocidade(p.ModoVelocidade.LENTA, 0.5, 0)
    time.sleep(0.3)
    assert c.velocidade_atual().alvo == pytest.approx(0.5)
    c.velocidade(p.ModoVelocidade.LENTA, 0.25, 0)
    time.sleep(0.3)
    assert c.velocidade_atual().alvo == pytest.approx(0.25)
    c.velocidade(p.ModoVelocidade.NORMAL, 1.0, 0)
    time.sleep(0.3)
    assert c.velocidade_atual().modo == p.ModoVelocidade.NORMAL

    # o critério literal: lenta 5 s, cliente morto no segundo 2, volta sozinho no 5
    t0 = time.monotonic()
    c.velocidade(p.ModoVelocidade.LENTA, 0.5, 5000)
    time.sleep(0.3)
    v = c.velocidade_atual()
    assert v.modo == p.ModoVelocidade.LENTA and 4000 < v.restante_ms <= 5000
    time.sleep(2.0 - (time.monotonic() - t0))
    c.fechar()
    time.sleep(4.0 - (time.monotonic() - t0))
    c2 = Cliente(porta=28011)
    c2.conectar()
    v = c2.velocidade_atual()
    assert v.modo == p.ModoVelocidade.LENTA and 0 < v.restante_ms < 1500
    time.sleep(5.6 - (time.monotonic() - t0))
    v = c2.velocidade_atual()
    assert v.modo == p.ModoVelocidade.NORMAL and v.alvo == pytest.approx(1.0) and v.restante_ms == 0

    # turbo com prazo curto
    c2.velocidade(p.ModoVelocidade.TURBO, 2.0, 1000)
    time.sleep(0.3)
    assert c2.velocidade_atual().modo == p.ModoVelocidade.TURBO
    time.sleep(1.2)
    assert c2.velocidade_atual().modo == p.ModoVelocidade.NORMAL
    assert c2.status() == p.Status.RODANDO
    c2.fechar()
