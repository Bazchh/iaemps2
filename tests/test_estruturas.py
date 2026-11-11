"""O documento de estruturas (S9-02) é gerado do perfil de memória: o perfil tem a forma esperada e o
documento no repositório é o que o gerador produz hoje."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PERFIL = RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
DOCUMENTO = RAIZ / "docs" / "Estruturas-SLUS-21134.md"
GERADOR = RAIZ / "docs" / "fonte" / "gerar_estruturas.py"
CHAVES_ESTRUTURA = {"id", "nome", "status", "raiz", "tamanho", "resumo", "campos", "funcoes", "pendencias"}
CHAVES_CAMPO = {"d", "t", "n", "s", "e", "l", "p"}
CHAVES_CONFERENCIA = {
    "data",
    "estados",
    "sala",
    "semente",
    "sorteados",
    "aceite_cliente",
    "campos",
    "observacoes",
}
RESULTADOS = {"bate", "lido", "diverge", "não conferível"}


def _perfil() -> dict:
    return json.loads(PERFIL.read_text(encoding="utf-8"))


def _gerador():
    spec = importlib.util.spec_from_file_location("gerar_estruturas", GERADOR)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_perfil_tem_a_forma_esperada() -> None:
    e = _perfil()["estruturas"]
    provas = set(e["provas"])
    ids = [s["id"] for s in e["lista"]]
    assert len(ids) == len(set(ids)), "id de estrutura repetido"
    for s in e["lista"]:
        assert set(s) - {"conferencia"} == CHAVES_ESTRUTURA, s["id"]
        assert s["status"] in {"lida", "parcial", "nao_lida"}, s["id"]
        deslocamentos = [c["d"] for c in s["campos"]]
        assert len(deslocamentos) == len(set(deslocamentos)), (s["id"], "deslocamento repetido")
        for c in s["campos"]:
            assert set(c) == CHAVES_CAMPO, (s["id"], c)
            assert c["d"] and c["n"], (s["id"], c)
            usadas = {p.strip() for p in c["p"].split(",") if p.strip()}
            assert usadas and usadas <= provas, (s["id"], c["d"], c["p"])
        for f in s["funcoes"]:
            assert set(f) == {"nome", "endereco", "papel"}, (s["id"], f)
        cf = s.get("conferencia")
        if cf:
            assert set(cf) == CHAVES_CONFERENCIA, s["id"]
            assert cf["aceite_cliente"] == "pendente" or cf["aceite_cliente"].startswith("aceito"), s["id"]
            assert set(cf["sorteados"]) <= set(deslocamentos) and len(cf["sorteados"]) == min(
                3, len(deslocamentos)
            ), s["id"]
            assert set(cf["campos"]) <= set(deslocamentos), (s["id"], "conferência de campo que não existe")
            for d, r in cf["campos"].items():
                assert set(r) == {"resultado", "estado", "lido", "relacao"}, (s["id"], d)
                assert r["resultado"] in RESULTADOS and r["estado"] in cf["estados"], (s["id"], d)


def test_documento_esta_atualizado() -> None:
    esperado = _gerador().gerar(_perfil())
    atual = DOCUMENTO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert atual == esperado, (
        "docs/Estruturas-SLUS-21134.md desatualizado: rode python docs/fonte/gerar_estruturas.py"
    )
