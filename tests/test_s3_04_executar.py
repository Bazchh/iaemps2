"""Card S3-04: executar e reverter pelo caso de uso de cada alavanca.

Critério de aceite: dado uma recarga executada, quando o jogador reverte, então o slot de volta é recarregado,
a intervenção fica revertida_por e o próximo pedido ao serviço leva o marco de reversão.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from iaemps2.catalogo import catalogo as cat
from iaemps2.mestre import memoria
from iaemps2.mestre.decisao import Veredito
from iaemps2.olho.situacao import Fase, Situacao
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente
from iaemps2.ponte.emulador import SEM_EXTENSAO, Capacidades
from iaemps2.ponte.estados import FilaDeSlots
from iaemps2.registro import banco
from iaemps2.sessao.executor import Executor
from iaemps2.sessao.relogio import Contador
from iaemps2.simulador.servidor import Simulador

COMPLETO = Capacidades(1, True, True, False)
COMBATE_3 = Situacao(descricao="cerco", fase=Fase.COMBATE, aperto=3, confianca=0.9)


@dataclass
class Bancada:
    sim: Simulador
    cliente: Cliente
    con: sqlite3.Connection
    sessao: str
    ciclo: int
    executor: Executor
    agora: list[float]

    def decisao(self, alavanca: str, parametros: dict[str, float]) -> int:
        return banco.gravar_decisao(
            self.con,
            {
                "ciclo_id": self.ciclo,
                "catalogo_versao": self.executor.catalogo.versao,
                "alavanca": alavanca,
                "parametros_json": json.dumps(parametros),
                "motivo": "m",
                "motivo_origem": "servico",
                "origem": "servico",
                "pedido_bruto": "{}",
            },
        )

    def executar(self, alavanca: str, **parametros: float) -> tuple[int, str, dict[str, float] | None]:
        v = Veredito(alavanca, parametros, "m", "servico", "servico")
        e = self.executor.executar(v, self.decisao(alavanca, parametros), COMBATE_3, p.Status.RODANDO)
        return e.intervencao_id, e.resultado, e.caminho_volta

    def intervencao(self, id_: int) -> sqlite3.Row:
        linha = self.con.execute("select * from intervencoes where id = ?", (id_,)).fetchone()
        assert linha is not None
        return linha


@pytest.fixture
def bancada(tmp_path: Path) -> Iterator[Bancada]:
    agora = [1000.0]
    with Simulador(
        "proprio", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.2, relogio=lambda: agora[0]
    ) as sim:
        cliente = Cliente(porta=sim.porta or 0)
        con = banco.criar(tmp_path / "s.sqlite")
        sessao = banco.abrir_sessao(
            con,
            jogo_titulo="J",
            jogo_serial="SLUS-21134",
            jogo_crc="013e349d",
            jogo_versao="1.01",
            emulador_versao="sim",
            modo="completo",
            tom="imprevisivel",
            intensidade="media",
            servico="falso",
            aceite_versao="1",
            config_json="{}",
        )
        ciclo = banco.gravar_ciclo(con, sessao, 1, 0, "rodando", "executando")
        contador = Contador(relogio=lambda: agora[0])
        slots = FilaDeSlots(tmp_path / "sstates", "SLUS-21134", "013e349d", list(range(90, 100)))
        executor = Executor(cliente, slots, con, sessao, contador, cat.montar(COMPLETO))
        yield Bancada(sim, cliente, con, sessao, ciclo, executor, agora)
        cliente.fechar()
        con.close()


def test_criterio_de_aceite_reverter_recarga(bancada: Bancada) -> None:
    # dois estados guardados: o destino (aperto baixo) e o atual
    bancada.executor._salvar(
        Situacao(descricao="calmo", fase=Fase.EXPLORACAO, aperto=1, confianca=1), "periodico", 93
    )
    id_, resultado, volta = bancada.executar("recarregar", slot=93)
    assert resultado == "confirmada" and volta is not None and volta["slot"] != 93
    linha = bancada.intervencao(id_)
    assert linha["resultado"] == "confirmada" and json.loads(linha["caminho_volta_json"]) == volta
    assert bancada.executor.ultima_reversivel is not None
    r = bancada.executor.reverter(bancada.ciclo)
    assert r is not None and r.resultado == "confirmada" and r.alavanca == "recarregar"
    assert bancada.intervencao(id_)["revertida_por"] == r.intervencao_id
    assert bancada.intervencao(r.intervencao_id)["origem"] == "reversao_jogador"
    m = memoria.reconstruir(bancada.con, bancada.sessao, agora_ms=10_000)
    assert m.marcos[0]["tipo"] == "reversao" and m.revertidas_pelo_jogador == ["recarregar"]
    assert bancada.executor.ultima_reversivel is None and bancada.executor.reverter(bancada.ciclo) is None


def test_pausa_confirma_e_termina_pela_plataforma(bancada: Bancada) -> None:
    id_, resultado, _ = bancada.executar("pausa", duracao_s=3)
    assert resultado == "confirmada" and bancada.cliente.status() == p.Status.PAUSADO
    assert bancada.executor.encerrar_vencidos() == []  # ainda não venceu
    bancada.agora[0] += 3.5
    assert bancada.executor.encerrar_vencidos() == [id_]
    assert bancada.cliente.status() == p.Status.RODANDO
    assert bancada.intervencao(id_)["fim_ms"] is not None


def test_camera_lenta_confirma_pela_consulta_de_velocidade(bancada: Bancada) -> None:
    id_, resultado, _ = bancada.executar("camera_lenta", escalar=0.5, duracao_s=5)
    assert resultado == "confirmada"
    v = bancada.cliente.velocidade_atual()
    assert v.modo == p.ModoVelocidade.LENTA and v.alvo == 0.5
    antes = json.loads(bancada.intervencao(id_)["estado_antes_json"])
    depois = json.loads(bancada.intervencao(id_)["estado_depois_json"])
    assert antes["velocidade"] == 1.0 and depois["velocidade"] == 0.5
    # o jogador reverte no meio: volta ao normal na hora
    r = bancada.executor.reverter(bancada.ciclo)
    assert r is not None and bancada.cliente.velocidade_atual().modo == p.ModoVelocidade.NORMAL
    assert bancada.intervencao(id_)["fim_ms"] is not None


def test_salvar_estado_registra_contexto_e_nao_e_reversivel(bancada: Bancada) -> None:
    bancada.executor.situacao_id_atual = None
    id_, resultado, _ = bancada.executar("salvar_estado")
    assert resultado == "confirmada" and bancada.intervencao(id_)["reversivel"] == 0
    assert bancada.executor.ultima_reversivel is None
    estados = bancada.con.execute(
        "select slot, motivo, confirmado_ms, bytes from estados_reservados"
    ).fetchall()
    assert len(estados) == 1 and estados[0]["slot"] == 90 and estados[0]["confirmado_ms"] is not None
    assert bancada.executor.aperto_dos_slots == {90: 3}
    assert bancada.executor.catalogo.slots_com_contexto == (90,)


def test_situacao_velha_descarta_sem_comandar(bancada: Bancada) -> None:
    bancada.sim.jogo.status = p.Status.PAUSADO  # o jogador pausou entre a decisão e a execução
    id_, resultado, _ = bancada.executar("camera_lenta", escalar=0.6, duracao_s=4)
    assert resultado == "descartada"
    assert bancada.intervencao(id_)["resultado"] == "descartada"
    assert bancada.cliente.velocidade_atual().modo == p.ModoVelocidade.NORMAL  # nada foi comandado


def test_falha_tres_vezes_tira_a_alavanca(bancada: Bancada) -> None:
    bancada.executor.catalogo = cat.montar(COMPLETO)
    bancada.sim.modo = "original"  # o comando estendido passa a falhar
    for _ in range(3):
        id_, resultado, _ = bancada.executar("pausa", duracao_s=2)
        assert resultado == "falhou" and bancada.intervencao(id_)["resultado"] == "falhou"
    pausa = bancada.executor.catalogo.alavanca("pausa")
    assert pausa is not None and not pausa.disponivel and bancada.executor.catalogo.versao == 2


def test_encerrar_todas_para_pausa_do_mestre(bancada: Bancada) -> None:
    a, _, _ = bancada.executar("turbo", escalar=2.0, duracao_s=8)
    assert bancada.cliente.velocidade_atual().modo == p.ModoVelocidade.TURBO
    assert bancada.executor.encerrar_todas() == [a]
    assert (
        bancada.cliente.velocidade_atual().modo == p.ModoVelocidade.NORMAL
        and bancada.executor.pendentes == []
    )


def test_modo_reduzido_nao_consulta_velocidade(tmp_path: Path) -> None:
    with Simulador("original", pasta_estados=tmp_path) as sim:
        cliente = Cliente(porta=sim.porta or 0)
        con = banco.criar(tmp_path / "r.sqlite")
        sessao = banco.abrir_sessao(
            con,
            jogo_titulo="J",
            jogo_serial="S",
            jogo_crc="0",
            jogo_versao=None,
            emulador_versao="sim",
            modo="reduzido",
            tom="imprevisivel",
            intensidade="media",
            servico="falso",
            aceite_versao="1",
            config_json="{}",
        )
        ex = Executor(
            cliente,
            FilaDeSlots(tmp_path, "S", "0", [90, 91]),
            con,
            sessao,
            Contador(),
            cat.montar(SEM_EXTENSAO),
        )
        estado = ex.estado_atual(None)
        assert estado["velocidade"] == 1.0 and estado["status"] == "rodando"
        cliente.fechar()
        con.close()
