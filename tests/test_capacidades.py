"""Card S9-03: o catálogo de capacidades é gerado do perfil; cada endereço existe no índice de funções do
executável; o número de argumentos pede trampolim quando passa de quatro; o que trava não tem ferramenta; as
constantes das ferramentas da bancada batem com o catálogo; contra o simulador, a ferramenta de criar personagem
chama o endereço do catálogo."""

from __future__ import annotations

import csv
import importlib.util
import json
import struct
from pathlib import Path

from iaemps2.bancada import modulos as md
from iaemps2.bancada import personagens as pz
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente
from iaemps2.simulador.servidor import Simulador

RAIZ = Path(__file__).resolve().parents[1]
PERFIL = RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
DOCUMENTO = RAIZ / "docs" / "Capacidades-SLUS-21134.md"
GERADOR = RAIZ / "docs" / "fonte" / "gerar_capacidades.py"
FUNCOES = RAIZ / "perfis" / "memoria" / "SLUS-21134.funcoes.csv"
CHAVES = {
    "id",
    "nome",
    "funcao",
    "endereco",
    "simbolo",
    "n_args",
    "argumentos",
    "via",
    "trampolim",
    "ferramenta",
    "pre_condicoes",
    "efeito",
    "desfazer",
    "risco",
    "estado",
    "prova",
}
ESTADOS = {"provada", "provada_sem_ferramenta", "provada_em_script", "candidata", "trava"}
EXECUTAVEL = (0x00100000, 0x00300000)


def _perfil() -> dict:
    return json.loads(PERFIL.read_text(encoding="utf-8"))


def _gerador():
    spec = importlib.util.spec_from_file_location("gerar_capacidades", GERADOR)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _indice() -> dict[int, str]:
    with FUNCOES.open(encoding="utf-8") as f:
        return {int(linha["endereco"], 16): linha["nome"] for linha in csv.DictReader(f)}


def test_catalogo_tem_a_forma_esperada() -> None:
    cp = _perfil()["capacidades"]
    ids = [c["id"] for c in cp["lista"]]
    assert len(ids) == len(set(ids)), "id repetido"
    for c in cp["lista"]:
        assert set(c) == CHAVES, c["id"]
        assert c["estado"] in ESTADOS and c["via"] in {"chamada", "escrita", "canal_cena"}, c["id"]
        assert set(c["prova"]) == {"data", "detalhe"}, c["id"]
        assert c["trampolim"] == (c["n_args"] > 4 or "float" in c["argumentos"]), (c["id"], "trampolim")
        if c["estado"] == "trava":
            assert c["ferramenta"] == "nenhuma", (c["id"], "trava não tem ferramenta")
        if c["estado"] == "provada":
            assert c["prova"]["data"], (c["id"], "provada sem data")
        if c["estado"] == "candidata":
            assert not c["prova"]["data"], (c["id"], "candidata com data de prova")


def test_enderecos_de_chamada_estao_no_indice_do_executavel() -> None:
    indice = _indice()
    for c in _perfil()["capacidades"]["lista"]:
        if c["via"] != "chamada":
            continue
        for e in c["endereco"]:
            a = int(e, 16)
            assert EXECUTAVEL[0] <= a < EXECUTAVEL[1], (c["id"], e, "fora do executável")
            assert a in indice, (c["id"], e, "não está no índice de funções")
            nome = indice[a]
            assert nome.startswith("FUN_") or nome.split("::")[-1] in c["simbolo"] or nome in c["funcao"], (
                c["id"],
                e,
                nome,
            )


def test_constantes_da_bancada_batem_com_o_catalogo() -> None:
    por_id = {c["id"]: c for c in _perfil()["capacidades"]["lista"]}
    assert por_id["criar_personagem"]["endereco"] == [f"0x{pz.EM_SET_EVENT:08X}"]
    assert por_id["destruir_tipo"]["endereco"] == [f"0x{md.SCE_DESTROY_EM:08X}"]
    assert por_id["liberar_modulo"]["endereco"] == [f"0x{md.INIT_MODULE:08X}"]
    assert por_id["carregar_modulo"]["endereco"] == [
        f"0x{md.MEM_ALLOC:08X}",
        f"0x{md.REGISTRAR_MODULO:08X}",
        f"0x{md.SEARCH_EM_MODULE:08X}",
    ]
    assert por_id["consultar_modulo"]["endereco"] == [f"0x{md.SEARCH_EM_MODULE:08X}"]
    assert por_id["vida"]["endereco"] == [f"0x{pz.BLOCO_G + 0x7ED6:08X}"]


def test_criar_personagem_chama_o_endereco_do_catalogo(tmp_path: Path) -> None:
    endereco = int(
        next(c for c in _perfil()["capacidades"]["lista"] if c["id"] == "criar_personagem")["endereco"][0], 16
    )
    with Simulador("proprio", pasta_estados=tmp_path) as sim:
        mem = sim.jogo.memoria
        struct.pack_into("<III", mem, pz.EM_MGR, pz.VETOR, 60, pz.PASSO)
        sim.resposta_chamada = (0, 0, 0)
        c = Cliente(porta=sim.porta or 0)
        c.conectar()
        pz.criar_personagem(c, 0x12)
        c.fechar()
        assert sim.chamadas == [(endereco, (AREA_DO_MESTRE,), 5000, 0)]


def test_documento_esta_atualizado() -> None:
    esperado = _gerador().gerar(_perfil())
    atual = DOCUMENTO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert atual == esperado, (
        "docs/Capacidades-SLUS-21134.md desatualizado: rode python docs/fonte/gerar_capacidades.py"
    )
