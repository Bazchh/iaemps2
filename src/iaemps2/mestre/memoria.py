"""A memória curta do mestre (card S3-03; caso C05).

Derivada do registro, nunca guardada à parte: as últimas intervenções com motivo e resultado, os marcos,
quantos ciclos se passaram sem intervenção e o que o jogador desfez. Limitada, em formato fechado, pronta
para o pedido de decisão. Na retomada (E05) é reconstruída do mesmo jeito.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoriaCurta:
    ultimas_intervencoes: list[dict[str, Any]] = field(default_factory=list)
    marcos: list[dict[str, Any]] = field(default_factory=list)
    ciclos_sem_agir: int = 0
    revertidas_pelo_jogador: list[str] = field(default_factory=list)
    lacunas: int = 0

    def como_json(self) -> dict[str, Any]:
        return {
            "ultimas_intervencoes": self.ultimas_intervencoes,
            "marcos": self.marcos,
            "ciclos_sem_agir": self.ciclos_sem_agir,
            "revertidas_pelo_jogador": self.revertidas_pelo_jogador,
            "lacunas": self.lacunas,
        }


def reconstruir(con: sqlite3.Connection, sessao_id: str, agora_ms: int, janela: int = 5) -> MemoriaCurta:
    """Lê a sessão viva e monta a memória. `agora_ms` é o contador da sessão, para os 'há N ms'."""
    intervencoes = [
        {
            "alavanca": r["alavanca"],
            "motivo": r["motivo"],
            "resultado": r["resultado"],
            "ha_ms": max(0, agora_ms - int(r["comando_ms"])),
            "revertida": bool(r["revertida_por"]),
        }
        for r in con.execute(
            """
            select i.alavanca, d.motivo, i.resultado, i.comando_ms, i.revertida_por
            from intervencoes i join decisoes d on d.id = i.decisao_id join ciclos c on c.id = d.ciclo_id
            where c.sessao_id = ? and i.origem = 'mestre'
            order by i.id desc limit ?
            """,
            (sessao_id, janela),
        )
    ]
    marcos = [
        {"tipo": r["tipo"], "ha_ms": max(0, agora_ms - int(r["inicio_ms"]))}
        for r in con.execute(
            """
            select m.tipo, c.inicio_ms from marcos m join ciclos c on c.id = m.ciclo_id
            where c.sessao_id = ? order by m.id desc limit ?
            """,
            (sessao_id, janela),
        )
    ]
    revertidas = [
        str(r["alavanca"])
        for r in con.execute(
            """
            select i.alavanca from intervencoes i join decisoes d on d.id = i.decisao_id
            join ciclos c on c.id = d.ciclo_id
            where c.sessao_id = ? and i.origem = 'mestre' and i.revertida_por is not null
            order by i.id desc limit ?
            """,
            (sessao_id, janela),
        )
    ]
    ultimo_ciclo_com_acao = con.execute(
        """
        select max(c.numero) from intervencoes i join decisoes d on d.id = i.decisao_id
        join ciclos c on c.id = d.ciclo_id where c.sessao_id = ? and i.resultado = 'confirmada'
        """,
        (sessao_id,),
    ).fetchone()[0]
    ultimo_ciclo = con.execute("select max(numero) from ciclos where sessao_id = ?", (sessao_id,)).fetchone()[
        0
    ]
    sem_agir = 0 if ultimo_ciclo is None else int(ultimo_ciclo) - int(ultimo_ciclo_com_acao or 0)
    lacunas = int(
        con.execute(
            "select count(*) from ciclos where sessao_id = ? and lacuna is not null", (sessao_id,)
        ).fetchone()[0]
    )
    return MemoriaCurta(intervencoes, marcos, sem_agir, revertidas, lacunas)
