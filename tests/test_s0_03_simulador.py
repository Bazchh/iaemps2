"""Card S0-03: simulador do canal do emulador.

Critério de aceite: dado o simulador em modo original, quando se pede capacidades, então vem falha
(modo reduzido); em modo próprio, vem a máscara (modo completo). A ponte que "marca o modo" é o card S1-02;
aqui a prova é no protocolo.
"""

from __future__ import annotations

import socket
import struct
import time
from pathlib import Path

import pytest

from iaemps2.ponte import protocolo as p
from iaemps2.simulador.servidor import VERSAO_SIMULADA, Simulador


def pedido(*cmds: bytes) -> bytes:
    return p.empacotar_pedido(*cmds)


def resposta(dados: bytes) -> tuple[int, bytes]:
    tamanho, resultado = struct.unpack_from("<IB", dados, 0)
    assert tamanho == len(dados)
    return resultado, dados[5:]


def test_versao_sem_jogo_responde() -> None:
    sim = Simulador()
    r, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.VERSION))))
    assert r == p.Resultado.OK
    assert p.ler_texto(corpo, 0)[0] == VERSAO_SIMULADA


def test_identificacao_e_status() -> None:
    sim = Simulador()
    r, corpo = resposta(
        sim.processar(
            pedido(
                p.comando(p.Codigo.TITLE),
                p.comando(p.Codigo.ID),
                p.comando(p.Codigo.UUID),
                p.comando(p.Codigo.GAME_VERSION),
                p.comando(p.Codigo.STATUS),
            )
        )
    )
    assert r == p.Resultado.OK
    titulo, i = p.ler_texto(corpo, 0)
    serial, i = p.ler_texto(corpo, i)
    crc, i = p.ler_texto(corpo, i)
    versao, i = p.ler_texto(corpo, i)
    (status,) = struct.unpack_from("<I", corpo, i)
    assert (titulo, serial, crc, versao, status) == ("Resident Evil 4", "SLUS-21134", "013e349d", "1.01", 0)


def test_capacidades_falham_no_original_e_respondem_no_proprio() -> None:
    r, _ = resposta(Simulador("original").processar(pedido(p.comando(p.Codigo.EXT_CAPABILITIES))))
    assert r == p.Resultado.FALHA
    r, corpo = resposta(Simulador("proprio").processar(pedido(p.comando(p.Codigo.EXT_CAPABILITIES))))
    assert r == p.Resultado.OK
    versao, mascara = struct.unpack("<HI", corpo)
    assert versao == p.VERSAO_EXTENSAO and mascara == p.CAP_PAUSA | p.CAP_VELOCIDADE


def test_leitura_e_escrita_de_memoria() -> None:
    sim = Simulador()
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.WRITE32, struct.pack("<II", 0x1000, 720)))))
    assert r == p.Resultado.OK
    r, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.READ32, struct.pack("<I", 0x1000)))))
    assert r == p.Resultado.OK and struct.unpack("<I", corpo)[0] == 720
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.READ8, struct.pack("<I", 0xFFFFFFFF)))))
    assert r == p.Resultado.FALHA


def test_um_comando_ruim_falha_o_pedido_inteiro() -> None:
    sim = Simulador()
    r, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.VERSION), bytes([0x55]))))
    assert r == p.Resultado.FALHA and corpo == b""


def test_tamanho_errado_falha() -> None:
    sim = Simulador()
    r, _ = resposta(sim.processar(struct.pack("<I", 99) + bytes([p.Codigo.VERSION])))
    assert r == p.Resultado.FALHA


def test_pausa_pela_extensao() -> None:
    sim = Simulador("proprio")
    sim.processar(pedido(p.comando(p.Codigo.EXT_SET_PAUSED, b"\x01")))
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.STATUS))))
    assert struct.unpack("<I", corpo)[0] == p.Status.PAUSADO
    sim.processar(pedido(p.comando(p.Codigo.EXT_SET_PAUSED, b"\x00")))
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.STATUS))))
    assert struct.unpack("<I", corpo)[0] == p.Status.RODANDO


def test_velocidade_com_vigia_volta_sozinha() -> None:
    agora = [100.0]
    sim = Simulador("proprio", relogio=lambda: agora[0])
    sim.processar(
        pedido(p.comando(p.Codigo.EXT_SET_SPEED, struct.pack("<BfI", p.ModoVelocidade.LENTA, 0.5, 5000)))
    )
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.EXT_GET_SPEED))))
    modo, alvo, restante = struct.unpack("<BfI", corpo)
    assert (modo, alvo, restante) == (p.ModoVelocidade.LENTA, 0.5, 5000)
    agora[0] = 104.0
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.EXT_GET_SPEED))))
    assert struct.unpack("<BfI", corpo)[2] == 1000
    agora[0] = 105.5  # a plataforma "caiu": ninguém mandou voltar
    sim.vigiar()
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.EXT_GET_SPEED))))
    modo, alvo, restante = struct.unpack("<BfI", corpo)
    assert (modo, alvo, restante) == (p.ModoVelocidade.NORMAL, 1.0, 0)


