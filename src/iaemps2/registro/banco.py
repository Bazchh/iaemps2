"""A sessão viva: um arquivo SQLite por sessão, só de acréscimo (Blueprint, capítulo 3; card S0-02).

Nenhuma função de alterar ou apagar existe aqui. O que pode mudar depois de gravado são as colunas
"uma única vez" listadas em PREENCHE_UMA_VEZ, de nulo (ou de 'pendente', no resultado da intervenção)
para um valor; o gatilho recusa qualquer outra alteração e qualquer exclusão.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

MIGRACAO = "0001"

# tabela -> colunas que podem ser preenchidas uma única vez depois do insert
PREENCHE_UMA_VEZ: dict[str, tuple[str, ...]] = {
    "sessoes": ("fechada_em_utc",),
    "catalogo_versoes": (),
    "ciclos": ("fim_ms",),
    "capturas": (),
    "situacoes": (),
    "decisoes": (),
    "intervencoes": ("confirmado_ms", "estado_depois_json", "resultado", "fim_ms", "revertida_por"),
    "estados_reservados": ("confirmado_ms", "bytes", "sobrescrito_ms", "suspeito"),
    "falhas": ("resolvida_ms",),
    "metricas": (),
    "marcos": (),
    "aceites": (),
}
# o valor "vazio" de cada coluna que pode ser preenchida: nulo, ou o marcador inicial
VAZIO: dict[tuple[str, str], str] = {
    ("intervencoes", "resultado"): "'pendente'",
    ("estados_reservados", "suspeito"): "0",
}
MENSAGEM = "registro só de acréscimo"


class RegistroError(RuntimeError):
    """Tentativa de alterar ou apagar o que já foi gravado."""


def _colunas(con: sqlite3.Connection, tabela: str) -> list[str]:
    return [str(linha[1]) for linha in con.execute(f"pragma table_info({tabela})")]


def _sql_gatilhos(con: sqlite3.Connection) -> str:
    partes: list[str] = []
    for tabela, uma_vez in PREENCHE_UMA_VEZ.items():
        partes.append(
            f"create trigger {tabela}_sem_delete before delete on {tabela} "
            f"begin select raise(ABORT, '{MENSAGEM}'); end;"
        )
        fixas = [c for c in _colunas(con, tabela) if c not in uma_vez]
        # qualquer coluna fixa alterada = recusa
        mudou_fixa = " or ".join(f"new.{c} is not old.{c}" for c in fixas)
        partes.append(
            f"create trigger {tabela}_sem_update before update on {tabela} "
            f"when {mudou_fixa} begin select raise(ABORT, '{MENSAGEM}'); end;"
        )
        # coluna "uma vez": só de vazio para valor, nunca de valor para outro
        for c in uma_vez:
            vazio = VAZIO.get((tabela, c), "null")
            condicao = f"old.{c} is not {vazio}"
            partes.append(
                f"create trigger {tabela}_{c}_uma_vez before update of {c} on {tabela} "
                f"when new.{c} is not old.{c} and ({condicao}) "
                f"begin select raise(ABORT, '{MENSAGEM}: {tabela}.{c} já preenchida'); end;"
            )
    return "\n".join(partes)


def novo_id_sessao(agora_ms: int | None = None) -> str:
    """Ordenável pelo tempo: milissegundos desde a época, mais um sufixo aleatório."""
    ms = int(time.time() * 1000) if agora_ms is None else agora_ms
    return f"{ms:013d}-{secrets.token_hex(3)}"


def agora_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def criar(caminho: Path) -> sqlite3.Connection:
    """Cria o arquivo da sessão com o esquema e os gatilhos. Recusa arquivo que já existe."""
    if caminho.exists():
        raise FileExistsError(f"sessão já existe: {caminho}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = _conectar(caminho)
    esquema = resources.files("iaemps2.registro").joinpath("esquema.sql").read_text(encoding="utf-8")
    with con:
        con.executescript(esquema)
        con.executescript(_sql_gatilhos(con))
        con.execute(f"pragma user_version = {int(MIGRACAO)}")
    return con


def abrir(caminho: Path) -> sqlite3.Connection:
    """Abre uma sessão existente. Recusa arquivo de outra migração."""
    if not caminho.is_file():
        raise FileNotFoundError(f"sessão não encontrada: {caminho}")
    con = _conectar(caminho)
    versao = int(con.execute("pragma user_version").fetchone()[0])
    if versao != int(MIGRACAO):
        con.close()
        raise RegistroError(f"{caminho}: migração {versao:04d}, esperada {MIGRACAO}")
    return con


def _conectar(caminho: Path) -> sqlite3.Connection:
    con = sqlite3.connect(caminho, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode = wal")
    con.execute("pragma foreign_keys = on")
    return con


def inserir(con: sqlite3.Connection, tabela: str, campos: Mapping[str, Any]) -> int:
    """Grava uma linha e devolve o id. É a única forma de escrever, além de preencher_uma_vez."""
    if tabela not in PREENCHE_UMA_VEZ:
        raise RegistroError(f"tabela desconhecida: {tabela}")
    nomes = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    try:
        cursor = con.execute(f"insert into {tabela} ({nomes}) values ({marcas})", tuple(campos.values()))
    except sqlite3.IntegrityError as erro:
        raise RegistroError(f"{tabela}: {erro}") from erro
    if tabela == "sessoes":
        return 0
    return int(cursor.lastrowid or 0)


def preencher_uma_vez(
    con: sqlite3.Connection, tabela: str, id_: int | str, campos: Mapping[str, Any]
) -> None:
    """Preenche colunas 'uma vez' de uma linha. O gatilho recusa qualquer coisa fora disso."""
    permitidas = PREENCHE_UMA_VEZ.get(tabela)
    if permitidas is None:
        raise RegistroError(f"tabela desconhecida: {tabela}")
    fora = [c for c in campos if c not in permitidas]
    if fora:
        raise RegistroError(f"{tabela}: colunas que não se preenchem depois: {', '.join(fora)}")
    atribuicoes = ", ".join(f"{c} = ?" for c in campos)
    try:
        con.execute(f"update {tabela} set {atribuicoes} where id = ?", (*campos.values(), id_))
    except sqlite3.IntegrityError as erro:
        raise RegistroError(f"{tabela}: {erro}") from erro


def abrir_sessao(
    con: sqlite3.Connection,
    *,
    jogo_titulo: str,
    jogo_serial: str,
    jogo_crc: str,
    jogo_versao: str | None,
    emulador_versao: str,
    modo: str,
    tom: str,
    intensidade: str,
    servico: str,
    aceite_versao: str,
    config_json: str,
    id_: str | None = None,
) -> str:
    sessao_id = id_ or novo_id_sessao()
    inserir(
        con,
        "sessoes",
        {
            "id": sessao_id,
            "aberta_em_utc": agora_utc(),
            "jogo_titulo": jogo_titulo,
            "jogo_serial": jogo_serial,
            "jogo_crc": jogo_crc,
            "jogo_versao": jogo_versao,
            "emulador_versao": emulador_versao,
            "modo": modo,
            "tom": tom,
            "intensidade": intensidade,
            "servico": servico,
            "aceite_versao": aceite_versao,
            "config_json": config_json,
        },
    )
    return sessao_id


def fechar_sessao(con: sqlite3.Connection, sessao_id: str) -> None:
    preencher_uma_vez(con, "sessoes", sessao_id, {"fechada_em_utc": agora_utc()})


def gravar_ciclo(
    con: sqlite3.Connection,
    sessao_id: str,
    numero: int,
    inicio_ms: int,
    status_emu: str,
    estado_mestre: str,
    lacuna: str | None = None,
) -> int:
    return inserir(
        con,
        "ciclos",
        {
            "sessao_id": sessao_id,
            "numero": numero,
            "inicio_ms": inicio_ms,
            "status_emu": status_emu,
            "estado_mestre": estado_mestre,
            "lacuna": lacuna,
        },
    )


def fechar_ciclo(con: sqlite3.Connection, ciclo_id: int, fim_ms: int) -> None:
    preencher_uma_vez(con, "ciclos", ciclo_id, {"fim_ms": fim_ms})


def gravar_captura(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "capturas", campos)


def gravar_situacao(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "situacoes", campos)


def gravar_decisao(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "decisoes", campos)


def gravar_intervencao(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "intervencoes", {"resultado": "pendente", **campos})


def gravar_falha(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "falhas", campos)


def gravar_metrica(con: sqlite3.Connection, campos: Mapping[str, Any]) -> int:
    return inserir(con, "metricas", campos)


def gravar_marco(con: sqlite3.Connection, ciclo_id: int, tipo: str, detalhe: str | None = None) -> int:
    return inserir(con, "marcos", {"ciclo_id": ciclo_id, "tipo": tipo, "detalhe": detalhe})


def cadeia(con: sqlite3.Connection, intervencao_id: int) -> sqlite3.Row | None:
    """A cadeia ciclo, captura, situação, decisão, intervenção de uma intervenção, numa linha só (F03)."""
    linha: sqlite3.Row | None = con.execute(
        """
        select c.numero as ciclo, cap.arquivo as captura, s.descricao as situacao, s.fase, s.aperto,
               d.alavanca as alavanca_decidida, d.motivo, d.origem as decisao_origem,
               i.alavanca, i.resultado, i.estado_antes_json, i.estado_depois_json
        from intervencoes i
        join decisoes d on d.id = i.decisao_id
        join ciclos c on c.id = d.ciclo_id
        left join situacoes s on s.id = d.situacao_id
        left join capturas cap on cap.id = s.captura_id
        where i.id = ?
        """,
        (intervencao_id,),
    ).fetchone()
    return linha
