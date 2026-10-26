"""Card S1-01: cliente do canal, conectar e sondar.

Critério de aceite: dado o emulador lançado com o jogo, quando a ponte conecta no mesmo instante, então ela
espera, e marca "canal pronto" só quando o status vira "rodando", registrando a versão do emulador.
Provado aqui contra o simulador com o cenário "carregando"; e contra o emulador real no teste marcado.
"""

from __future__ import annotations

import socket
import threading

import pytest

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import CanalError, Cliente, ComandoFalhouError
from iaemps2.simulador.servidor import VERSAO_SIMULADA, Simulador


def test_versao_status_e_identificacao() -> None:
    with Simulador() as sim, Cliente(porta=sim.porta or 0) as c:
        assert c.versao() == VERSAO_SIMULADA
        assert c.status() == p.Status.RODANDO
        ident = c.identificar()
        assert (ident.titulo, ident.serial, ident.crc, ident.versao_jogo) == (
            "Resident Evil 4",
            "SLUS-21134",
            "013e349d",
            "1.01",
        )


def test_espera_o_jogo_carregar() -> None:
    agora = [0.0]
    dormidas: list[float] = []

    def dormir(s: float) -> None:
        dormidas.append(s)
        agora[0] += s

    with Simulador(relogio=lambda: agora[0], cenarios={"carregando": 2.5}) as sim:
        c = Cliente(porta=sim.porta or 0, relogio=lambda: agora[0], dormir=dormir)
        c.conectar()
        assert c.versao() == VERSAO_SIMULADA  # a versão responde antes do jogo
        with pytest.raises(ComandoFalhouError):
            c.identificar()  # título dá falha enquanto carrega, como no emulador
        assert c.status() == p.Status.DESLIGADO
        assert c.esperar_jogo(limite_s=10, intervalo_s=1.0) == p.Status.RODANDO
        assert len(dormidas) == 3  # sondou em 0, 1, 2 e viu rodando em 3
        c.fechar()


def test_espera_desiste_no_limite() -> None:
    agora = [0.0]

    def dormir(s: float) -> None:
        agora[0] += s

    with Simulador(relogio=lambda: agora[0], cenarios={"carregando": 999}) as sim:
        c = Cliente(porta=sim.porta or 0, relogio=lambda: agora[0], dormir=dormir)
        assert c.esperar_jogo(limite_s=5, intervalo_s=1.0) == p.Status.DESLIGADO
        assert agora[0] >= 5


def test_porta_fechada() -> None:
    livre = socket.socket()
    livre.bind(("127.0.0.1", 0))
    porta = livre.getsockname()[1]
    livre.close()
    with pytest.raises(CanalError) as erro:
        Cliente(porta=porta).conectar()
    assert erro.value.classe == "porta_fechada"


def test_outro_programa_na_porta() -> None:
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    porta = servidor.getsockname()[1]

    def responder_http() -> None:
        cliente, _ = servidor.accept()
        cliente.recv(100)
        cliente.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        cliente.close()

    threading.Thread(target=responder_http, daemon=True).start()
    try:
        c = Cliente(porta=porta, tempo_limite_s=2)
        with pytest.raises(CanalError) as erro:
            c.versao()
        assert erro.value.classe == "outro_programa"
    finally:
        servidor.close()


def test_canal_cai_e_reconecta() -> None:
    with Simulador(cenarios={"canal_cai": 1}) as sim:
        c = Cliente(porta=sim.porta or 0, tempo_limite_s=2)
        assert c.versao() == VERSAO_SIMULADA  # 1º comando responde
        assert c.versao() == VERSAO_SIMULADA  # 2º: conexão cai, o cliente reconecta e repete
        assert c.reconexoes == 1


def test_status_travado_vira_classe_travado() -> None:
    with Simulador(cenarios={"status_trava": 1.0}) as sim:
        c = Cliente(porta=sim.porta or 0, tempo_limite_s=0.3)
        with pytest.raises(CanalError) as erro:
            c.status()
        assert erro.value.classe == "travado"
        assert not c.conectado


def test_falha_de_comando_nao_derruba_a_conexao() -> None:
    with Simulador("original") as sim, Cliente(porta=sim.porta or 0) as c:
        with pytest.raises(ComandoFalhouError):
            c.pedir(p.comando(p.Codigo.EXT_CAPABILITIES))
        assert c.conectado and c.versao() == VERSAO_SIMULADA


@pytest.mark.emulador
def test_emulador_real_identifica_o_jogo_de_abertura() -> None:
    with Cliente() as c:
        assert c.versao().startswith("PCSX2 v2.8")
        assert c.esperar_jogo(limite_s=90) == p.Status.RODANDO
        ident = c.identificar()
        assert ident.serial == "SLUS-21134" and ident.crc == "013e349d"