def test_velocidade_modo_normal_desarma() -> None:
    sim = Simulador("proprio")
    sim.processar(
        pedido(p.comando(p.Codigo.EXT_SET_SPEED, struct.pack("<BfI", p.ModoVelocidade.TURBO, 2.0, 60000)))
    )
    sim.processar(
        pedido(p.comando(p.Codigo.EXT_SET_SPEED, struct.pack("<BfI", p.ModoVelocidade.NORMAL, 1.0, 0)))
    )
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.EXT_GET_SPEED))))
    assert struct.unpack("<BfI", corpo)[0] == p.ModoVelocidade.NORMAL


def test_salvar_estado_responde_ok_e_grava_depois(tmp_path: Path) -> None:
    sim = Simulador(pasta_estados=tmp_path, atraso_salvamento_s=0.15)
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.SAVE_STATE, bytes([90])))))
    assert r == p.Resultado.OK
    arquivo = sim.arquivo_estado(90)
    assert arquivo is not None and arquivo.name == "SLUS-21134 (013E349D).90.p2s"
    assert not arquivo.exists()  # ainda não: é assíncrono, como no emulador
    fim = time.monotonic() + 3
    tamanhos: list[int] = []
    while time.monotonic() < fim:
        if arquivo.exists():
            tamanhos.append(arquivo.stat().st_size)
            if len(tamanhos) >= 2 and tamanhos[-1] == tamanhos[-2] and tamanhos[-1] == 16 * 4000:
                break
        time.sleep(0.05)
    assert tamanhos and tamanhos[-1] == 16 * 4000
    assert min(tamanhos) < max(tamanhos)  # cresceu: "existe" não é "pronto" (LC-11)


def test_cenario_salvamento_nunca_aparece(tmp_path: Path) -> None:
    sim = Simulador(
        pasta_estados=tmp_path, atraso_salvamento_s=0.01, cenarios={"salvamento_nunca_aparece": 1}
    )
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.SAVE_STATE, bytes([90])))))
    assert r == p.Resultado.OK
    time.sleep(0.1)
    arquivo = sim.arquivo_estado(90)
    assert arquivo is not None and not arquivo.exists()


def test_cenario_carregando() -> None:
    agora = [0.0]
    sim = Simulador(relogio=lambda: agora[0], cenarios={"carregando": 3})
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.TITLE))))
    assert r == p.Resultado.FALHA
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.STATUS))))
    assert struct.unpack("<I", corpo)[0] == p.Status.DESLIGADO
    agora[0] = 3.5
    r, _ = resposta(sim.processar(pedido(p.comando(p.Codigo.TITLE))))
    assert r == p.Resultado.OK


def test_cenario_troca_serial() -> None:
    sim = Simulador(cenarios={"troca_serial": 2})
    for _ in range(3):
        sim.processar(pedido(p.comando(p.Codigo.STATUS)))
    _, corpo = resposta(sim.processar(pedido(p.comando(p.Codigo.ID))))
    assert p.ler_texto(corpo, 0)[0] == "SLUS-99999"


def test_cenario_desconhecido_e_recusado() -> None:
    with pytest.raises(ValueError, match="cenário desconhecido"):
        Simulador(cenarios={"meteoro": 1})


# ---- pela porta, como a ponte vai usar ----


def _conversar(porta: int, dados: bytes, timeout: float = 2.0) -> bytes:
    with socket.create_connection(("127.0.0.1", porta), timeout=timeout) as s:
        s.sendall(dados)
        cabecalho = s.recv(5)
        (tamanho,) = struct.unpack_from("<I", cabecalho, 0)
        corpo = cabecalho
        while len(corpo) < tamanho:
            corpo += s.recv(tamanho - len(corpo))
        return corpo


def test_servidor_responde_pela_porta() -> None:
    with Simulador("proprio") as sim:
        assert sim.porta is not None and sim.porta > 0
        r, corpo = resposta(
            _conversar(sim.porta, pedido(p.comando(p.Codigo.VERSION), p.comando(p.Codigo.ID)))
        )
        assert r == p.Resultado.OK
        versao, i = p.ler_texto(corpo, 0)
        serial, _ = p.ler_texto(corpo, i)
        assert versao == VERSAO_SIMULADA and serial == "SLUS-21134"


def test_cenario_canal_cai() -> None:
    with Simulador(cenarios={"canal_cai": 1}) as sim:
        assert sim.porta is not None
        with socket.create_connection(("127.0.0.1", sim.porta), timeout=2.0) as s:
            s.sendall(pedido(p.comando(p.Codigo.VERSION)))
            assert s.recv(5)  # o primeiro responde
            s.recv(200)
            s.sendall(pedido(p.comando(p.Codigo.VERSION)))
            assert s.recv(5) == b""  # o segundo: conexão fechada sem resposta


def test_cenario_status_trava() -> None:
    with Simulador(cenarios={"status_trava": 1.0}) as sim:
        assert sim.porta is not None
        with socket.create_connection(("127.0.0.1", sim.porta), timeout=0.3) as s:
            s.sendall(pedido(p.comando(p.Codigo.STATUS)))
            with pytest.raises(TimeoutError):
                s.recv(5)
