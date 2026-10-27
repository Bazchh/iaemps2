"""Card S3-06: o esqueleto ambulante, ponta a ponta sem emulador real, sem serviço real e sem monitor.

Critério de aceite (a metade automática): dado o simulador com o jogo de abertura, quando uma sessão roda vários
ciclos com situações e decisões gravadas, então toda intervenção está no registro com antes, depois e motivo,
nenhuma fora do catálogo, e o resumo traz custo e latência. A outra metade é a sessão jogada pelo cliente.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from iaemps2.catalogo import catalogo as cat
from iaemps2.config import Config
from iaemps2.olho import captura as cap
from iaemps2.ponte.cliente import Cliente
from iaemps2.servicos.falso import ServicoFalso
from iaemps2.sessao.abrir import abrir
from iaemps2.sessao.ciclo import PainelSilencioso, Sessao, texto_do_resumo
from iaemps2.sessao.maquina import Estado, Evento
from iaemps2.sessao.relogio import Contador
from iaemps2.simulador.servidor import Simulador

SIT = '{"descricao": "%s", "fase": "%s", "aperto": %d, "confianca": 0.9}'
MENU = SIT % ("Tela do cartão de memória", "sistema", 0)
EXPLORA = SIT % ("Leon anda por uma estrada vazia", "exploracao", 0)
COMBATE = SIT % ("Leon cercado por aldeões, pouca vida", "combate", 4)
DEC = '{"alavanca": "%s", "parametros": %s, "motivo": "%s"}'


class Cenas:
    """Capturas sintéticas que mudam quando a cena muda, para o comparador liberar o envio."""

    def __init__(self) -> None:
        self.cor = 10

    def mudar(self) -> None:
        self.cor = (self.cor + 90) % 256

    def __call__(self, overlay: cap.Retangulo | None) -> cap.Captura:
        return cap.preparar(
            Image.new("RGB", (640, 360), (self.cor, self.cor, self.cor)),
            cap.Retangulo(0, 0, 640, 360),
            640,
            70,
        )


def _config(tmp_path: Path) -> Config:
    c = Config()
    c.emulador.pasta_estados = str(tmp_path / "sstates")
    c.sessoes.pasta = str(tmp_path / "sessoes")
    c.servico.preco_entrada_por_milhao = 0.10
    c.servico.preco_saida_por_milhao = 0.40
    c.captura.intervalo_ms = 500
    return c


def _sessao(
    tmp_path: Path, sim: Simulador, servico: ServicoFalso, cenas: Cenas, agora: list[float]
) -> Sessao:
    config = _config(tmp_path)
    config.canal.porta = sim.porta or 0
    contador = Contador(relogio=lambda: agora[0])
    return abrir(
        config,
        PainelSilencioso(contador.agora_ms),
        pedir_aceite=lambda texto: True,
        intensidade=cat.Intensidade.FORTE,
        servico=servico,
        capturar=cenas,
        contador=contador,
        cliente=Cliente(porta=sim.porta or 0),
        pasta_sessoes=tmp_path / "sessoes",
    )


def _avancar(sessao: Sessao, agora: list[float], passos: int, dt: float = 1.0) -> None:
    for _ in range(passos):
        sessao.passo()
        agora[0] += dt


def test_sessao_inteira_no_simulador(tmp_path: Path) -> None:
    agora = [1000.0]
    cenas = Cenas()
    servico = ServicoFalso(
        respostas=[MENU, EXPLORA, COMBATE, EXPLORA],
        decisoes=[
            DEC % ("nada", "{}", "Explorando com calma."),
            DEC % ("camera_lenta", '{"escalar": 0.5, "duracao_s": 3}', "O cerco aperta."),
            DEC % ("teleporte", "{}", "fora do catálogo"),
        ],
    )
    with Simulador(
        "proprio", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.1, relogio=lambda: agora[0]
    ) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        assert s.jogo.modo == "completo" and s.executor.slots.ocupados() == [90]  # estado inicial salvo
        s.iniciar()
        s.passo()  # PRONTO -> observando; captura 1 (menu) -> bloqueada
        assert s.laco.estado == Estado.BLOQUEADA and s.contador.congelado
        _avancar(s, agora, 2)  # sem mudança: ciclos poupados, continua bloqueada
        assert s.laco.estado == Estado.BLOQUEADA
        cenas.mudar()
        s.passo()  # exploração -> cena voltou -> decidindo
        assert s.laco.estado == Estado.DECIDINDO and not s.contador.congelado
        s.passo()  # decide 'nada' -> observando
        assert s.laco.estado == Estado.OBSERVANDO
        agora[0] += 20
        cenas.mudar()
        s.passo()  # combate aperto 4 -> decidindo
        s.passo()  # camera_lenta validada -> executando
        assert s.laco.estado == Estado.EXECUTANDO
        s.passo()  # executa, confirma -> observando; painel mostra ação e motivo
        assert s.laco.estado == Estado.OBSERVANDO
        assert s.painel.painel.ultima_acao == "camera lenta" and s.painel.painel.motivo == "O cerco aperta."
        assert s.cliente.velocidade_atual().modo.name == "LENTA"
        agora[0] += 4
        s.passo()  # a duração venceu: fim registrado
        cenas.mudar()
        agora[0] += 20
        s.passo()  # exploração -> decidindo
        s.passo()  # 'teleporte' descartado -> observando
        assert s.laco.estado == Estado.OBSERVANDO
        # o jogador reverte e depois encerra
        s.gesto("reverter")
        s.passo()
        s.gesto("encerrar")
        s.passo()
        assert s.laco.estado == Estado.ENCERRADA and s.encerrada.is_set()

        r = s.resumo()
        assert r["ciclos"] >= 8 and r["capturas_enviadas"] == 4 and r["capturas_poupadas"] >= 2
        assert r["intervencoes_por_alavanca"] == [{"alavanca": "camera_lenta", "n": 1}]
        assert r["decisoes_nada"] >= 1 and r["decisoes_descartadas"] == 1 and r["reversoes"] == 1
        assert r["latencias"]["descrever"]["n"] == 4 and r["latencias"]["decidir"]["n"] == 3
        assert r["custo_estimado"] is not None and r["custo_estimado"] > 0 and r["tokens_entrada"] > 0
        assert r["falhas"] == 0 and r["estados_salvos"] >= 1
        texto = texto_do_resumo(r)
        assert "camera_lenta x1" in texto and "latência descrever" in texto and "O cerco aperta." in texto

        # toda intervenção do mestre: antes, depois, motivo; nenhuma fora do catálogo
        linhas = s.con.execute(
            "select i.alavanca, i.estado_antes_json, i.estado_depois_json, d.motivo, i.resultado, i.fim_ms from intervencoes i join decisoes d on d.id = i.decisao_id"
        ).fetchall()
        assert len(linhas) == 2  # a câmera lenta e a reversão
        nomes = {a.nome for a in s.executor.catalogo.alavancas}
        for alavanca, antes, depois, motivo, resultado, _fim in linhas:
            assert (
                alavanca in nomes and json.loads(antes)["status"] and json.loads(depois)["status"] and motivo
            )
            assert resultado == "confirmada"
        assert linhas[0][5] is not None  # a câmera lenta tem fim registrado
        assert (s.pasta / "capturas" / "000001.jpg").exists()
        assert s.con.execute("select fechada_em_utc from sessoes").fetchone()[0] is not None
        assert s.laco.recusados == 0
        s.con.close()


def test_falha_do_servico_e_visivel_e_silencia(tmp_path: Path) -> None:
    from iaemps2.servicos.base import ServicoError

    agora = [0.0]
    cenas = Cenas()
    servico = ServicoFalso(respostas=[ServicoError("fora_do_ar", "503"), EXPLORA])
    with Simulador(
        "original", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.1, relogio=lambda: agora[0]
    ) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.iniciar()
        s.passo()
        assert s.laco.estado == Estado.SILENCIADA
        assert s.painel.painel.falha is not None and "fora_do_ar" in s.painel.painel.falha
        assert s.con.execute("select count(*) from falhas where visivel = 1").fetchone()[0] == 1
        agora[0] += 10
        s.passo()  # tenta recuperar: o canal responde -> observando
        assert s.laco.estado == Estado.OBSERVANDO and s.painel.painel.falha is None
        cenas.mudar()
        s.passo()
        assert s.laco.estado == Estado.DECIDINDO
        s.gesto("encerrar")
        s.passo()
        assert s.resumo()["falhas"] == 1
        s.con.close()


def test_pausa_do_jogador_encerra_acoes_e_retoma(tmp_path: Path) -> None:
    agora = [0.0]
    cenas = Cenas()
    servico = ServicoFalso(
        respostas=[COMBATE], decisoes=[DEC % ("turbo", '{"escalar": 2, "duracao_s": 8}', "Sem tempo.")]
    )
    with Simulador(
        "proprio", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.1, relogio=lambda: agora[0]
    ) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.iniciar()
        for _ in range(3):
            s.passo()
        assert s.cliente.velocidade_atual().modo.name == "TURBO"
        s.gesto("pausar")
        s.passo()
        assert s.laco.estado == Estado.PAUSADA_JOGADOR and s.painel.painel.pausado
        assert s.cliente.velocidade_atual().modo.name == "NORMAL"  # encerrou a ação com duração
        s.gesto("pausar")  # o mesmo gesto retoma
        s.passo()
        assert s.laco.estado == Estado.OBSERVANDO and not s.painel.painel.pausado
        s.fila.enfileirar(Evento.JOGADOR_ENCERROU, origem="jogador")
        s.passo()
        s.con.close()


def test_encerrar_apos_prazo(tmp_path: Path) -> None:
    agora = [0.0]
    with Simulador(
        "original", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.1, relogio=lambda: agora[0]
    ) as sim:
        s = _sessao(tmp_path, sim, ServicoFalso(), Cenas(), agora)
        s.encerrar_apos_s = 5
        s.iniciar()
        _avancar(s, agora, 7)
        assert s.laco.estado == Estado.ENCERRADA
        s.con.close()


def test_pausa_termina_no_segundo_certo_sem_depender_do_ciclo(tmp_path: Path) -> None:
    """Prova de fogo: pausas de 3 s duraram 9 e 11 s porque o fim só era visto entre ciclos, e o ciclo esperava
    o serviço. O relógio de fim roda em thread própria."""
    import threading
    import time

    agora = [0.0]
    servico = ServicoFalso(respostas=[COMBATE], decisoes=[DEC % ("pausa", '{"duracao_s": 3}', "Pausa.")])
    with Simulador(
        "proprio", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.1, relogio=lambda: agora[0]
    ) as sim:
        s = _sessao(tmp_path, sim, servico, Cenas(), agora)
        s.iniciar()
        for _ in range(3):
            s.passo()
        assert s.cliente.status().name == "PAUSADO"
        relogio_de_fim = threading.Thread(target=s.vigiar_fins, daemon=True)
        relogio_de_fim.start()
        agora[0] += 4  # o prazo venceu; nenhum passo() é chamado
        limite = time.monotonic() + 2
        while s.cliente.status().name != "RODANDO" and time.monotonic() < limite:
            time.sleep(0.05)
        assert s.cliente.status().name == "RODANDO"
        assert s.con.execute("select fim_ms from intervencoes").fetchone()[0] is not None
        s.encerrada.set()
        relogio_de_fim.join(timeout=2)
        s.con.close()
