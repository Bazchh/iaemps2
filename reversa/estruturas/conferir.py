"""Conferência ao vivo das estruturas do perfil (S9-02): lê cada campo pelo canal do emulador e confere por uma
relação INDEPENDENTE do próprio perfil sempre que existe uma (EM_LIST × cEm, soma das classes de polígonos,
matriz × inversa, projeção do alvo da câmera, cabeçalho do AFS lido na ISO, lista de áreas pela raiz do código).

Só leitura: não escreve na memória, não chama função, não salva estado. Vale para UMA execução, um estado e uma
sala. Depois de ler tudo, sorteia três campos por estrutura com semente registrada: o aceite do card é do cliente,
a conferência automática só prepara a lista do que ele olha.

Uso: conferir.py [semente=2026] [perfil] [saida.json]
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import struct
import sys
import time
from pathlib import Path

from iaemps2.bancada import modulos as md
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SEMENTE = int(ARGS[0]) if ARGS else 2026
RAIZ = Path(__file__).resolve().parents[2]
PERFIL = Path(ARGS[1]) if len(ARGS) > 1 else RAIZ / "perfis" / "memoria" / "SLUS-21134.json"
SAIDA = Path(ARGS[2]) if len(ARGS) > 2 else Path(__file__).with_name("conferencia.json")
# --estado=N: recarrega o slot N antes de ler (o estado em que a conferência vale); sem a opção, lê o que está
# rodando e registra 96 (o estado limpo do jogador, carregado ao lançar)
ESTADO = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--estado=")), 96)
CARREGAR = any(a.startswith("--estado=") for a in sys.argv[1:])

PG = 0x00425BA0
EM_MGR = 0x004203B0
PPL = 0x004203D0
EM_LIST = 0x0042DEE4
ITEM_MGR = 0x003CE148
TABELA_PECAS = 0x00326DE8
TABELA_ARMAS = 0x003A99C0
TABELA_MODULOS = 0x00455E50
TAREFAS = 0x00451688
TAREFA_CORRENTE = 0x00451680
RAIZ_CENAS = 0x004563F0
SAT_MGR = 0x0041AF10
EAT_MGR = 0x0041AF30
CAM_OLHO = 0x003CA220
CAM_ALVO = 0x003CA230
CAM_VP = 0x004327C0
CAM_TELA = 0x00432840
OBJETOS = 0x004568AC
SMD = 0x004568A0
EFEITOS = 0x004203A4
CONTROLE = 0x00431948
ANEXOS = 0x017BCDF0
HEAP = (0x00100000, 0x02000000)
CODIGO = (0x00100000, 0x00400000)

BATE, DIVERGE, LIDO, NAO = "bate", "diverge", "lido", "não conferível"


class Leitor:
    def __init__(self, c: Cliente) -> None:
        self.c = c
        self.cache: dict[tuple[int, int], bytes] = {}

    def bloco(self, inicio: int, tamanho: int) -> bytes:
        chave = (inicio, tamanho)
        if chave not in self.cache:
            self.cache[chave] = md.ler_bloco(self.c, inicio, tamanho)
        return self.cache[chave]

    def u8(self, a: int) -> int:
        return self.bloco(a, 1)[0]

    def s8(self, a: int) -> int:
        return struct.unpack("<b", self.bloco(a, 1))[0]

    def u16(self, a: int) -> int:
        return struct.unpack("<H", self.bloco(a, 2))[0]

    def s16(self, a: int) -> int:
        return struct.unpack("<h", self.bloco(a, 2))[0]

    def u32(self, a: int) -> int:
        return struct.unpack("<I", self.bloco(a, 4))[0]

    def s32(self, a: int) -> int:
        return struct.unpack("<i", self.bloco(a, 4))[0]

    def f32(self, a: int) -> float:
        return struct.unpack("<f", self.bloco(a, 4))[0]

    def vec3(self, a: int) -> tuple[float, float, float]:
        return struct.unpack("<fff", self.bloco(a, 12))

    def mat4(self, a: int) -> list[list[float]]:
        v = struct.unpack("<16f", self.bloco(a, 64))
        return [list(v[i : i + 4]) for i in range(0, 16, 4)]


def heap(a: int) -> bool:
    return HEAP[0] <= a < HEAP[1]


def codigo(a: int) -> bool:
    return CODIGO[0] <= a < CODIGO[1]


def h(a: int) -> str:
    return f"0x{a:08X}"


def mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def identidade(m: list[list[float]], tol: float = 1e-3) -> bool:
    return all(abs(m[i][j] - (1.0 if i == j else 0.0)) < tol for i in range(4) for j in range(4))


class Conferencia:
    """Acumula um resultado por campo de cada estrutura; só os campos listados no perfil entram."""

    def __init__(self, perfil: dict) -> None:
        self.perfil = perfil
        self.campos = {s["id"]: [c["d"] for c in s["campos"]] for s in perfil["estruturas"]["lista"]}
        self.resultados: dict[str, dict[str, dict]] = {k: {} for k in self.campos}
        self.observacoes: dict[str, list[str]] = {k: [] for k in self.campos}

    def anota(self, est: str, d: str, lido: str, resultado: str, relacao: str = "") -> None:
        if d not in self.campos[est]:
            raise KeyError(f"{est} {d} não está no perfil")
        self.resultados[est][d] = {"lido": lido, "resultado": resultado, "relacao": relacao}

    def obs(self, est: str, texto: str) -> None:
        self.observacoes[est].append(texto)


def conferir(m_: Leitor, cf: Conferencia, iso: Path) -> dict:
    ctx: dict = {}
    # ---- pG -------------------------------------------------------------------------------------------
    sala = m_.u16(PG + 0x7EB8)
    ctx["sala"] = sala
    vida, vida_max = m_.s16(PG + 0x7ED6), m_.s16(PG + 0x7ED8)
    sub, sub_max = m_.s16(PG + 0x7EDA), m_.s16(PG + 0x7EDC)
    dif, traje, pers = m_.u8(PG + 0x7EC4), m_.u8(PG + 0x7EE8), m_.u8(PG + 0x7EEA)
    lista_no = m_.s8(PG + 0x7ED5)
    # EM_LIST e vetor de personagens (usados nas relações cruzadas)
    p_array, n_array, tam = m_.u32(EM_MGR), m_.u32(EM_MGR + 4), m_.u32(EM_MGR + 8)
    ctx.update(p_array=p_array, n_array=n_array, tam=tam)
    lista = [m_.bloco(EM_LIST + 0x20 * i, 0x20) for i in range(256)]
    entradas = [i for i, e in enumerate(lista) if e[1] != 0]
    vagas = []
    for v in range(n_array):
        b = p_array + v * tam
        if m_.u32(b) & 0x201 == 1:
            vagas.append(b)
    ctx["vagas"] = vagas
    # cEm com origem na lista (emset_no != 0xFF) e a entrada correspondente
    pares = []
    for b in vagas:
        no = m_.u8(b + 0x4C0)
        if no != 0xFF and no < 256 and lista[no][1] != 0:
            pares.append((b, no, lista[no]))
    ctx["pares"] = pares
    salas_lista = {struct.unpack_from("<H", lista[i], 0x18)[0] for i in entradas}
    estagios = {s >> 8 for s in salas_lista}
    cf.anota(
        "pG",
        "0x7EB8",
        h(sala),
        BATE if estagios == {sala >> 8} and sala in salas_lista else DIVERGE,
        f"EM_LIST+0x18 das {len(entradas)} entradas da lista: estágios {sorted(estagios)}, "
        f"{len(salas_lista)} salas, a atual entre elas = {sala in salas_lista}",
    )
    cf.anota("pG", "0x7EC4", str(dif), BATE if 0 <= dif <= 10 else DIVERGE, "faixa 0..10")
    cf.anota(
        "pG",
        "0x7ED5",
        str(lista_no),
        BATE if (lista_no >= 0) == (len(entradas) > 0) else DIVERGE,
        f"lista com {len(entradas)} entradas ocupadas",
    )
    hp_pl = m_.s16(p_array + 0x4B0)
    cf.anota(
        "pG",
        "0x7ED6",
        str(vida),
        BATE if vida == hp_pl and 0 <= vida <= 2400 else DIVERGE,
        f"cEm do jogador +0x4B0 = {hp_pl}; faixa 0..2400",
    )
    cf.anota(
        "pG",
        "0x7ED8",
        str(vida_max),
        BATE if vida_max >= vida and vida_max <= 2400 else DIVERGE,
        f"≥ vida {vida}, ≤ 2400",
    )
    cf.anota("pG", "0x7EDA", str(sub), BATE if 0 <= sub <= sub_max else DIVERGE, f"0..máximo {sub_max}")
    cf.anota("pG", "0x7EDC", str(sub_max), BATE if sub_max >= sub else DIVERGE, f"≥ vida da parceira {sub}")
    cf.anota("pG", "0x7EE8", str(traje), BATE if traje <= 5 else DIVERGE, "faixa 0..5")
    id_pl = m_.u8(p_array + 0x11C)
    cf.anota(
        "pG",
        "0x7EEA",
        str(pers),
        BATE if pers <= 5 and id_pl == 0 else DIVERGE,
        f"faixa 0..5; cEm do jogador +0x11C = {id_pl} (0 = jogador)",
    )
    cf.anota(
        "pG", "0x5C", h(m_.u32(PG + 0x5C)), LIDO, "sem relação independente (só o bit 0x40000000 é lido no C)"
    )
    v70 = m_.s32(PG + 0x70)
    cf.anota(
        "pG",
        "0x70",
        str(v70),
        BATE if (v70 >= 0) == (len(entradas) > 0) else DIVERGE,
        "negativo só quando a lista precisa ser recarregada",
    )
    cf.anota("pG", "0x7EED", str(m_.u8(PG + 0x7EED)), LIDO, "sem relação independente")
    cf.anota("pG", "0xB3B0", str(m_.s32(PG + 0xB3B0)), LIDO, "sem relação independente")
    # Em_flg: bit (31 − índice) na lista de 32 bytes do em_list_no
    if 0 <= lista_no < 12 and pares:
        flg = struct.unpack("<8I", m_.bloco(PG + 0x7F60 + 0x20 * lista_no, 0x20))
        marcados = {i for i in range(256) if flg[i // 32] >> (31 - i % 32) & 1}
        criados = {no for _, no, _ in pares}
        cf.anota(
            "pG",
            "0x7F60",
            f"lista {lista_no}: {len(marcados)} bits",
            BATE if criados <= marcados else DIVERGE,
            f"entradas criadas {sorted(criados)} ⊆ bits ligados {sorted(marcados)[:16]}",
        )
    else:
        cf.anota("pG", "0x7F60", "—", NAO, "sem lista carregada neste estado")
    cf.anota(
        "pG",
        "0x8344",
        h(PG + 0x8344),
        BATE if PG + 0x8344 == EM_LIST else DIVERGE,
        f"aritmética = {h(EM_LIST)}; {len(entradas)} entradas ocupadas",
    )
    # ---- EmMgr ----------------------------------------------------------------------------------------
    cf.anota(
        "EmMgr",
        "0x00",
        h(p_array),
        BATE if heap(p_array) and m_.u32(PPL) == p_array else DIVERGE,
        f"no heap; pPL {h(m_.u32(PPL))} = pArray (vaga 0 = jogador)",
    )
    cf.anota("EmMgr", "0x04", str(n_array), BATE if n_array == 60 else DIVERGE, "60 vagas")
    cf.anota("EmMgr", "0x08", h(tam), BATE if tam == 0xED0 else DIVERGE, "passo 0xED0")
    cf.anota("EmMgr", "0x0C", str(m_.u8(EM_MGR + 0xC)), LIDO, "sem relação independente")
    alive = m_.u32(EM_MGR + 0x10)
    cadeia, q, guarda = [], alive, 0
    while heap(q) and guarda < 64:
        cadeia.append(q)
        q = m_.u32(q + 4)
        guarda += 1
    cf.anota(
        "EmMgr",
        "0x10",
        h(alive),
        BATE if set(cadeia) == set(vagas) else DIVERGE,
        f"cadeia por +0x4 tem {len(cadeia)} nós; vagas com be_flag vivo = {len(vagas)}",
    )
    guid = m_.u32(EM_MGR + 0x34)
    cf.anota("EmMgr", "0x34", str(guid), LIDO, "papel só pelo nome do GameCube; sem relação independente")
    # ---- cEm (jogador = vaga 0; inimigo = primeiro par da lista) ----------------------------------------
    pl = p_array

    # inimigo de referência: vivo (hp > 0) e o que menos se afastou do ponto da lista (inimigos andam e morrem)
    def _afast(par: tuple) -> float:
        b_, _, e_ = par
        return math.dist([v * 10 for v in struct.unpack_from("<hhh", e_, 0xC)], m_.vec3(b_ + 0xC0))

    vivos_lista = [q for q in pares if m_.s16(q[0] + 0x4B0) > 0]
    inim = min(vivos_lista, key=_afast) if vivos_lista else (pares[0] if pares else None)
    if pares:
        cf.obs(
            "cEm",
            f"{len(pares)} cEm vindos da lista, {len(vivos_lista)} com vida > 0; afastamentos do ponto da lista (mm): "
            f"{sorted(round(_afast(q)) for q in pares)}",
        )
    cf.anota("cEm", "0x000", h(m_.u32(pl)), BATE if m_.u32(pl) & 0x201 == 1 else DIVERGE, "jogador vivo")
    cf.anota(
        "cEm",
        "0x004",
        h(m_.u32(pl + 4)),
        BATE if m_.u32(pl + 4) in cadeia or m_.u32(pl + 4) == 0 else DIVERGE,
        "próximo da cadeia de vivos",
    )
    vt = m_.u32(pl + 8)
    cf.anota(
        "cEm",
        "0x008",
        h(vt),
        BATE if codigo(vt) and codigo(m_.u32(vt + 0x2C)) else DIVERGE,
        f"tabela no executável; *(vt+0x2C) = {h(m_.u32(vt + 0x2C))} é código",
    )
    m = m_.mat4(pl + 0x10)
    pos = m_.vec3(pl + 0xC0)
    normas = [math.sqrt(sum(x * x for x in m[i][:3])) for i in range(3)]
    cf.anota(
        "cEm",
        "0x010",
        f"linhas {[round(n, 3) for n in normas]}, translação {[round(x) for x in m[3][:3]]}",
        BATE if all(abs(n - 1) < 1e-2 for n in normas) and math.dist(m[3][:3], pos) < 1 else DIVERGE,
        "três linhas unitárias; quarta = pos (+0xC0)",
    )
    if inim:
        b, no, e = inim
        ecm = struct.unpack_from("<hhh", e, 0xC)
        epos = m_.vec3(b + 0xC0)
        d = math.dist([v * 10 for v in ecm], epos)
        cf.anota(
            "cEm",
            "0x0C0",
            f"inimigo vaga {(b - p_array) // tam}: {[round(v) for v in epos]}",
            BATE if d < 2000 else DIVERGE,
            f"EM_LIST[{no}] pos×10 = {[v * 10 for v in ecm]}; distância {d:.0f} mm",
        )
        erot = struct.unpack_from("<hhh", e, 0x12)
        eang = m_.vec3(b + 0xD0)
        esp = [r * math.pi / 16384 for r in erot]
        dy = abs((eang[1] - esp[1] + math.pi) % (2 * math.pi) - math.pi)
        cf.anota(
            "cEm",
            "0x0D0",
            f"{[round(a, 3) for a in eang]}",
            BATE if dy < 0.5 else DIVERGE,
            f"EM_LIST[{no}] rot×π/16384 = {[round(a, 3) for a in esp]}; diferença em y {dy:.3f} rad",
        )
        cf.anota(
            "cEm",
            "0x11C",
            str(m_.u8(b + 0x11C)),
            BATE if m_.u8(b + 0x11C) == e[1] else DIVERGE,
            f"EM_LIST[{no}]+1 = {e[1]}",
        )
        cf.anota(
            "cEm",
            "0x11D",
            str(m_.u8(b + 0x11D)),
            BATE if m_.u8(b + 0x11D) == e[2] else DIVERGE,
            f"EM_LIST[{no}]+2 = {e[2]}",
        )
        hp = struct.unpack_from("<H", e, 8)[0]
        cf.anota(
            "cEm",
            "0x4B2",
            str(m_.s16(b + 0x4B2)),
            BATE if m_.s16(b + 0x4B2) == hp else DIVERGE,
            f"EM_LIST[{no}]+8 = {hp}",
        )
        cf.anota(
            "cEm",
            "0x4B0",
            f"inimigo {m_.s16(b + 0x4B0)}; jogador {hp_pl}",
            BATE if 0 < m_.s16(b + 0x4B0) <= hp and hp_pl == vida else DIVERGE,
            f"0 < vida ≤ EM_LIST[{no}]+8 = {hp}; jogador = pG vida = {vida}",
        )
        cf.anota(
            "cEm",
            "0x4BD",
            str(m_.u8(b + 0x4BD)),
            BATE if m_.u8(b + 0x4BD) == e[3] else DIVERGE,
            f"EM_LIST[{no}]+3 = {e[3]}",
        )
        fl = struct.unpack_from("<I", e, 4)[0]
        cf.anota(
            "cEm",
            "0x4AC",
            h(m_.u32(b + 0x4AC)),
            BATE if m_.u32(b + 0x4AC) == fl else DIVERGE,
            f"EM_LIST[{no}]+4 = {h(fl)}",
        )
        cf.anota(
            "cEm",
            "0x4CA",
            str(m_.u8(b + 0x4CA)),
            BATE if m_.u8(b + 0x4CA) == e[0xB] else DIVERGE,
            f"EM_LIST[{no}]+0xB = {e[0xB]}",
        )
        gr = struct.unpack_from("<h", e, 0x1A)[0] * 1000.0
        cf.anota(
            "cEm",
            "0x4A4",
            f"{m_.f32(b + 0x4A4):.0f}",
            BATE if abs(m_.f32(b + 0x4A4) - gr) < 1 else DIVERGE,
            f"EM_LIST[{no}]+0x1A × 1000 = {gr:.0f}",
        )
        cf.anota(
            "cEm",
            "0x4C0",
            str(no),
            BATE if e[1] == m_.u8(b + 0x11C) else DIVERGE,
            f"EM_LIST[{no}] tem id {e[1]} = cEm+0x11C {m_.u8(b + 0x11C)}",
        )
        lpl = m_.f32(b + 0x498)
        d2 = (epos[0] - pos[0]) ** 2 + (epos[2] - pos[2]) ** 2
        cf.anota(
            "cEm",
            "0x498",
            f"{lpl:.4g}",
            BATE if abs(lpl - d2) <= 0.05 * d2 + 1e4 else DIVERGE,
            f"distância² xz ao jogador calculada {d2:.4g} (5 %; o jogo atualiza por quadro)",
        )
        lsub = m_.f32(b + 0x49C)
        cf.anota(
            "cEm",
            "0x49C",
            f"{lsub:.4g}",
            BATE if abs(lsub - 1e16) < 1e9 or lsub < 1e13 else DIVERGE,
            "1e16 sem parceira, senão distância²",
        )
        mod = m_.u32(b + 0x480)
        mods = [
            (
                m_.u16(TABELA_MODULOS + i * 0x98 + 0x80),
                m_.u32(TABELA_MODULOS + i * 0x98 + 0x84),
                m_.u32(TABELA_MODULOS + i * 0x98 + 0x88),
                m_.u32(TABELA_MODULOS + i * 0x98 + 0x8C),
                m_.u32(TABELA_MODULOS + i * 0x98 + 0x90),
            )
            for i in range(4)
        ]
        ctx["mods"] = mods
        dentro = [
            t for t, dat, rel, tdat, trel in mods if (dat <= mod < dat + tdat) or (rel <= mod < rel + trel)
        ]
        cf.anota(
            "cEm",
            "0x480",
            h(mod),
            BATE if dentro else DIVERGE,
            f"cai no .dat/.rel do módulo de tipo {[h(t) for t in dentro]} (tipo do inimigo {h(e[1])})",
        )
    else:
        for d in (
            "0x0C0",
            "0x0D0",
            "0x11C",
            "0x11D",
            "0x4B2",
            "0x4B0",
            "0x4BD",
            "0x4AC",
            "0x4CA",
            "0x4A4",
            "0x4C0",
            "0x498",
            "0x49C",
            "0x480",
        ):
            cf.anota("cEm", d, "—", NAO, "nenhum inimigo criado da lista neste estado")
    pold = m_.vec3(pl + 0x130)
    cf.anota(
        "cEm",
        "0x130",
        f"{[round(v) for v in pold]}",
        BATE if math.dist(pold, pos) < 500 else DIVERGE,
        f"jogador parado: pos {[round(v) for v in pos]}",
    )
    partes = m_.u32(pl + 0x110)
    ploc = m_.vec3(partes + 0x80) if heap(partes) else (0, 0, 0)
    pmun = m_.vec3(partes + 0x40) if heap(partes) else (0, 0, 0)
    pold_ = m_.vec3(partes + 0x90) if heap(partes) else (0, 0, 0)
    cf.anota(
        "cEm",
        "0x110",
        h(partes),
        BATE if heap(partes) and math.dist(pmun, pos) < 2000 and math.dist(pold_, pmun) < 500 else DIVERGE,
        f"1ª parte: matriz +0x40 = {[round(v) for v in pmun]} (mundo, perto de pos); +0x90 = {[round(v) for v in pold_]}; "
        f"+0x80 = {[round(v) for v in ploc]} (local, não mundo)",
    )
    wn = m_.vec3(pl + 0x140)
    nw = math.sqrt(sum(v * v for v in wn))
    cf.anota(
        "cEm",
        "0x140",
        f"{[round(v, 3) for v in wn]}",
        BATE if nw < 1e-3 or abs(nw - 1) < 1e-2 else DIVERGE,
        "zero ou unitária",
    )
    pf = m_.u32(pl + 0x150)
    fn = m_.vec3(pf) if heap(pf) else (0, 0, 0)
    nf = math.sqrt(sum(v * v for v in fn))
    cf.anota(
        "cEm",
        "0x150",
        f"{h(pf)} → {[round(v, 3) for v in fn]}",
        BATE if heap(pf) and abs(nf - 1) < 1e-2 and fn[1] > 0 else DIVERGE,
        "ponteiro para normal unitária com y > 0",
    )
    pmi = m_.u32(pl + 0x190)
    maddr = m_.u32(pmi + 0xC) if heap(pmi) else 0
    cab = m_.bloco(maddr, 0x50) if heap(maddr) else b""
    nmat = struct.unpack_from("<H", cab, 0xA)[0] if cab else -1
    cf.anota(
        "cEm",
        "0x190",
        f"{h(pmi)} → modelo {h(maddr)}",
        BATE if cab and 0 < nmat < 64 and m_.u32(maddr + 0xC) else DIVERGE,
        f"cabeçalho do .bin: {nmat} materiais, tabela {h(m_.u32(maddr + 0xC)) if cab else '—'}",
    )
    cop = m_.vec3(pl + 0x290)
    cf.anota(
        "cEm",
        "0x290",
        f"{[round(v) for v in cop]}",
        BATE if math.dist(cop, pos) < 500 else DIVERGE,
        "igual a pos",
    )
    cf.anota("cEm", "0x2FC", str(m_.u16(pl + 0x2FC)), LIDO, "número de animação; sem relação independente")
    cf.anota(
        "cEm",
        "0x320",
        f"raio {m_.f32(pl + 0x330):.0f}",
        BATE if m_.f32(pl + 0x330) == 400.0 else DIVERGE,
        "cAtariInfo+0x10 = 400 no jogador",
    )
    cf.anota("cEm", "0x4D0", h(m_.u32(pl + 0x4D0)), LIDO, "registro de acerto; sem relação independente")
    an = m_.u32(pl + 0x710)
    cf.anota(
        "cEm",
        "0x710",
        h(an),
        BATE if an == 0 or ANEXOS <= an < ANEXOS + 0x10000 else DIVERGE,
        "0 ou dentro do vetor de anexos 0x017BCDF0",
    )
    # ---- cAtariInfo (jogador) ------------------------------------------------------------------------------
    at = pl + 0x320
    cf.anota("cAtariInfo", "0x00", f"{[round(v) for v in m_.vec3(at)]}", LIDO, "sem relação independente")
    cf.anota(
        "cAtariInfo",
        "0x10",
        f"{m_.f32(at + 0x10):.0f}",
        BATE if m_.f32(at + 0x10) == 400.0 else DIVERGE,
        "400 no jogador",
    )
    cf.anota("cAtariInfo", "0x14", f"{m_.f32(at + 0x14):.0f}", LIDO, "sem relação independente")
    cf.anota("cAtariInfo", "0x18", f"{m_.f32(at + 0x18):.0f}", LIDO, "sem relação independente")
    cf.anota("cAtariInfo", "0x1C", str(m_.s16(at + 0x1C)), LIDO, "sem relação independente")
    cf.anota(
        "cAtariInfo",
        "0x1E",
        h(m_.u16(at + 0x1E)),
        BATE if m_.u16(at + 0x1E) == 0x1301 else DIVERGE,
        "0x1301 no jogador",
    )
    cf.anota(
        "cAtariInfo",
        "0x20",
        f"{m_.f32(at + 0x20):.0f}, {m_.f32(at + 0x24):.0f}",
        BATE if abs(m_.f32(at + 0x20) - m_.f32(at + 0x10)) < 1e-3 else DIVERGE,
        "raio-alvo = raio quando a interpolação terminou",
    )
    cf.anota(
        "cAtariInfo",
        "0x28",
        str(m_.u16(at + 0x28)),
        BATE if m_.u16(at + 0x28) == 0 else DIVERGE,
        "0 quadros restantes com o jogador parado",
    )
    mp = m_.vec3(at + 0x40)
    cf.anota(
        "cAtariInfo",
        "0x40",
        f"{[round(v) for v in mp]}",
        BATE
        if abs(mp[0] - pos[0]) < 50 and abs(mp[2] - pos[2]) < 50 and 700 < mp[1] - pos[1] < 1000
        else DIVERGE,
        f"pos + (0, {mp[1] - pos[1]:.0f}, 0)",
    )
    mo = m_.vec3(at + 0x50)
    cf.anota(
        "cAtariInfo",
        "0x50",
        f"{[round(v) for v in mo]}",
        BATE if math.dist(mo, mp) < 500 else DIVERGE,
        "igual a m_Pos parado",
    )
    nx = m_.u32(at + 0x60)
    cf.anota("cAtariInfo", "0x60", h(nx), BATE if nx == 0 or heap(nx) else DIVERGE, "0 ou ponteiro no heap")
    # ---- EM_LIST --------------------------------------------------------------------------------------
    if pares:
        b, no, e = inim
        cf.anota(
            "EM_LIST",
            "0x00",
            h(e[0]),
            BATE if e[0] & 2 else DIVERGE,
            "bit 1 (já criada) ligado numa entrada criada",
        )
        cf.anota(
            "EM_LIST",
            "0x01",
            h(e[1]),
            BATE if e[1] == m_.u8(b + 0x11C) else DIVERGE,
            f"cEm+0x11C = {m_.u8(b + 0x11C)}",
        )
        cf.anota(
            "EM_LIST",
            "0x02",
            str(e[2]),
            BATE if e[2] == m_.u8(b + 0x11D) else DIVERGE,
            f"cEm+0x11D = {m_.u8(b + 0x11D)}",
        )
        cf.anota(
            "EM_LIST",
            "0x03",
            str(e[3]),
            BATE if e[3] == m_.u8(b + 0x4BD) else DIVERGE,
            f"cEm+0x4BD = {m_.u8(b + 0x4BD)}",
        )
        fl = struct.unpack_from("<I", e, 4)[0]
        cf.anota(
            "EM_LIST",
            "0x04",
            h(fl),
            BATE if fl == m_.u32(b + 0x4AC) else DIVERGE,
            f"cEm+0x4AC = {h(m_.u32(b + 0x4AC))}",
        )
        hp = struct.unpack_from("<H", e, 8)[0]
        cf.anota(
            "EM_LIST",
            "0x08",
            str(hp),
            BATE if hp == m_.s16(b + 0x4B2) else DIVERGE,
            f"cEm+0x4B2 = {m_.s16(b + 0x4B2)}",
        )
        cf.anota(
            "EM_LIST",
            "0x0B",
            str(e[0xB]),
            BATE if e[0xB] == m_.u8(b + 0x4CA) else DIVERGE,
            f"cEm+0x4CA = {m_.u8(b + 0x4CA)}",
        )
        ecm = struct.unpack_from("<hhh", e, 0xC)
        d = math.dist([v * 10 for v in ecm], m_.vec3(b + 0xC0))
        cf.anota(
            "EM_LIST", "0x0C", str(list(ecm)), BATE if d < 2000 else DIVERGE, f"×10 a {d:.0f} mm de cEm+0xC0"
        )
        erot = struct.unpack_from("<hhh", e, 0x12)
        ay = m_.f32(b + 0xD4)
        dy = abs((ay - erot[1] * math.pi / 16384 + math.pi) % (2 * math.pi) - math.pi)
        cf.anota(
            "EM_LIST",
            "0x12",
            str(list(erot)),
            BATE if dy < 0.5 else DIVERGE,
            f"×π/16384 a {dy:.3f} rad de cEm+0xD4",
        )
        room = struct.unpack_from("<H", e, 0x18)[0]
        cf.anota("EM_LIST", "0x18", h(room), BATE if room == sala else DIVERGE, f"pG+0x7EB8 = {h(sala)}")
        gr = struct.unpack_from("<h", e, 0x1A)[0]
        cf.anota(
            "EM_LIST",
            "0x1A",
            str(gr),
            BATE if abs(gr * 1000 - m_.f32(b + 0x4A4)) < 1 else DIVERGE,
            f"×1000 = cEm+0x4A4 {m_.f32(b + 0x4A4):.0f}",
        )
        cf.anota("EM_LIST", "0x1C", e[0x1C:0x20].hex(), LIDO, "reserva")
        vazias = sum(1 for i in range(256) if lista[i][1] == 0)
        cf.obs("EM_LIST", f"{len(entradas)} entradas ocupadas, {vazias} vazias; {len(pares)} criadas em cEm")
    elif entradas:
        # lista carregada mas nenhuma entrada criada: só as relações internas da própria lista
        ents = [lista[i] for i in entradas]
        bf0 = {e[0] for e in ents}
        cf.anota(
            "EM_LIST",
            "0x00",
            str(sorted(h(x)[-2:] for x in bf0)),
            LIDO,
            f"contagens: {dict(sorted((h(x)[-2:], sum(1 for e in ents if e[0] == x)) for x in bf0))}; "
            "nenhum cEm vivo veio da lista, logo bit 0 e bit 1 não significam 'cEm vivo agora'",
        )
        ids_l = sorted({e[1] for e in ents})
        cf.anota(
            "EM_LIST",
            "0x01",
            str([h(x)[-2:] for x in ids_l]),
            BATE if all(0 < x < 0x80 for x in ids_l) else DIVERGE,
            "tipos válidos (1..0x7F; 0x0F é o aliado com modelo de jogador)",
        )
        cf.anota("EM_LIST", "0x02", str(sorted({e[2] for e in ents})), LIDO, "variante")
        cf.anota("EM_LIST", "0x03", str(sorted({e[3] for e in ents})), LIDO, "set")
        cf.anota(
            "EM_LIST",
            "0x04",
            str(sorted({h(struct.unpack_from("<I", e, 4)[0]) for e in ents})[:6]),
            LIDO,
            "flag",
        )
        hps = [struct.unpack_from("<H", e, 8)[0] for e in ents]
        cf.anota(
            "EM_LIST",
            "0x08",
            f"{min(hps)}..{max(hps)}",
            BATE if all(0 < x <= 60000 for x in hps) else DIVERGE,
            "vida > 0",
        )
        cf.anota("EM_LIST", "0x0B", str(sorted({e[0xB] for e in ents})), LIDO, "Character")
        poss = [struct.unpack_from("<hhh", e, 0xC) for e in ents]
        cf.anota(
            "EM_LIST",
            "0x0C",
            f"{len(poss)} posições; x {min(p_[0] for p_ in poss)}..{max(p_[0] for p_ in poss)} cm",
            BATE if all(abs(p_[0]) < 30000 and abs(p_[2]) < 30000 for p_ in poss) else DIVERGE,
            "dentro de ±300 m",
        )
        rots = [struct.unpack_from("<hhh", e, 0x12) for e in ents]
        cf.anota(
            "EM_LIST",
            "0x12",
            str(sorted({r[1] for r in rots})[:8]),
            BATE if all(-32768 <= r[1] <= 32767 and r[0] == 0 == r[2] for r in rots) else DIVERGE,
            "só o eixo y (π/16384) é usado",
        )
        rooms = {struct.unpack_from("<H", e, 0x18)[0] for e in ents}
        cf.anota(
            "EM_LIST",
            "0x18",
            str(sorted(h(r) for r in rooms)),
            BATE if {r >> 8 for r in rooms} == {sala >> 8} else DIVERGE,
            f"todas no estágio de pG+0x7EB8 ({sala >> 8})",
        )
        grs = {struct.unpack_from("<h", e, 0x1A)[0] for e in ents}
        cf.anota(
            "EM_LIST",
            "0x1A",
            str(sorted(grs)),
            BATE if all(0 <= g <= 100 for g in grs) else DIVERGE,
            "raio de guarda em metros (0..100)",
        )
        cf.anota("EM_LIST", "0x1C", str(sorted({e[0x1C:0x20].hex() for e in ents})[:4]), LIDO, "reserva")
        cf.obs(
            "EM_LIST",
            f"{len(entradas)} entradas ocupadas, nenhuma criada em cEm: os cruzamentos com cEm ficam para um estado com inimigo da lista",
        )
    else:
        for d in cf.campos["EM_LIST"]:
            cf.anota("EM_LIST", d, "—", NAO, "lista vazia neste estado")
    # ---- cItemMgr --------------------------------------------------------------------------------------
    vet, nvag = m_.u32(ITEM_MGR + 0x14), m_.u32(ITEM_MGR + 0x1C)
    cf.anota("cItemMgr", "0x14", h(vet), BATE if heap(vet) else DIVERGE, "no heap")
    cf.anota("cItemMgr", "0x1C", str(nvag), BATE if nvag == 384 else DIVERGE, "384")
    itens = [m_.bloco(vet + 14 * i, 14) for i in range(min(nvag, 384))]
    ocup = [(i, it) for i, it in enumerate(itens) if it[4] & 1]
    eq = m_.u32(ITEM_MGR + 0xC)
    eq_id = m_.u16(ITEM_MGR + 0x10)
    id_na_vaga = (
        struct.unpack_from("<H", itens[(eq - vet) // 14], 0)[0] if vet <= eq < vet + 14 * nvag else -1
    )
    cf.anota(
        "cItemMgr",
        "0x0C",
        h(eq),
        BATE if id_na_vaga == eq_id else DIVERGE,
        f"vaga {(eq - vet) // 14 if id_na_vaga >= 0 else '?'} do vetor tem id {h(id_na_vaga)}",
    )
    cf.anota(
        "cItemMgr",
        "0x10",
        h(eq_id),
        BATE if id_na_vaga == eq_id else DIVERGE,
        "igual ao id da vaga apontada por +0xC",
    )
    ult = m_.u32(ITEM_MGR + 0x18)
    cf.anota(
        "cItemMgr",
        "0x18",
        h(ult),
        BATE if vet <= ult < vet + 14 * nvag or ult == 0 else DIVERGE,
        "dentro do vetor",
    )
    ids = sorted({struct.unpack_from("<H", it, 0)[0] for _, it in ocup})
    cf.anota(
        "cItemMgr",
        "item+0x0",
        f"{[h(i)[-4:] for i in ids]}",
        BATE if 0x23 in ids else DIVERGE,
        f"{len(ocup)} vagas ocupadas; pistola 0x23 presente",
    )
    pist = next((it for _, it in ocup if struct.unpack_from("<H", it, 0)[0] == 0x23), None)
    balas = next((it for _, it in ocup if struct.unpack_from("<H", it, 0)[0] == 0x04), None)
    cf.anota(
        "cItemMgr",
        "item+0x2",
        f"pistola {struct.unpack_from('<H', pist, 2)[0] if pist else '—'}; balas {struct.unpack_from('<H', balas, 2)[0] if balas else '—'}",
        BATE if pist and struct.unpack_from("<H", pist, 2)[0] == 1 else DIVERGE,
        "1 nas armas",
    )
    cf.anota(
        "cItemMgr",
        "item+0x4",
        f"{len(ocup)} com bit 0",
        BATE if 0 < len(ocup) < nvag else DIVERGE,
        "bit 0 = ocupada",
    )
    donos = {it[5] for _, it in ocup}
    d13 = m_.u8(ITEM_MGR + 0x13)
    cf.anota(
        "cItemMgr",
        "item+0x5",
        str(sorted(donos)),
        BATE if donos <= {d13} or len(donos) == 1 else DIVERGE,
        f"gerenciador +0x13 = {d13}",
    )
    cf.anota(
        "cItemMgr",
        "item+0x6",
        h(struct.unpack_from("<H", pist, 6)[0]) if pist else "—",
        LIDO,
        "níveis da pistola",
    )
    cap = struct.unpack_from("<H", pist, 8)[0] >> 3 if pist else -1
    # capacidade por nível da tabela de armas
    armas = [m_.bloco(TABELA_ARMAS + 0x16 * i, 0x16) for i in range(43)]
    arma_p = next((a for a in armas if struct.unpack_from("<H", a, 0)[0] == 0x23), None)
    caps = list(struct.unpack_from("<6H", arma_p, 8)) if arma_p else []
    cf.anota(
        "cItemMgr",
        "item+0x8",
        f"{cap} balas",
        BATE if 0 <= cap <= max(caps or [0]) else DIVERGE,
        f"≤ capacidade máxima {caps}",
    )
    pecas = {}
    for i in range(64):
        pc = m_.bloco(TABELA_PECAS + 0x58 * i, 0x58)
        pid = struct.unpack_from("<H", pc, 0)[0]
        if pid == 0xFFFF:
            break
        pecas[pid] = pc
    ctx["pecas"] = pecas
    mal = [it for _, it in ocup if it[0xD] == 1]
    dentro_ok = True
    for it in mal:
        pid = struct.unpack_from("<H", it, 0)[0]
        pc = pecas.get(pid)
        if pc:
            w, hh = pc[4], pc[5]
            cx, cy = struct.unpack_from("<ff", pc, 8)
            x0, y0 = it[0xA] / 2 - cx, it[0xB] / 2 - cy
            if it[0xC] & 1:
                w, hh = hh, w
            if x0 < -0.01 or y0 < -0.01 or x0 + w > 10.01 or y0 + hh > 6.01:
                dentro_ok = False
    cf.anota(
        "cItemMgr",
        "item+0xA",
        f"{len(mal)} itens na maleta",
        BATE if mal and dentro_ok else DIVERGE,
        "canto = centro − centro da peça; todos dentro da maleta 10×6",
    )
    cf.anota(
        "cItemMgr",
        "item+0xC",
        str(sorted({it[0xC] for _, it in ocup})),
        BATE if all(it[0xC] <= 7 for _, it in ocup) else DIVERGE,
        "0..7",
    )
    cf.anota(
        "cItemMgr",
        "item+0xD",
        str(sorted({it[0xD] for _, it in ocup})),
        BATE if all(it[0xD] <= 1 for _, it in ocup) else DIVERGE,
        "0 ou 1",
    )
    # ---- tabelas_itens -----------------------------------------------------------------------------------
    pc = pecas.get(0x23)
    cf.anota(
        "tabelas_itens",
        "peça+0x0",
        f"{len(pecas)} peças até 0xFFFF",
        BATE if len(pecas) == 64 else DIVERGE,
        "64 entradas",
    )
    cf.anota(
        "tabelas_itens",
        "peça+0x4",
        str(pc[4]) if pc else "—",
        BATE if pc and pc[4] == 3 else DIVERGE,
        "pistola 3",
    )
    cf.anota(
        "tabelas_itens",
        "peça+0x5",
        str(pc[5]) if pc else "—",
        BATE if pc and pc[5] == 2 else DIVERGE,
        "pistola 2",
    )
    cxy = struct.unpack_from("<ff", pc, 8) if pc else (0, 0)
    cf.anota(
        "tabelas_itens",
        "peça+0x8",
        str([round(v, 2) for v in cxy]),
        BATE if cxy == (1.0, 0.5) else DIVERGE,
        "pistola (1,0; 0,5)",
    )
    grade = pc[0x10 : 0x10 + pc[4] * pc[5]] if pc else b""
    cf.anota(
        "tabelas_itens",
        "peça+0x10",
        grade.decode("latin-1"),
        BATE if grade == b"1" * len(grade) and grade else DIVERGE,
        "largura × altura de '1'",
    )
    n_ids = sum(1 for a in armas if struct.unpack_from("<H", a, 0)[0] not in (0, 0xFFFF))
    cf.anota(
        "tabelas_itens",
        "arma+0x0",
        f"{n_ids} ids",
        BATE if arma_p is not None else DIVERGE,
        "pistola 0x23 está na tabela",
    )
    foguete = next((a for a in armas if a[3] == 13), None)
    cf.anota(
        "tabelas_itens",
        "arma+0x3",
        f"nº 13 → id {h(struct.unpack_from('<H', foguete, 0)[0]) if foguete else '—'}",
        BATE if foguete is not None else DIVERGE,
        "lança-foguetes = 13",
    )
    cf.anota("tabelas_itens", "arma+0x4", str(arma_p[4]) if arma_p else "—", LIDO, "sem relação independente")
    cf.anota(
        "tabelas_itens",
        "arma+0x6",
        h(arma_p[6]) if arma_p else "—",
        BATE if arma_p and arma_p[6] == 0x04 else DIVERGE,
        "pistola → 0x04",
    )
    cf.anota(
        "tabelas_itens",
        "arma+0x8",
        str(caps),
        BATE if caps == [10, 13, 16, 19, 22, 25] else DIVERGE,
        "10/13/16/19/22/25",
    )
    # ---- modulos -----------------------------------------------------------------------------------------
    mods = ctx.get("mods") or [
        (
            m_.u16(TABELA_MODULOS + i * 0x98 + 0x80),
            m_.u32(TABELA_MODULOS + i * 0x98 + 0x84),
            m_.u32(TABELA_MODULOS + i * 0x98 + 0x88),
            m_.u32(TABELA_MODULOS + i * 0x98 + 0x8C),
            m_.u32(TABELA_MODULOS + i * 0x98 + 0x90),
        )
        for i in range(4)
    ]
    flags = [m_.u16(TABELA_MODULOS + i * 0x98 + 0x82) for i in range(4)]
    inis = [m_.u32(TABELA_MODULOS + i * 0x98 + 0x94) for i in range(4)]
    tipos_vivos = {m_.u8(b + 0x11C) for b in vagas}
    usados = [(t, dat, rel, td, tr) for t, dat, rel, td, tr in mods if t]
    cf.anota(
        "modulos",
        "0x80",
        str([h(t)[-4:] for t, *_ in mods]),
        BATE if usados and {t for t, *_ in usados} & tipos_vivos else DIVERGE,
        f"tipos vivos no vetor: {sorted(h(t)[-4:] for t in tipos_vivos)}; ao menos um módulo residente tem personagem vivo",
    )
    cf.anota(
        "modulos",
        "0x82",
        str([h(f)[-4:] for f in flags]),
        BATE if all(f & 2 for f, (t, *_) in zip(flags, mods, strict=True) if t) else DIVERGE,
        "bit 2 (ligado) em toda entrada usada; bits 1/4 dizem se o carregador alocou .rel/.dat por esta tabela",
    )
    cf.anota(
        "modulos",
        "0x84",
        str([h(d) for _, d, *_ in usados]),
        BATE if all(heap(d) for _, d, *_ in usados) else DIVERGE,
        "no heap",
    )
    snr = [m_.bloco(rel, 4) for _, _, rel, *_ in usados if heap(rel)]
    cf.anota(
        "modulos",
        "0x88",
        str([h(r) for _, _, r, *_ in usados]),
        BATE if snr and all(s == b"SNR2" for s in snr) else DIVERGE,
        f"cada .rel começa por 'SNR2': {[s.decode('latin-1') for s in snr]}",
    )
    cf.anota(
        "modulos",
        "0x8C",
        str([h(td) for *_, td, _ in usados]),
        BATE if all(td % 0x800 == 0 for *_, td, _ in usados) else DIVERGE,
        "múltiplo de 0x800",
    )
    cf.anota(
        "modulos",
        "0x90",
        str([h(tr) for *_, tr in usados]),
        BATE if all(tr % 0x800 == 0 for *_, tr in usados) else DIVERGE,
        "múltiplo de 0x800",
    )
    ini_ok = all(rel <= ini < rel + tr for (t, dat, rel, td, tr), ini in zip(mods, inis, strict=True) if t)
    cf.anota(
        "modulos",
        "0x94",
        str([h(i) for i, (t, *_) in zip(inis, mods, strict=True) if t]),
        BATE if ini_ok else DIVERGE,
        "dentro do .rel da entrada",
    )
    afs = md.Afs(iso)
    ctx["afs"] = afs
    arq = [
        (
            t,
            m_.u16(0x00328458 + t * 8),
            m_.u16(0x00328458 + t * 8 + 2),
            m_.u16(0x00328458 + t * 8 + 4),
            m_.u16(0x00328458 + t * 8 + 6),
        )
        for t, *_ in usados
    ]
    cf.anota(
        "modulos",
        "arq+0x0",
        str([(h(t)[-4:], i) for t, i, *_ in arq]),
        BATE if all(i < afs.n and afs.nomes[i].lower().endswith(".dat") for _, i, *_ in arq) else DIVERGE,
        f"índice < {afs.n} e nome .dat no AFS: {[afs.nomes[i] for _, i, *_ in arq if i < afs.n]}",
    )
    cf.anota(
        "modulos",
        "arq+0x2",
        str([(h(t)[-4:], i) for t, _, i, *_ in arq]),
        BATE if all(i < afs.n and afs.nomes[i].lower().endswith(".rel") for _, _, i, *_ in arq) else DIVERGE,
        f"nome .rel no AFS: {[afs.nomes[i] for _, _, i, *_ in arq if i < afs.n]}",
    )
    cf.anota("modulos", "arq+0x4", str([i for *_, i, _ in arq]), LIDO, "sem relação independente")
    cf.anota("modulos", "arq+0x6", str([i for *_, i in arq]), LIDO, "sem relação independente")
    # tamanho do .rel no AFS × tamanho na tabela
    for t, _, irel, *_ in arq:
        a = afs.arquivo(irel)
        tr = next(tr for tt, *_, tr in usados if tt == t)
        cf.obs(
            "modulos",
            f"tipo {h(t)[-4:]}: .rel {a.nome} {a.tamanho} B no AFS; tabela +0x90 = {tr} ({'bate' if (a.tamanho + 0x7FF) // 0x800 * 0x800 == tr else 'diverge'})",
        )
    # ---- afs --------------------------------------------------------------------------------------------
    with iso.open("rb") as f:
        f.seek(afs.base)
        cab = f.read(16)
        tam_iso = f.seek(0, 2)
    cf.anota("afs", "0x00", repr(cab[:4]), BATE if cab[:4] == b"AFS\0" else DIVERGE, "lido na ISO")
    cf.anota("afs", "0x04", str(afs.n), BATE if afs.n == 2628 else DIVERGE, "2628")
    off, tam_n = afs.entradas[afs.n]
    dentro = all(afs.base + o + t <= tam_iso for o, t in afs.entradas)
    cf.anota(
        "afs",
        "0x08",
        f"última entrada ({off}, {tam_n})",
        BATE if dentro and tam_n == 48 * afs.n else DIVERGE,
        f"todas dentro da ISO; nomes = 48 × {afs.n} = {48 * afs.n}",
    )
    cf.anota(
        "afs",
        "nomes",
        f"{afs.nomes[0]} … {afs.nomes[-1]}",
        BATE if all(n for n in afs.nomes) else DIVERGE,
        "nenhum nome vazio",
    )
    # ---- tarefas -----------------------------------------------------------------------------------------
    tar = [m_.bloco(TAREFAS + i * 0x350, 0x350) for i in range(20)]
    ativas = [(i, t) for i, t in enumerate(tar) if t[5] in (0x16, 0x17)]
    tipos = [t[5] for t in tar]
    cf.anota(
        "tarefas",
        "0x05",
        str([h(x)[-2:] for x in tipos]),
        BATE if ativas and all(x in (0, 0x16, 0x17) for x in tipos) else DIVERGE,
        f"{len(ativas)} vagas com 0x16/0x17; outros valores vistos: "
        f"{[(i, h(x)[-2:], h(struct.unpack_from('<I', tar[i], 0x344)[0])) for i, x in enumerate(tipos) if x not in (0, 0x16, 0x17)]}",
    )
    cf.anota(
        "tarefas",
        "0x04",
        str([t[4] for _, t in ativas]),
        LIDO,
        "estado (TaskExec grava 1; TaskSleep liga 0x80)",
    )
    sem = [struct.unpack_from("<I", t, 0xC)[0] for _, t in ativas]
    cf.anota(
        "tarefas",
        "0x0C",
        str(sem),
        BATE if all(0 < s < 0x1000 for s in sem) else DIVERGE,
        "id de semáforo do kernel (pequeno)",
    )
    cf.anota("tarefas", "0x10", str([t[0x10] for _, t in ativas]), LIDO, "sem relação independente")
    cf.anota(
        "tarefas",
        "0x14",
        str([struct.unpack_from("<H", t, 0x14)[0] for _, t in ativas]),
        LIDO,
        "quadros a dormir",
    )
    cf.anota(
        "tarefas",
        "0x18",
        str([h(struct.unpack_from("<I", t, 0x18)[0]) for _, t in ativas]),
        LIDO,
        "argumento",
    )
    f340 = [struct.unpack_from("<I", t, 0x340)[0] for _, t in ativas]
    f344 = [struct.unpack_from("<I", t, 0x344)[0] for _, t in ativas]
    cf.anota(
        "tarefas",
        "0x344",
        str([h(x) for x in f344]),
        BATE if f344 and all(codigo(x) or heap(x) for x in f344) else DIVERGE,
        "endereço de código",
    )
    cf.anota(
        "tarefas", "0x340", str([h(x) for x in f340]), BATE if f340 == f344 else DIVERGE, "cópia de +0x344"
    )
    cor = m_.u32(TAREFA_CORRENTE)
    cf.obs(
        "tarefas",
        f"tarefa corrente 0x451680 = {h(cor)} ({'na tabela' if TAREFAS <= cor < TAREFAS + 20 * 0x350 else 'fora da tabela'})",
    )
    # ---- cenas -------------------------------------------------------------------------------------------
    raiz = m_.u32(RAIZ_CENAS)
    inicio = raiz + 0x8C
    nos, q, guarda = [], m_.u32(inicio), 0
    while q != 0xFFFFFFFF and guarda < 512:
        if q > inicio:
            nos.append(q)
        q = m_.u32(q)
        guarda += 1
    areas = [m_.bloco(n, 0xA0) for n in nos]
    cf.obs(
        "cenas",
        f"raiz *0x4563F0 = {h(raiz)}; lista a partir de {h(inicio)} com {len(nos)} áreas (percorridas {guarda} nós)",
    )
    cf.anota(
        "cenas",
        "0x00",
        f"{len(nos)} elos",
        BATE if nos else DIVERGE,
        "lista termina em 0xFFFFFFFF; nós acima da raiz são áreas",
    )
    cf.anota("cenas", "0x04", "—", LIDO, "volume não decodificado")
    cf.anota("cenas", "0x34", str(sorted({a[0x34] for a in areas})), LIDO, "sinalizadores")
    ids_ = [a[0x35] for a in areas]
    cf.anota(
        "cenas",
        "0x35",
        str(sorted(set(ids_))),
        BATE if areas and all(i <= 21 for i in ids_) else DIVERGE,
        "0..21",
    )
    nums = [a[0x36] for a in areas]
    cf.anota(
        "cenas",
        "0x36",
        f"{len(nums)} números, {len(set(nums))} distintos",
        BATE if len(nums) == len(set(nums)) else DIVERGE,
        "número único por área (chave de SceAtPtr)",
    )
    cf.anota("cenas", "0x38", str(sorted({h(a[0x38])[-2:] for a in areas})), LIDO, "trg_type")
    cf.anota(
        "cenas",
        "0x39",
        str(sorted({a[0x39] for a in areas})),
        BATE if all(a[0x39] in (0, 1, 2, 8, 3, 9, 10, 11) for a in areas) else DIVERGE,
        "combinação de 1/2/8",
    )
    cf.anota(
        "cenas",
        "0x3A",
        str(sorted({a[0x3A] for a in areas})),
        BATE if all(a[0x3A] <= 0x14 for a in areas) else DIVERGE,
        "≤ 0x14",
    )
    cf.anota("cenas", "0x3B", str(sorted({h(a[0x3B])[-2:] for a in areas})), LIDO, "cópia")
    cf.anota(
        "cenas",
        "0x3C",
        str(sorted({h(struct.unpack_from("<I", a, 0x3C)[0]) for a in areas})[:6]),
        LIDO,
        "argumento",
    )
    fns = [struct.unpack_from("<I", a, 0x40)[0] for a in areas]
    cf.anota(
        "cenas",
        "0x40",
        str(sorted({h(x) for x in fns})[:8]),
        BATE if all(x == 0 or codigo(x) or heap(x) for x in fns) else DIVERGE,
        "0 ou código",
    )
    pri = [a[0x44] for a in areas]
    cf.anota("cenas", "0x44", str(sorted(set(pri))), BATE if all(x <= 15 for x in pri) else DIVERGE, "0..15")
    cf.anota("cenas", "0x45", str(sorted({a[0x45] for a in areas})), LIDO, "kind")
    par = [struct.unpack_from("<I", a, 0x4C)[0] for a in areas]
    cf.anota(
        "cenas",
        "0x4C",
        str(sorted({h(x) for x in par})[:6]),
        BATE if all(x == 0 or heap(x) for x in par) else DIVERGE,
        "0 ou ponteiro",
    )
    cf.anota("cenas", "0x60", "—", LIDO, "dados por tipo não decodificados")
    # ---- colisao -----------------------------------------------------------------------------------------
    sp, sn, ss, sa, st = (
        m_.u32(SAT_MGR),
        m_.u32(SAT_MGR + 4),
        m_.u32(SAT_MGR + 8),
        m_.u32(SAT_MGR + 0x10),
        m_.u32(SAT_MGR + 0x1C),
    )
    et = m_.u32(EAT_MGR + 0x1C)
    cf.anota("colisao", "mgr+0x00", h(sp), BATE if heap(sp) else DIVERGE, "no heap")
    cf.anota("colisao", "mgr+0x04", str(sn), BATE if sn == 20 else DIVERGE, "20")
    cf.anota("colisao", "mgr+0x08", h(ss), BATE if ss == 0xF0 else DIVERGE, "0xF0")
    cf.anota(
        "colisao",
        "mgr+0x10",
        h(sa),
        BATE if sa == 0 or sp <= sa < sp + sn * ss else DIVERGE,
        "dentro do vetor",
    )
    cf.anota(
        "colisao", "mgr+0x1C", f"SatMgr {st}, EatMgr {et}", BATE if (st, et) == (0, 1) else DIVERGE, "0 e 1"
    )
    sat = sp
    bf, fl = m_.u32(sat), m_.u16(sat + 0x2A)
    nv, npl = m_.u16(sat + 0x1C), m_.u16(sat + 0x1E)
    cls = struct.unpack("<HHH", m_.bloco(sat + 0x20, 6))
    arq_ = m_.u32(sat + 0x60)
    pv, pn, pe, pp = (m_.u32(sat + o) for o in (0xC, 0x10, 0x14, 0x18))
    cf.anota("colisao", "sat+0x00", h(bf), BATE if bf & 1 else DIVERGE, "peça da sala viva")
    cf.anota("colisao", "sat+0x2A", h(fl), BATE if fl & 4 else DIVERGE, "ativa (4)")
    cf.anota("colisao", "sat+0x1C", str(nv), BATE if 0 < nv < 65536 else DIVERGE, "> 0")
    cf.anota("colisao", "sat+0x1E", str(npl), BATE if 0 < npl <= 8192 else DIVERGE, "1..8192")
    cf.anota(
        "colisao",
        "sat+0x20",
        str(list(cls)),
        BATE if sum(cls) == npl else DIVERGE,
        f"soma = nº de polígonos {npl}",
    )
    cf.anota("colisao", "sat+0x60", h(arq_), BATE if heap(arq_) else DIVERGE, "no heap")
    cf.anota(
        "colisao", "sat+0x0C", h(pv), BATE if arq_ <= pv < arq_ + 0x200000 else DIVERGE, "dentro do arquivo"
    )
    cf.anota("colisao", "sat+0x10", h(pn), BATE if pv < pn else DIVERGE, "depois dos vértices")
    cf.anota("colisao", "sat+0x14", h(pe), BATE if pn < pe else DIVERGE, "depois das normais")
    cf.anota("colisao", "sat+0x18", h(pp), BATE if pe < pp else DIVERGE, "depois das arestas")
    # polígonos: índices dentro dos limites
    polys = m_.bloco(pp, min(npl, 256) * 0x14)
    idx_ok = all(max(struct.unpack_from("<HHH", polys, i * 0x14)) < nv for i in range(min(npl, 256)))
    cf.obs("colisao", f"índices de vértice dos primeiros {min(npl, 256)} polígonos < {nv}: {idx_ok}")
    bloco = m_.u32(sat + 0x30)
    cf.anota(
        "colisao",
        "sat+0x30",
        h(bloco),
        BATE if arq_ <= bloco < arq_ + 0x200000 else DIVERGE,
        "dentro do arquivo",
    )
    mt, mi = m_.mat4(sat + 0x70), m_.mat4(sat + 0xB0)
    prod = mul(mt, mi)
    cf.anota(
        "colisao",
        "sat+0x70",
        f"translação {[round(v) for v in mt[3][:3]]}",
        BATE if identidade(prod) else DIVERGE,
        "matriz × inversa = identidade",
    )
    cf.anota(
        "colisao",
        "sat+0xB0",
        f"translação {[round(v) for v in mi[3][:3]]}",
        BATE if identidade(prod) else DIVERGE,
        "matriz × inversa = identidade",
    )
    # ---- camera ------------------------------------------------------------------------------------------
    olho, alvo = m_.vec3(CAM_OLHO), m_.vec3(CAM_ALVO)
    vp, tela = m_.mat4(CAM_VP), m_.mat4(CAM_TELA)
    v = [alvo[0], alvo[1], alvo[2], 1.0]
    r = [sum(v[k] * vp[k][j] for k in range(4)) for j in range(4)]
    w = r[3]
    sx, sy = (256 - r[0] / w * 1104.64, 224 + r[1] / w * 1706.67) if w else (-1, -1)
    dist = math.dist(olho, alvo)
    cf.anota(
        "camera",
        "0x003CA220",
        f"{[round(x) for x in olho]}",
        BATE if 500 < dist < 20000 else DIVERGE,
        f"a {dist:.0f} mm do alvo",
    )
    cf.anota(
        "camera",
        "0x003CA230",
        f"{[round(x) for x in alvo]}",
        BATE if math.dist(alvo, pos) < 3000 else DIVERGE,
        f"a {math.dist(alvo, pos):.0f} mm do jogador",
    )
    cf.anota(
        "camera",
        "0x004327C0",
        f"w = {w:.0f}",
        BATE if abs(w - dist) < 0.05 * dist else DIVERGE,
        f"w ≈ distância olho-alvo {dist:.0f}",
    )
    cf.anota(
        "camera",
        "0x00432840",
        f"alvo em tela ({sx:.0f}, {sy:.0f})",
        BATE if abs(sx - 256) < 8 and abs(sy - 224) < 8 else DIVERGE,
        "alvo projeta no centro (256, 224)",
    )
    cf.obs("camera", f"matriz de tela: diagonal {[round(tela[i][i], 2) for i in range(4)]}")
    # ---- modelo_visual -------------------------------------------------------------------------------------
    tbl = m_.u32(OBJETOS)  # scrObjTbl: ponteiro para um vetor (heap) de ponteiros cObj
    objs = [o for o in struct.unpack("<250I", m_.bloco(tbl, 1000)) if heap(o)] if heap(tbl) else []
    smd = m_.u32(SMD)
    # os cObj do cenário vivem no segundo gerente de objetos (cObjMgr 0x431D40: pArray, nArray, size 0x4F0)
    o_arr, o_n, o_sz = m_.u32(0x431D40), m_.u32(0x431D44), m_.u32(0x431D48)
    no_mgr = [o for o in objs if o_arr <= o < o_arr + o_n * o_sz and (o - o_arr) % o_sz == 0]
    cf.obs(
        "modelo_visual",
        f"cObjMgr 0x431D40: vetor {h(o_arr)} × {o_n} de {h(o_sz)}; {len(no_mgr)} dos {len(objs)} objetos da tabela estão nele",
    )
    cf.anota(
        "modelo_visual",
        "bin+0x00",
        f"modelo do jogador {h(maddr)}: {nmat} materiais",
        BATE if 0 < nmat < 64 else DIVERGE,
        "cabeçalho do .bin do jogador",
    )
    no_ = m_.u32(maddr + 0xC + 12) if heap(maddr) else 0
    cf.anota("modelo_visual", "nó", h(no_), LIDO, "ponteiro do nó")
    cf.anota("modelo_visual", "segmento", "—", NAO, "não decodificado nesta conferência")
    if objs:
        vivos = [o for o in objs if m_.u32(o) & 1]
        mats = [m_.mat4(o + 0x10) for o in vivos]
        escalas = [round(math.sqrt(sum(x * x for x in mm[0][:3])), 1) for mm in mats]
        cf.anota(
            "modelo_visual",
            "cObj+0x10",
            f"{len(vivos)} objetos vivos; escala da 1ª linha {sorted(set(escalas))[:6]}; "
            f"1º translação {[round(x) for x in mats[0][3][:3]]}",
            BATE
            if mats
            and all(mm[3][3] == 1.0 and all(math.isfinite(x) for row in mm for x in row) for mm in mats)
            and all(0.5 <= s <= 20 for s in escalas)
            and len(no_mgr) == len(objs)
            else DIVERGE,
            "matriz afim finita com a escala do objeto embutida (10 na maioria, 1 em alguns), [3][3] = 1; "
            "todos no vetor do cObjMgr",
        )
    else:
        cf.anota("modelo_visual", "cObj+0x10", "—", NAO, "tabela de objetos vazia")
    cf.obs("modelo_visual", f"SMD 0x4568A0 = {h(smd)}; {len(objs)} ponteiros cObj no heap")
    # ---- efeitos -------------------------------------------------------------------------------------------
    ger = m_.u32(EFEITOS)
    usadas = 0
    for i in range(0xD7):
        e3 = m_.u32(ger + 0x7400 + 0xC * i + 8)
        if e3 != 0xD6:
            usadas += 1
    cf.anota(
        "efeitos",
        "est+0x0",
        f"gerente {h(ger)}: {usadas} de 215 entradas usadas",
        BATE if heap(ger) and 0 < usadas < 215 else DIVERGE,
        "EspGetEstAddr: 3ª palavra 0xD6 = vazia",
    )
    # ---- controle ------------------------------------------------------------------------------------------
    cf.anota("controle", "0x00", h(m_.u32(CONTROLE)), LIDO, "ninguém aperta botão nesta conferência")
    # ---- snr2 ------------------------------------------------------------------------------------------------
    assin = []
    for t, _, rel, *_ in usados:
        cab = m_.bloco(rel, 64)
        assin.append(cab[:4].decode("latin-1"))
        cf.obs(
            "snr2",
            f".rel do tipo {h(t)[-4:]}: {cab[:4].decode('latin-1')} palavras {[h(x) for x in struct.unpack('<16I', cab)[1:8]]}",
        )
    if "0x00" in cf.campos["snr2"]:
        cf.anota(
            "snr2",
            "0x00",
            str(assin),
            BATE if assin and all(a == "SNR2" for a in assin) else DIVERGE,
            f"início de cada um dos {len(assin)} .rel residentes (tabela de módulos +0x88)",
        )
    # ---- tipos_inimigo ---------------------------------------------------------------------------------------
    tab = m_.bloco(0x003C8F40, 64 * 4)
    cf.obs("tipos_inimigo", f"primeiras 8 palavras: {[h(x) for x in struct.unpack('<8I', tab[:32])]}")
    return ctx


def main() -> int:
    perfil = json.loads(PERFIL.read_text(encoding="utf-8"))
    cf = Conferencia(perfil)
    c = Cliente(tempo_limite_s=20.0)
    c.conectar()
    try:
        ident = c.identificar()
        if c.status() != p.Status.RODANDO:
            print("emulador não está rodando")
            return 1
        if CARREGAR:
            c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([ESTADO])))
            for _ in range(40):
                time.sleep(0.5)
                if c.status() == p.Status.RODANDO:
                    break
            time.sleep(3.0)
        c.pausar(True)  # leituras coerentes entre si (um só quadro); só leitura, nada é escrito
        try:
            ctx = conferir(Leitor(c), cf, md.ISO_PADRAO)
        finally:
            c.pausar(False)
    finally:
        c.fechar()
    rnd = random.Random(SEMENTE)
    saida = {
        "data": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "jogo": {"serial": ident.serial, "crc": ident.crc, "versao": ident.versao_jogo},
        "estado": ESTADO,
        "sala": h(ctx["sala"]),
        "semente": SEMENTE,
        "estruturas": {},
    }
    for est, campos in cf.campos.items():
        res = cf.resultados[est]
        faltam = [d for d in campos if d not in res]
        sorteio = rnd.sample(campos, min(3, len(campos))) if campos else []
        saida["estruturas"][est] = {
            "campos": {d: res[d] for d in campos if d in res},
            "sem_leitura": faltam,
            "sorteados": sorteio,
            "observacoes": cf.observacoes[est],
        }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"estado {ESTADO}, sala {saida['sala']}, semente {SEMENTE}, {saida['data']}")
    for est, bloco in saida["estruturas"].items():
        cont = {}
        for r in bloco["campos"].values():
            cont[r["resultado"]] = cont.get(r["resultado"], 0) + 1
        print(
            f"== {est}: {dict(cont) or 'sem campos'}"
            + (f"; sem leitura: {bloco['sem_leitura']}" if bloco["sem_leitura"] else "")
        )
        for d in bloco["sorteados"]:
            r = bloco["campos"].get(d)
            print(
                f"   sorteado {d}: "
                + (f"{r['resultado']} — lido {r['lido']} ({r['relacao']})" if r else "sem leitura")
            )
        for r_d, r in bloco["campos"].items():
            if r["resultado"] == DIVERGE:
                print(f"   DIVERGE {r_d}: lido {r['lido']} ({r['relacao']})")
        for o in bloco["observacoes"]:
            print(f"   obs: {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
