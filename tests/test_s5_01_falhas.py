"""Card S5-01: falhas classificadas do serviço e do emulador (contrato 4; casos G02 e G03).

Critério de aceite: dado o serviço respondendo erro 503 por três ciclos, quando a sessão roda, então o overlay
mostra a falha em destaque, nenhuma ação acontece, e no quarto ciclo com resposta válida o mestre retoma
sozinho, tudo registrado.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from iaemps2.catalogo import catalogo as cat
from iaemps2.config import Config
from iaemps2.olho import captura as cap
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import CanalError, Cliente
from iaemps2.servicos.base import ServicoError
from iaemps2.servicos.falso import ServicoFalso
from iaemps2.sessao.abrir import abrir
from iaemps2.sessao.ciclo import PainelSilencioso, Sessao
from iaemps2.sessao.maquina import Estado, Evento
from iaemps2.sessao.relogio import Contador
from iaemps2.simulador.servidor import Simulador

SIT = '{"descricao": "%s", "fase": "%s", "aperto": %d, "confianca": 0.9}'
EXPLORA = SIT % ("Leon anda por uma estrada vazia", "exploracao", 0)
NADA = '{"alavanca": "nada", "parametros": {}, "motivo": "Calma."}'
FORA_DO_AR = ServicoError("fora_do_ar", "503")


class Cenas:
    def __init__(self) -> None:
        self.cor = 10

    def mudar(self) -> None:
        self.cor = (self.cor + 90) % 256

    def __call__(self, overlay: cap.Retangulo | None) -> cap.Captura:
        imagem = Image.new("RGB", (640, 360), (self.cor, self.cor, self.cor))
        return cap.preparar(imagem, cap.Retangulo(0, 0, 640, 360), 640, 70)


def _config(tmp_path: Path) -> Config:
    c = Config()
    c.emulador.pasta_estados = str(tmp_path / "sstates")
    c.sessoes.pasta = str(tmp_path / "sessoes")
    c.captura.intervalo_ms = 500
    return c


def _sessao(
    tmp_path: Path,
    sim: Simulador,
    servico: ServicoFalso,
    cenas: Cenas,
    agora: list[float],
    config: Config | None = None,
    processo_vivo: list[bool] | None = None,
) -> Sessao:
    config = config or _config(tmp_path)
    config.canal.porta = sim.porta or 0
    contador = Contador(relogio=lambda: agora[0])
    vivo = processo_vivo if processo_vivo is not None else [True]
    s = abrir(
        config,
        PainelSilencioso(contador.agora_ms),
        pedir_aceite=lambda texto: True,
        intensidade=cat.Intensidade.FORTE,
        servico=servico,
        capturar=cenas,
        contador=contador,
        cliente=Cliente(porta=sim.porta or 0),
        pasta_sessoes=tmp_path / "sessoes",
        processo_vivo=lambda: vivo[0],
    )
    s.iniciar()
    return s


def _falhas(s: Sessao) -> list[tuple[str, str, int]]:
    return [
        (r[0], r[1], r[2])
        for r in s.con.execute("select origem, classe, visivel from falhas order by id").fetchall()
    ]


def test_criterio_de_aceite_tres_503_e_retomada_sozinha(tmp_path: Path) -> None:
    agora = [1000.0]
    cenas = Cenas()
    servico = ServicoFalso(respostas=[FORA_DO_AR, FORA_DO_AR, FORA_DO_AR, EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.passo()  # falha 1: silencia por 4 s
        assert s.laco.estado == Estado.SILENCIADA
        assert s.painel.painel.falha is not None and "fora_do_ar" in s.painel.painel.falha
        agora[0] += 5
        s.passo()  # a espera venceu: volta a observar
        assert s.laco.estado == Estado.OBSERVANDO
        cenas.mudar()
        s.passo()  # falha 2: silencia por 8 s (a contagem não zerou na volta)
        assert s.laco.estado == Estado.SILENCIADA and s.falhas_seguidas_do_servico == 2
        agora[0] += 5
        s.passo()
        assert s.laco.estado == Estado.SILENCIADA  # 5 s não bastam: o intervalo cresceu de verdade
        agora[0] += 4
        s.passo()
        assert s.laco.estado == Estado.OBSERVANDO
        cenas.mudar()
        s.passo()  # falha 3: 16 s
        assert s.falhas_seguidas_do_servico == 3
        agora[0] += 17
        s.passo()
        cenas.mudar()
        s.passo()  # quarto ciclo com resposta válida: retoma sozinho
        assert s.laco.estado == Estado.DECIDINDO and s.falhas_seguidas_do_servico == 0
        assert s.painel.painel.falha is None
        assert s.con.execute("select count(*) from intervencoes").fetchone()[0] == 0
        assert _falhas(s) == [("servico", "fora_do_ar", 1)] * 3
        assert s.resumo()["falhas"] == 3
        s.con.close()


def test_recusa_nao_silencia_e_a_proxima_captura_vai_inteira(tmp_path: Path) -> None:
    agora = [0.0]
    cenas = Cenas()
    servico = ServicoFalso(respostas=[ServicoError("recusa", "política"), EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.passo()
        assert s.laco.estado == Estado.OBSERVANDO  # não silencia
        assert _falhas(s) == [("servico", "recusa", 1)]
        agora[0] += 1
        s.passo()  # mesma imagem, mas a referência foi esquecida: vai de novo e é descrita
        assert s.laco.estado == Estado.DECIDINDO
        s.con.close()


def test_formato_silencia_so_na_segunda_seguida(tmp_path: Path) -> None:
    agora = [0.0]
    cenas = Cenas()
    # o olho tenta duas vezes por ciclo: cada ciclo inválido consome duas respostas
    servico = ServicoFalso(respostas=["{a", "{b", "{c", "{d", EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.passo()
        assert s.laco.estado == Estado.OBSERVANDO and s.formato_seguidos == 1  # situação inválida, segue
        cenas.mudar()
        s.passo()
        assert s.laco.estado == Estado.SILENCIADA
        assert _falhas(s) == [("servico", "formato", 1)]
        agora[0] += 5
        s.passo()
        cenas.mudar()
        s.passo()
        assert s.laco.estado == Estado.DECIDINDO and s.formato_seguidos == 0
        s.con.close()


def test_limite_informado_pelo_servico_manda_na_espera(tmp_path: Path) -> None:
    agora = [0.0]
    cenas = Cenas()
    servico = ServicoFalso(respostas=[ServicoError("limite", "cota", espera_s=60), EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora)
        s.passo()
        assert s.laco.estado == Estado.SILENCIADA
        agora[0] += 30
        s.passo()
        assert s.laco.estado == Estado.SILENCIADA  # 60 s informados, não os 4 s padrão
        agora[0] += 31
        s.passo()
        assert s.laco.estado == Estado.OBSERVANDO
        s.con.close()


def test_falhas_prolongadas_pausam_o_mestre_e_so_o_jogador_retoma(tmp_path: Path) -> None:
    agora = [0.0]
    cenas = Cenas()
    config = _config(tmp_path)
    config.servico.limite_falhas_seguidas = 4
    servico = ServicoFalso(respostas=[FORA_DO_AR] * 4 + [EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, cenas, agora, config=config)
        for _ in range(3):
            s.passo()  # falha
            agora[0] += 40  # além da espera máxima
            s.passo()  # volta
            cenas.mudar()
        assert s.laco.estado == Estado.OBSERVANDO and s.falhas_seguidas_do_servico == 3
        s.passo()  # quarta falha seguida: o mestre se pausa
        assert s.laco.estado == Estado.PAUSADA_JOGADOR and s.painel.painel.pausado
        assert "4 falhas seguidas" in (s.painel.painel.ultima_acao or "") + (s.painel.painel.motivo or "")
        assert s.con.execute("select count(*) from marcos where tipo = 'pausa_por_falhas'").fetchone()[0] == 1
        agora[0] += 100
        s.passo()
        assert s.laco.estado == Estado.PAUSADA_JOGADOR  # o tempo não retoma; só o jogador
        s.gesto("pausar")
        s.passo()  # retomou e já observou a cena válida no mesmo passo
        assert s.laco.estado == Estado.DECIDINDO and s.falhas_seguidas_do_servico == 0
        s.con.close()


def test_emulador_fechado_encerra_a_sessao_marcando_a_queda(tmp_path: Path) -> None:
    agora = [0.0]
    vivo = [True]
    servico = ServicoFalso(respostas=[EXPLORA], decisoes=[NADA])
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, servico, Cenas(), agora, processo_vivo=vivo)
        s.passo()
        assert s.laco.estado == Estado.DECIDINDO
        sim.parar()  # o emulador some
        vivo[0] = False
        s.passo()  # decide 'nada' sem o canal
        s.passo()  # o ciclo seguinte sonda o canal: falha do emulador -> silenciada
        assert s.laco.estado == Estado.SILENCIADA and s.origem_do_silencio == "emulador"
        agora[0] += 3
        s.passo()  # processo ausente: fechado -> encerrada com a queda marcada
        assert s.laco.estado == Estado.ENCERRADA and s.encerrada.is_set()
        assert s.con.execute("select count(*) from marcos where tipo = 'queda_emulador'").fetchone()[0] == 1
        assert any(classe == "fechado" for _, classe, _ in _falhas(s))
        assert s.resumo()["falhas"] >= 2
        s.con.close()


def test_emulador_travado_vira_fechado_depois_do_limite(tmp_path: Path) -> None:
    agora = [0.0]
    config = _config(tmp_path)
    config.emulador.limite_travado_s = 10
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, ServicoFalso(), Cenas(), agora, config=config)
        s.fila.enfileirar(Evento.PRONTO)
        s.laco.processar_todos()
        s.origem_do_silencio = "emulador"
        s.fila.enfileirar(Evento.FALHA_EMULADOR, origem="plataforma", classe="travado")
        s.laco.processar_todos()
        assert s.laco.estado == Estado.SILENCIADA
        s._classificar_emulador(CanalError("travado", "sem resposta"), 1_000)
        assert s.laco.estado == Estado.SILENCIADA and "travado" in (s.painel.painel.falha or "")
        s._classificar_emulador(CanalError("travado", "sem resposta"), 8_000)
        assert s.laco.estado == Estado.SILENCIADA  # ainda dentro do limite
        s._classificar_emulador(CanalError("travado", "sem resposta"), 12_000)
        assert s.laco.estado == Estado.ENCERRADA  # além do limite: tratado como fechado
        s.con.close()


def test_ao_reconectar_velocidade_fora_do_normal_sem_acao_em_vigor_volta(tmp_path: Path) -> None:
    agora = [0.0]
    with Simulador("proprio", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, ServicoFalso(), Cenas(), agora)
        s.cliente.velocidade(
            p.ModoVelocidade.LENTA, 0.5, 0
        )  # o emulador ficou alterado enquanto o mestre caiu
        assert not s.executor.pendentes
        s._conferir_emulador_ao_voltar()
        assert s.cliente.velocidade_atual().modo == p.ModoVelocidade.NORMAL
        assert ("emulador", "velocidade_restaurada", 0) in _falhas(s)
        s.con.close()


def test_falha_sem_processar_so_enfileira(tmp_path: Path) -> None:
    """A thread do relógio de fim nunca mexe na máquina: só enfileira; o laço processa."""
    agora = [0.0]
    with Simulador("original", pasta_estados=tmp_path / "sstates", relogio=lambda: agora[0]) as sim:
        s = _sessao(tmp_path, sim, ServicoFalso(), Cenas(), agora)
        s.laco.processar_todos()
        assert s.laco.estado == Estado.OBSERVANDO
        s._falha("emulador", "x", "y", processar=False)
        assert s.laco.estado == Estado.OBSERVANDO and s.fila.pendentes() == 1
        s.laco.processar_todos()
        assert s.laco.estado == Estado.SILENCIADA
        s.con.close()
