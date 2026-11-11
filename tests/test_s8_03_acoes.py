"""Card S8-03: ações de mundo no catálogo (casos H05 e H07).

Critério de aceite (parte automática, contra o simulador): dado uma situação de combate, quando o mestre decide
baixar a vida do jogador até o mínimo da faixa por 20 s, então o valor cai, é relido igual, volta sozinho no
prazo, nunca abaixo do mínimo, e o registro tem antes, depois, motivo e volta. Mais: dano no meio do prazo não
impede a volta (devolve o que tirou), morte no meio não escreve, reversão do jogador devolve antes do prazo,
estado não é salvo com ação em vigor, recarga descarta a ação sem escrever, perfil de outro jogo não entra.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from iaemps2.catalogo import catalogo as cat
from iaemps2.catalogo import mundo
from iaemps2.mestre.decisao import Decisao, Veredito, conferir
from iaemps2.olho.situacao import Fase, Situacao
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente
from iaemps2.ponte.emulador import SEM_EXTENSAO, Capacidades
from iaemps2.ponte.estados import FilaDeSlots
from iaemps2.registro import banco
from iaemps2.sessao.executor import Executor
from iaemps2.sessao.relogio import Contador
from iaemps2.simulador.servidor import Simulador

RAIZ = Path(__file__).resolve().parents[1]
PERFIL = RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
COMPLETO = Capacidades(1, True, True, False)
COMBATE_3 = Situacao(descricao="cerco", fase=Fase.COMBATE, aperto=3, confianca=0.9)
MENU = Situacao(descricao="maleta", fase=Fase.MENU, aperto=0, confianca=0.9)
PG = 0x00425BA0
VIDA, VIDA_MAX = PG + 0x7ED6, PG + 0x7ED8
EM_MGR, VETOR, PASSO = 0x004203B0, 0x01789F40, 0xED0


def _acoes() -> tuple[mundo.AcaoDeMundo, ...]:
    carga = mundo.carregar_perfil(PERFIL, "SLUS-21134", "013e349d")
    assert carga.recusadas == (), carga.recusadas
    return carga.acoes


@dataclass
class Bancada:
    sim: Simulador
    cliente: Cliente
    con: sqlite3.Connection
    sessao: str
    ciclo: int
    executor: Executor
    agora: list[float]

    @property
    def mem(self) -> bytearray:
        return self.sim.jogo.memoria

    def vida(self) -> int:
        return struct.unpack_from("<h", self.mem, VIDA)[0]

    def decisao(self, alavanca: str, parametros: dict[str, float]) -> int:
        return banco.gravar_decisao(
            self.con,
            {
                "ciclo_id": self.ciclo,
                "catalogo_versao": self.executor.catalogo.versao,
                "alavanca": alavanca,
                "parametros_json": json.dumps(parametros),
                "motivo": "O corpo pesa.",
                "motivo_origem": "servico",
                "origem": "servico",
                "pedido_bruto": "{}",
            },
        )

    def executar(self, alavanca: str, situacao: Situacao = COMBATE_3, **parametros: float):
        v = Veredito(alavanca, parametros, "O corpo pesa.", "servico", "servico")
        return self.executor.executar(v, self.decisao(alavanca, parametros), situacao, p.Status.RODANDO)

    def intervencao(self, id_: int) -> sqlite3.Row:
        linha = self.con.execute("select * from intervencoes where id = ?", (id_,)).fetchone()
        assert linha is not None
        return linha

    def encerramentos(self, alavanca: str) -> list[sqlite3.Row]:
        return self.con.execute(
            "select * from intervencoes where origem = 'encerramento' and alavanca = ? order by id",
            (alavanca,),
        ).fetchall()


@pytest.fixture
def bancada(tmp_path: Path) -> Iterator[Bancada]:
    agora = [1000.0]
    with Simulador(
        "proprio", pasta_estados=tmp_path / "sstates", atraso_salvamento_s=0.2, relogio=lambda: agora[0]
    ) as sim:
        mem = sim.jogo.memoria
        struct.pack_into("<hh", mem, VIDA, 1200, 1200)
        struct.pack_into("<III", mem, EM_MGR, VETOR, 60, PASSO)
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
        catalogo = cat.montar(COMPLETO, acoes_de_mundo=_acoes())
        executor = Executor(cliente, slots, con, sessao, contador, catalogo)
        yield Bancada(sim, cliente, con, sessao, ciclo, executor, agora)
        cliente.fechar()
        con.close()


# ---------- H05: o perfil declara, a plataforma confere ----------


def test_perfil_do_jogo_entra_no_catalogo_como_alavancas_com_faixa_por_intensidade() -> None:
    acoes = _acoes()
    assert {a.id for a in acoes} >= {"vida_do_jogador", "municao_do_pente", "vida_do_inimigo_mais_proximo"}
    leve = cat.montar(COMPLETO, intensidade=cat.Intensidade.LEVE, acoes_de_mundo=acoes)
    forte = cat.montar(COMPLETO, intensidade=cat.Intensidade.FORTE, acoes_de_mundo=acoes)
    a_leve, a_forte = leve.alavanca("vida_do_jogador"), forte.alavanca("vida_do_jogador")
    assert a_leve is not None and a_forte is not None and a_leve.mundo is not None
    assert a_leve.parametros["fracao"].minimo > a_forte.parametros["fracao"].minimo
    assert a_leve.parametros["duracao_s"].maximo < a_forte.parametros["duracao_s"].maximo
    assert leve.alavancas[-1].nome == cat.NADA and a_leve.executa_por == "H07"
    # vai no pedido de decisão como qualquer outra
    assert any(x["alavanca"] == "vida_do_jogador" for x in leve.para_o_pedido())
    # versão nova (emulador reiniciado) não perde as ações
    nova = cat.nova_versao(leve, COMPLETO, "emulador reiniciado")
    assert nova.alavanca("vida_do_jogador") is not None and nova.versao == 2
    # modo reduzido: as ações existem mas não estão disponíveis (escrevem pelo canal estendido)
    reduzido = cat.montar(SEM_EXTENSAO, acoes_de_mundo=acoes)
    assert reduzido.alavanca("vida_do_jogador") is not None and not reduzido.disponiveis().count(
        "vida_do_jogador"
    )


def test_perfil_de_outro_jogo_ou_ausente_nao_muda_o_catalogo(tmp_path: Path) -> None:
    assert mundo.carregar_perfil(PERFIL, "SLUS-21134", "deadbeef").acoes == ()
    assert mundo.carregar_perfil(PERFIL, "SLUS-99999", "013e349d").acoes == ()
    assert mundo.carregar_perfil(tmp_path / "nada.json", "SLUS-21134", "013e349d").acoes == ()
    sem = cat.montar(COMPLETO)
    com_nada = cat.montar(COMPLETO, acoes_de_mundo=())
    assert [a.nome for a in sem.alavancas] == [a.nome for a in com_nada.alavancas]


def test_acao_sem_capacidade_provada_ou_sem_piso_e_recusada(tmp_path: Path) -> None:
    perfil = json.loads(PERFIL.read_text(encoding="utf-8"))
    acao = next(a for a in perfil["acoes_de_mundo"] if a["id"] == "vida_do_jogador")
    candidata = dict(acao, capacidade="criar_area_de_roteiro")
    sem_piso = dict(acao, proibicoes=dict(acao["proibicoes"], piso=100))
    perfil["acoes_de_mundo"] = [candidata, sem_piso]
    arquivo = tmp_path / "SLUS-21134.json"
    arquivo.write_text(json.dumps(perfil), encoding="utf-8")
    carga = mundo.carregar_perfil(arquivo, "SLUS-21134", "013e349d")
    assert carga.acoes == () and len(carga.recusadas) == 2
    assert "não 'provada'" in carga.recusadas[0][1] and "RN-01" in carga.recusadas[1][1]


def test_validacao_1_descarta_fora_de_jogo_e_fora_da_faixa() -> None:
    catalogo = cat.montar(COMPLETO, acoes_de_mundo=_acoes())
    fora = conferir(
        Decisao(alavanca="vida_do_jogador", parametros={"fracao": 0.5, "duracao_s": 10}, motivo="x"),
        catalogo,
        MENU,
        {},
    )
    assert fora.origem == "descarte" and "RN-03" in (fora.descarte_motivo or "")
    baixo = conferir(
        Decisao(alavanca="vida_do_jogador", parametros={"fracao": 0.1, "duracao_s": 10}, motivo="x"),
        catalogo,
        COMBATE_3,
        {},
    )
    assert baixo.origem == "descarte" and "fora da faixa" in (baixo.descarte_motivo or "")
    ok = conferir(
        Decisao(
            alavanca="vida_do_jogador", parametros={"fracao": 0.35, "duracao_s": 20}, motivo="O corpo pesa."
        ),
        catalogo,
        COMBATE_3,
        {},
    )
    assert ok.executa and ok.alavanca == "vida_do_jogador"
    so_combate = conferir(
        Decisao(
            alavanca="vida_do_inimigo_mais_proximo", parametros={"fracao": 0.5, "duracao_s": 10}, motivo="x"
        ),
        catalogo,
        Situacao(descricao="calmo", fase=Fase.EXPLORACAO, aperto=1, confianca=0.9),
        {},
    )
    assert so_combate.origem == "descarte" and "só em combate" in (so_combate.descarte_motivo or "")


# ---------- H07: o critério de aceite ----------


def test_criterio_de_aceite_vida_cai_e_volta_no_prazo(bancada: Bancada) -> None:
    e = bancada.executar("vida_do_jogador", fracao=0.35, duracao_s=20)
    assert e.resultado == "confirmada" and bancada.vida() == 420  # 0,35 × 1200, relido igual
    linha = bancada.intervencao(e.intervencao_id)
    assert linha["resultado"] == "confirmada" and json.loads(linha["parametros_json"]) == {
        "fracao": 0.35,
        "duracao_s": 20,
    }
    volta = json.loads(linha["caminho_volta_json"])
    assert volta["valor_antes"] == 1200 and volta["valor_escrito"] == 420 and volta["tirado"] == 780
    assert volta["endereco"] == VIDA and volta["maxima"] == 1200
    decisao = bancada.con.execute(
        "select motivo from decisoes where id = ?", (linha["decisao_id"],)
    ).fetchone()
    assert decisao["motivo"] == "O corpo pesa."
    # no prazo volta sozinha
    bancada.agora[0] += 19
    assert bancada.executor.encerrar_vencidos() == [] and bancada.vida() == 420
    bancada.agora[0] += 1.5
    assert bancada.executor.encerrar_vencidos() == [e.intervencao_id]
    assert bancada.vida() == 1200
    assert bancada.intervencao(e.intervencao_id)["fim_ms"] is not None
    fim = bancada.encerramentos("vida_do_jogador")
    assert len(fim) == 1 and fim[0]["resultado"] == "confirmada"
    assert json.loads(fim[0]["parametros_json"])["devolvido"] == 780


def test_nunca_abaixo_do_piso_e_nunca_sobe(bancada: Bancada) -> None:
    struct.pack_into("<hh", bancada.mem, VIDA, 1000, 1000)
    e = bancada.executar("vida_do_jogador", fracao=0.25, duracao_s=10)  # 250 < piso 300
    assert e.resultado == "confirmada" and bancada.vida() == 300
    bancada.agora[0] += 11
    bancada.executor.encerrar_vencidos()
    assert bancada.vida() == 1000
    struct.pack_into("<h", bancada.mem, VIDA, 300)
    e2 = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=10)  # já no piso
    assert e2.resultado == "descartada" and "piso" in (e2.detalhe or "") and bancada.vida() == 300
    struct.pack_into("<h", bancada.mem, VIDA, 500)
    e3 = bancada.executar("vida_do_jogador", fracao=0.9, duracao_s=10)  # alvo 1080 acima do atual: não sobe
    assert e3.resultado == "descartada" and "abaixo do atual" in (e3.detalhe or "") and bancada.vida() == 500


def test_dano_no_meio_devolve_o_tirado_e_morte_nao_escreve(bancada: Bancada) -> None:
    e = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=20)
    assert e.resultado == "confirmada" and bancada.vida() == 600
    struct.pack_into("<h", bancada.mem, VIDA, 350)  # o jogo tirou 250 no meio do prazo
    bancada.agora[0] += 21
    bancada.executor.encerrar_vencidos()
    assert bancada.vida() == 950  # 350 + os 600 tirados, limitado à máxima
    e2 = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=20)
    assert e2.resultado == "confirmada" and bancada.vida() == 600
    struct.pack_into("<h", bancada.mem, VIDA, 0)  # morreu no meio
    bancada.agora[0] += 21
    bancada.executor.encerrar_vencidos()
    assert bancada.vida() == 0
    fim = bancada.encerramentos("vida_do_jogador")[-1]
    assert fim["resultado"] == "descartada" and "sem escrita" in json.loads(fim["parametros_json"])["motivo"]


def test_reversao_do_jogador_devolve_antes_do_prazo(bancada: Bancada) -> None:
    e = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=20)
    assert e.resultado == "confirmada" and bancada.vida() == 600
    r = bancada.executor.reverter(bancada.ciclo)
    assert r is not None and r.resultado == "confirmada" and bancada.vida() == 1200
    assert bancada.intervencao(e.intervencao_id)["revertida_por"] == r.intervencao_id
    assert bancada.executor.pendentes == []
    bancada.agora[0] += 21
    assert bancada.executor.encerrar_vencidos() == [] and bancada.vida() == 1200


def test_estado_nao_e_salvo_com_acao_em_vigor_e_recarga_descarta(bancada: Bancada) -> None:
    bancada.executor._salvar(COMBATE_3, "periodico", 93)
    e = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=20)
    assert e.resultado == "confirmada"
    assert bancada.executor.salvar_periodico(COMBATE_3) is None
    assert bancada.executor.aperto_dos_slots.keys() == {93}
    bancada.executor.aperto_dos_slots[93] = 1  # recarregar exige slot com aperto menor
    e2 = bancada.executar("recarregar", slot=93)
    assert e2.resultado == "confirmada" and bancada.executor.pendentes == []
    fim = bancada.encerramentos("vida_do_jogador")
    assert (
        len(fim) == 1
        and fim[0]["resultado"] == "descartada"
        and "recarga" in json.loads(fim[0]["parametros_json"])["motivo"]
    )


def test_releitura_diferente_do_escrito_e_falha_com_volta(
    bancada: Bancada, monkeypatch: pytest.MonkeyPatch
) -> None:
    from iaemps2.ponte import memoria

    monkeypatch.setattr(
        memoria, "escrever", lambda *a, **k: None
    )  # o jogo sobrescreve na hora: a releitura não bate
    e = bancada.executar("vida_do_jogador", fracao=0.5, duracao_s=20)
    assert e.resultado == "falhou" and "relido" in (e.detalhe or "") and bancada.executor.pendentes == []
    assert bancada.vida() == 1200


def test_fora_de_jogo_na_hora_descarta_sem_escrever(bancada: Bancada) -> None:
    e = bancada.executar("vida_do_jogador", MENU, fracao=0.5, duracao_s=20)
    assert e.resultado == "descartada" and bancada.vida() == 1200
    assert bancada.intervencao(e.intervencao_id)["resultado"] == "descartada"


def test_municao_por_ponteiro_e_inimigo_mais_proximo(bancada: Bancada) -> None:
    mem = bancada.mem
    item = 0x010F654E
    struct.pack_into("<I", mem, 0x003CE148 + 0xC, item)
    struct.pack_into("<H", mem, item + 8, 10 << 3)
    e = bancada.executar("municao_do_pente", fracao=0.3, duracao_s=10)
    assert e.resultado == "confirmada" and struct.unpack_from("<H", mem, item + 8)[0] == 3 << 3
    bancada.agora[0] += 11
    bancada.executor.encerrar_vencidos()
    assert struct.unpack_from("<H", mem, item + 8)[0] == 10 << 3
    # dois inimigos vivos: o mais próximo do jogador é o escolhido; um objeto (tipo 0x51) não conta
    struct.pack_into("<fff", mem, VETOR + 0xC0, 0.0, 0.0, 0.0)
    for vaga, tipo, pos, hp in ((3, 0x12, 5000.0, 500), (4, 0x15, 2000.0, 800), (5, 0x51, 100.0, 1000)):
        base = VETOR + vaga * PASSO
        struct.pack_into("<I", mem, base, 0x02002077)
        mem[base + 0x11C] = tipo
        struct.pack_into("<fff", mem, base + 0xC0, pos, 0.0, 0.0)
        struct.pack_into("<hh", mem, base + 0x4B0, hp, hp)
    e2 = bancada.executar("vida_do_inimigo_mais_proximo", fracao=0.5, duracao_s=10)
    assert e2.resultado == "confirmada"
    assert struct.unpack_from("<h", mem, VETOR + 4 * PASSO + 0x4B0)[0] == 400
    assert struct.unpack_from("<h", mem, VETOR + 3 * PASSO + 0x4B0)[0] == 500
    bancada.agora[0] += 11
    bancada.executor.encerrar_vencidos()
    assert struct.unpack_from("<h", mem, VETOR + 4 * PASSO + 0x4B0)[0] == 800
