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
        assert set(s) == CHAVES_ESTRUTURA, s["id"]
        assert s["status"] in {"lida", "parcial", "nao_lida"}, s["id"]
        for c in s["campos"]:
            assert set(c) == CHAVES_CAMPO, (s["id"], c)
            assert c["d"] and c["n"], (s["id"], c)
            usadas = {p.strip() for p in c["p"].split(",") if p.strip()}
            assert usadas and usadas <= provas, (s["id"], c["d"], c["p"])
        for f in s["funcoes"]:
            assert set(f) == {"nome", "endereco", "papel"}, (s["id"], f)


def test_documento_esta_atualizado() -> None:
    esperado = _gerador().gerar(_perfil())
    atual = DOCUMENTO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert atual == esperado, (
        "docs/Estruturas-SLUS-21134.md desatualizado: rode python docs/fonte/gerar_estruturas.py"
    )
