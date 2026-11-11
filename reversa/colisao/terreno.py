"""Chão andável a partir do modelo VISUAL da sala.

Lê os objetos de cenário (tabela scrObjTbl 0x4568AC), interpreta o .bin de cada um na memória (formato PS2:
materiais -> nós -> segmentos de vértices int16 x fator de escala, triângulos em tiras), leva os triângulos ao
mundo pela matriz do objeto (+0x10), filtra os que estão perto do jogador e têm inclinação andável, e monta um
arquivo SAT (cSatFile) só de chão com um bloco único. Com --criar, aloca o arquivo com mem_alloc do jogo, registra
a peça via cSatMgr::create(dados) e desliga as paredes do jogador na região (como morro.py). Sem --criar, só analisa.

Uso: terreno.py [raio_m=30] [inclinacao_max_graus=60] [--criar]
"""

import json
import math
import struct
import sys
import time
from pathlib import Path

from iaemps2.bancada import modulos as md, personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente

SCR_OBJ_TBL = 0x004568AC
SATMGR = 0x0041AF10  # cSatMgr SatMgr (personagens); 0x41AF30 é o EatMgr (balas e objetos)
CREATE_DATA = 0x001A32D0  # cSatMgr::create(this, data, flag, pos, rot, type)
PL_NOHIT = 0x00400000
UNDO = Path(__file__).with_name("morro_undo.json")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
raio = float(args[0]) * 1000.0 if args else 30000.0
incl_max = float(args[1]) if len(args) > 1 else 60.0
criar = "--criar" in sys.argv
sala_inteira = "--sala" in sys.argv
if sala_inteira:
    raio = 1e9
ny_min = math.cos(math.radians(incl_max))

c = Cliente(porta=28011, tempo_limite_s=60.0)
c.conectar()
jog = pz.ler_vec3(c, pz.VETOR + 0xC0)
print(f"jogador em {tuple(round(v) for v in jog)}; raio {raio/1000:.0f} m; inclinação máx {incl_max:.0f}°")


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def triangulos_do_bin(base):
    """Devolve lista de triângulos (3 vértices locais já multiplicados pelo fator) do .bin em `base`."""
    h = md.ler_bloco(c, base, 0x50)
    magic, ntex = struct.unpack_from("<HH", h, 0)
    if magic != 0x30:
        return []
    nmat = struct.unpack_from("<H", h, 0xA)[0]
    mat_ofs = u32(h, 0xC)
    mats = md.ler_bloco(c, base + mat_ofs, 16 * nmat)
    tris = []
    for m in range(nmat):
        node = base + u32(mats, m * 16 + 12)
        nh = md.ler_bloco(c, node, 16)
        total, segs_m1, nbones = struct.unpack_from("<HBB", nh, 0)
        cab = 4 + nbones
        cab = ((cab + 15) // 16) * 16
        pos = node + cab
        for i in range(segs_m1 + 1):
            h1 = md.ler_bloco(c, pos, 16)
            pos += 16
            cor = True
            if h1[12] == 0 and h1[14] > 1:  # tabela de pesos (modelos com ossos)
                pos += h1[0] * 0x10
                h1 = md.ler_bloco(c, pos, 16)
                pos += 16
                cor = False
            h2 = md.ler_bloco(c, pos, 16)
            h3 = md.ler_bloco(c, pos + 16, 16)
            pos += 32
            n_linhas = h2[0]
            fator = struct.unpack_from("<f", h2, 12)[0]
            tam = h3[0] * 0x10
            dados = md.ler_bloco(c, pos, tam) if tam else b""
            pos += tam
            vs = []
            for k in range(n_linhas):
                o = k * 24
                if o + 24 > len(dados):
                    break
                x, y, z = struct.unpack_from("<hhh", dados, o)
                comp = struct.unpack_from("<H", dados, o + 14)[0]
                vs.append(((x * fator, y * fator, z * fator), comp))
            inv = False
            for k in range(2, len(vs)):
                if vs[k][1] == 0:
                    a_, b_, c_ = vs[k - 2][0], vs[k - 1][0], vs[k][0]
                    tris.append((a_, b_, c_) if inv else (c_, b_, a_))
                    inv = not inv
                else:
                    inv = False
            if i > 0:
                pos += 16  # EndTag
            # o primeiro segmento não tem EndTag antes do próximo? a ferramenta lê o EndTag só para i > 0
    return tris


def ao_mundo(v, m):
    x, y, z = v
    return (
        x * m[0] + y * m[4] + z * m[8] + m[12],
        x * m[1] + y * m[5] + z * m[9] + m[13],
        x * m[2] + y * m[6] + z * m[10] + m[14],
    )


tbl = u32(md.ler_bloco(c, SCR_OBJ_TBL, 4), 0)
objs = struct.unpack_from("<250I", md.ler_bloco(c, tbl, 1000), 0)
selecionados = []
paredes = []
total_tris = 0
for i, o in enumerate(objs):
    if not (0x100000 < o < 0x2000000):
        continue
    d = md.ler_bloco(c, o, 0x200)
    if not (u32(d, 0) & 1):
        continue
    m = struct.unpack_from("<16f", d, 0x10)
    info = u32(d, 0x190)
    if not info:
        continue
    model = u32(md.ler_bloco(c, info + 0xC, 4), 0)
    if not (0x100000 < model < 0x2000000):
        continue
    # caixa do modelo no mundo: pula objetos longe
    hb = md.ler_bloco(c, model + 0x30, 28)
    cx, cy, cz, _, w, hgt, dp = struct.unpack_from("<7f", hb, 0)
    centro = ao_mundo((cx, cy, cz), m)
    ext = max(w, hgt, dp) * max(abs(m[0]), abs(m[5]), abs(m[10]))
    if math.dist((centro[0], centro[2]), (jog[0], jog[2])) > raio + ext:
        continue
    tris = triangulos_do_bin(model)
    total_tris += len(tris)
    for t in tris:
        w0, w1, w2 = (ao_mundo(v, m) for v in t)
        if all(math.dist((v[0], v[2]), (jog[0], jog[2])) > raio for v in (w0, w1, w2)):
            continue
        ax, ay, az = (w1[k] - w0[k] for k in range(3))
        bx, by, bz = (w2[k] - w0[k] for k in range(3))
        nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-3:
            continue
        nx, ny, nz = nx / ln, ny / ln, nz / ln
        if abs(ny) < ny_min:
            paredes.append(((w0, w1, w2), (nx, ny, nz)))
            continue
        selecionados.append(((w0, w1, w2), (nx, ny, nz)))
print(f"triângulos lidos dos modelos próximos: {total_tris}; andáveis no raio (as duas orientações): {len(selecionados)}")
etapas = {"bruto": list(selecionados)}

# calibra o sinal da orientação: a face sob os pés do jogador é uma face de cima
def sob(px, pz_, lista):
    melhor = None
    for (a, b, cc), n in lista:
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0):
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if abs(y - jog[1]) < 400 and (melhor is None or abs(y - jog[1]) < abs(melhor[0] - jog[1])):
                melhor = (y, n[1])
    return melhor

pos_ = sum(1 for _, n in selecionados if n[1] > 0.9)
neg_ = sum(1 for _, n in selecionados if n[1] < -0.9)
sinal = 1.0 if pos_ >= neg_ else -1.0
print(f"faces quase horizontais: {pos_} com normal +y, {neg_} com -y; sinal das faces de cima = {sinal:+.0f}")
cima = []
for (a, b, cc), n in selecionados:
    if n[1] * sinal > 0:
        cima.append(((a, b, cc), (n[0] * sinal, n[1] * sinal, n[2] * sinal)) if sinal > 0 else ((a, cc, b), (-n[0], -n[1], -n[2])))
print(f"faces viradas para cima: {len(cima)} (descartadas as de baixo: {len(selecionados) - len(cima)})")
selecionados = cima
etapas["cima"] = list(cima)
if sinal < 0:
    paredes = [((a, cc, b), (-n[0], -n[1], -n[2])) for (a, b, cc), n in paredes]
print(f"faces de parede (mais íngremes que {incl_max:.0f}°): {len(paredes)}")

# mantém só a superfície mais alta: descarta triângulo com outro triângulo acima do seu centro (até 4 m)
CELG = 2000.0
grade = {}
for idx, ((a, b, cc), n) in enumerate(selecionados):
    xs_ = (a[0], b[0], cc[0]); zs_ = (a[2], b[2], cc[2])
    for gx in range(int(min(xs_) // CELG), int(max(xs_) // CELG) + 1):
        for gz in range(int(min(zs_) // CELG), int(max(zs_) // CELG) + 1):
            grade.setdefault((gx, gz), []).append(idx)
def acima_de(px, py, pz_, proprio):
    for j in grade.get((int(px // CELG), int(pz_ // CELG)), ()):
        if j == proprio:
            continue
        (a, b, cc), n = selecionados[j]
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0):
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if 50 < y - py < 1000:
                return True
    return False
topo = []
for idx, ((a, b, cc), n) in enumerate(selecionados):
    cx, cy, cz = ((a[k] + b[k] + cc[k]) / 3 for k in range(3))
    if not acima_de(cx, cy, cz, idx):
        topo.append(((a, b, cc), n))
print(f"só a superfície mais alta: {len(topo)} (cobertos descartados: {len(selecionados) - len(topo)})")
selecionados = topo
etapas["topo"] = list(topo)

# descarta os que coincidem com o chão/rampa que a colisão da sala já tem (diferença < 25 cm no centro)
pArray, nArray, size = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
sala = pArray  # a peça da sala é a primeira do vetor (construída na carga da sala)
d = md.ler_bloco(c, sala, 0x34)
vtx, nrm, _, poly = struct.unpack_from("<IIII", d, 0xC)
nv, npoly, nfloor, nslope, nwall, _, nnorm = struct.unpack_from("<HHHHHHH", d, 0x1C)
vs = md.ler_bloco(c, vtx, nv * 12)
ns = md.ler_bloco(c, nrm, nnorm * 12)
ps = md.ler_bloco(c, poly, npoly * 0x14)
V = [struct.unpack_from("<fff", vs, i * 12) for i in range(nv)]
NN = [struct.unpack_from("<fff", ns, i * 12) for i in range(nnorm)]
chao_sala = []
for i in range(nfloor + nslope):
    a, b, cc, k = struct.unpack_from("<HHHH", ps, i * 0x14)
    chao_sala.append((V[a], V[b], V[cc], NN[k]))

def altura_sala(px, pz_):
    melhor = None
    for a, b, cc, n in chao_sala:
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if melhor is None or y > melhor:
                melhor = y
    return melhor

novos = []
for (a, b, cc), n in selecionados:
    cx, cy, cz = ((a[k] + b[k] + cc[k]) / 3 for k in range(3))
    y = altura_sala(cx, cz)
    if y is not None and abs(y - cy) < 250:
        continue
    novos.append(((a, b, cc), n))
print(f"fora do chão que a colisão já tem: {len(novos)}")
selecionados = novos

# altura do terreno visual sob o jogador (validação da transformação)
def altura_sob(px, pz_):
    melhor = None
    for (a, b, cc), n in selecionados:
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0):
            if abs(n[1]) > 1e-6:
                y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
                if melhor is None or abs(y - jog[1]) < abs(melhor - jog[1]):
                    melhor = y
    return melhor

print(f"altura do terreno visual sob o jogador: {altura_sob(jog[0], jog[2])} (jogador y={jog[1]:.0f})")
etapas["final"] = list(selecionados)
def alturas_em(px, pz_, lista):
    out = []
    for (a, b, cc), n in lista:
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            out.append((round(a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]), round(n[1], 2)))
    return sorted(out, reverse=True)
for nome in ("bruto", "cima", "topo", "final"):
    print(f"  sob o jogador, etapa {nome}: {alturas_em(jog[0], jog[2], etapas[nome])}")
ang_ = struct.unpack_from("<f", md.ler_bloco(c, pz.VETOR + 0xD4, 4), 0)[0]
fx_, fz_ = math.sin(ang_), math.cos(ang_)
print(f"  frente do jogador: ({fx_:+.2f}, {fz_:+.2f}); perfil à frente (distância: altura final / inclinação máx das faces brutas):")
for dm in (0.5, 1, 1.5, 2, 3, 4, 6):
    px_, pz2 = jog[0] + fx_ * dm * 1000, jog[2] + fz_ * dm * 1000
    fin = alturas_em(px_, pz2, etapas["final"])
    bru = alturas_em(px_, pz2, etapas["bruto"])
    incl = max((math.degrees(math.acos(min(1.0, abs(ny_)))) for _, ny_ in bru), default=None)
    print(f"    {dm:>3} m: final {fin[:3]} | bruto {bru[:4]} | inclinação máx {incl if incl is None else round(incl)}°")
# paredes à frente: faces visuais íngremes a até 2,5 m na direção da frente, e paredes ativas da colisão da sala
pArrayA, nArrayA, sizeA = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
dA = md.ler_bloco(c, pArrayA, 0x34)
vtxA, nrmA, _, polyA = struct.unpack_from("<IIII", dA, 0xC)
nvA, npolyA, nflA, nslA, nwlA = struct.unpack_from("<HHHHH", dA, 0x1C)
vsA = md.ler_bloco(c, vtxA, nvA * 12); psA = md.ler_bloco(c, polyA, npolyA * 0x14)
perto_sala = []
for i in range(nflA + nslA, npolyA):
    v = struct.unpack_from("<HHH", psA, i * 0x14); st = struct.unpack_from("<I", psA, i * 0x14 + 0x10)[0]
    pts = [struct.unpack_from("<fff", vsA, k * 12) for k in v]
    cx2, cy2, cz2 = (sum(pt[j] for pt in pts) / 3 for j in range(3))
    dx_, dz_ = cx2 - jog[0], cz2 - jog[2]
    adiante = dx_ * fx_ + dz_ * fz_
    if 0 < adiante < 2500 and abs(-dx_ * fz_ + dz_ * fx_) < 1500 and abs(cy2 - jog[1]) < 3000:
        perto_sala.append((round(adiante), "ATIVA" if not (st & PL_NOHIT) else "desligada", "saltável" if st & 0x80000 else "", round(min(pt[1] for pt in pts) - jog[1]), round(max(pt[1] for pt in pts) - jog[1])))
print(f"  paredes da colisão da sala à frente (dist, estado, salto, base e topo relativos): {perto_sala[:8]}")
faces_frente = []
for (a, b, cc), n in paredes:
    cx2, cy2, cz2 = ((a[k] + b[k] + cc[k]) / 3 for k in range(3))
    dx_, dz_ = cx2 - jog[0], cz2 - jog[2]
    adiante = dx_ * fx_ + dz_ * fz_
    if 0 < adiante < 2500 and abs(-dx_ * fz_ + dz_ * fx_) < 1500 and abs(cy2 - jog[1]) < 3000:
        faces_frente.append((round(adiante), round(n[0] * fx_ + n[2] * fz_, 2), round(cy2 - jog[1])))
faces_frente.sort()
print(f"  faces visuais íngremes à frente (dist, normal·frente [negativo = de frente para o Leon], altura relativa): {faces_frente[:12]} (total {len(faces_frente)})")
print(f"  chão da colisão da sala sob o jogador: {alturas_em(jog[0], jog[2], [((a, b, cc), n) for a, b, cc, n in chao_sala])}")
if not selecionados or not criar:
    atual = json.loads(Path(__file__).with_name("triangulos_chao.json").read_text(encoding="utf-8")) if Path(__file__).with_name("triangulos_chao.json").exists() else {}
    Path(__file__).with_name("triangulos_chao.json").write_text(json.dumps({
        "meus": [[list(a), list(b), list(cc), list(n)] for (a, b, cc), n in selecionados],
        "sala": [[list(a), list(b), list(cc), list(n)] for a, b, cc, n in chao_sala],
        "paredes_visuais": [[list(a), list(b), list(cc), list(n)] for (a, b, cc), n in paredes],
        "faixa": atual.get("faixa", [0x01F00000, 0x01F00000 + 718528]),
        "faixas": atual.get("faixas", []),
    }), encoding="utf-8")
    print("triangulos_chao.json gravado (só análise, com paredes visuais)")
    c.fechar()
    sys.exit(0)

# ---- monta e registra um cSatFile por lote de triângulos
ZERO, TRAMP = AREA_DO_MESTRE + 0x240, AREA_DO_MESTRE + 0x1000
md.escrever_bloco(c, ZERO, bytes(16))


def montar(lote, parede=False, marcas=None):
    verts = {}
    vlist = []
    def vid(v):
        k = (round(v[0]), round(v[1]), round(v[2]))
        if k not in verts:
            verts[k] = len(vlist)
            vlist.append(k)
        return verts[k]
    polys = [(vid(a), vid(b), vid(cc), n) for (a, b, cc), n in lote]
    N = len(polys)
    vb = b"".join(struct.pack("<fff", *v) for v in vlist)
    nb = b"".join(struct.pack("<fff", *pl[3]) for pl in polys)
    eb = b""
    pb = b""
    for i, (i0, i1, i2, n) in enumerate(polys):
        v0, v1, v2 = vlist[i0], vlist[i1], vlist[i2]
        for pq in ((v0, v1), (v1, v2), (v2, v0)):
            eb += struct.pack("<fff", pq[1][0] - pq[0][0], pq[1][1] - pq[0][1], pq[1][2] - pq[0][2])
        st_ = JUMPOVER if (marcas is not None and marcas[i]) else 0
        pb += struct.pack("<HHHHHHHHI", i0, i1, i2, i, 3 * i, 3 * i + 1, 3 * i + 2, 0, st_)
    CEL = 4000.0
    celulas = {}
    for i, (i0, i1, i2, n) in enumerate(polys):
        pts = [vlist[i0], vlist[i1], vlist[i2]]
        for gx in range(int(min(pt[0] for pt in pts) // CEL), int(max(pt[0] for pt in pts) // CEL) + 1):
            for gz in range(int(min(pt[2] for pt in pts) // CEL), int(max(pt[2] for pt in pts) // CEL) + 1):
                celulas.setdefault((gx, gz), []).append(i)
    blocos = []
    for (gx, gz), idx in celulas.items():
        corpo = struct.pack("<ffffffHHHHI", gx * CEL - 10, 0.0, gz * CEL - 10, CEL + 20, 0.0, CEL + 20, 0 if parede else len(idx), 0, len(idx) if parede else 0, 0, 0)
        corpo += b"".join(struct.pack("<H", i) for i in idx)
        corpo += bytes((-len(corpo)) % 16)
        blocos.append(bytearray(corpo))
    for k in range(len(blocos) - 1):
        struct.pack_into("<I", blocos[k], 0x20, len(blocos[k]))
    hdr = struct.pack("<BBHHHHHHHHH", 0xFF, 0, len(vlist), N, 3 * N, 0, N, 0 if parede else N, 0, N if parede else 0, len(blocos))
    arquivo = hdr + vb + nb + eb + pb + b"".join(bytes(b) for b in blocos)
    return arquivo + bytes((-len(arquivo)) % 16), len(vlist), len(blocos)


MEM_FREE = 0x002296D8
LIMITE_HEAP = 0x01E60000  # acima disso há dados vivos (medido 30/10); o alocador não checa
ALOCS = Path(__file__).with_name("alocacoes.json")
alocadas = json.loads(ALOCS.read_text(encoding="utf-8")) if ALOCS.exists() else []


def liberar_anteriores():
    global alocadas
    for end in alocadas:
        r = c.chamar(MEM_FREE, (end,), tempo_limite_ms=3000)
        print(f"Mem_free({end:#x}): {r.estado}")
    alocadas = []
    ALOCS.write_text("[]", encoding="utf-8")


# faixas zeradas medidas 30/10: topo da RAM (960 KB) e 0xAB0000..0xDF0000 (3,3 MB); o vigia da gravidade confere se alguém escreve nelas
FAIXAS = [[0x01F00000, 0x01FF0000, 0x01F00000], [0x00AB0000, 0x00DF0000, 0x00AB0000]]  # [início, fim, próximo livre]
FAIXA_LIVRE = (FAIXAS[0][0], FAIXAS[0][1])
proximo_livre = [FAIXAS[0][0]]


def registrar(arquivo, faixa=0):
    for fx in (FAIXAS[faixa], *[f_ for i_, f_ in enumerate(FAIXAS) if i_ != faixa]):
        end = fx[2]
        fim_ = end + len(arquivo)
        if fim_ > fx[1]:
            continue
        ocupado = sum(1 for x in md.ler_bloco(c, end, len(arquivo)) if x)
        if ocupado and "--substituir" not in sys.argv:
            print(f"faixa {end:#x}..{fim_:#x} tem {ocupado} bytes não zerados; não gravo")
            return 0, 0
        fx[2] = (fim_ + 0xFFF) & ~0xFFF
        proximo_livre[0] = FAIXAS[0][2]
        break
    else:
        print(f"arquivo de {len(arquivo)} bytes não cabe em nenhuma faixa livre")
        return 0, 0
    md.escrever_bloco(c, end, arquivo)
    codigo = [0x24080000, 0x24090000, 0x08000000 | (CREATE_DATA >> 2), 0x00000000]
    c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMP + 4 * i, w)) for i, w in enumerate(codigo)))
    r = c.chamar(TRAMP, (SATMGR, end, 0, 0), tempo_limite_ms=5000)
    return end, (r.v0 if r.ok else 0)


c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
time.sleep(1.5)
pArray, nArray, size = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
for i in range(1, nArray):
    b = pArray + i * size
    h = md.ler_bloco(c, b, 0x34)
    nfl_, nsl_, nwl_ = struct.unpack_from("<HHH", h, 0x20)
    minha = (h[0] & 1) and h[0x2A] in (0, 4) and nsl_ == 0 and ((nwl_ == 0 and nfl_ > 0) or (nfl_ == 0 and nwl_ > 12))
    if ("--substituir" in sys.argv or sala_inteira) and minha:
        c.pedir(p.comando(p.Codigo.WRITE8, struct.pack("<IB", b + 0x2A, 0)), p.comando(p.Codigo.WRITE32, struct.pack("<II", b, 0)))
        print(f"peça de terreno anterior {b:#x} liberada (vaga devolvida)")

# uma peça só (até 8000 triângulos cada; a grade de blocos faz a poda espacial) — o SatMgr tem só 20 vagas
lotes = {0: selecionados}
criadas = 0
for chave, lote in sorted(lotes.items()):
    for k in range(0, len(lote), 8000):
        arquivo, nv_, nb_ = montar(lote[k:k + 8000])
        end, peca = registrar(arquivo)
        print(f"ladrilho {chave}: {len(lote[k:k+8000])} triângulos, {nb_} blocos, {len(arquivo)} bytes -> dados {end:#x} peça {peca:#x} | status {c.status().name}", flush=True)
        if not peca:
            print("alocação ou registro falhou; parando")
            break
        criadas += 1
JUMPOVER = 0x00080000
SAT_ATTR_PL_NOHIT = PL_NOHIT

def altura_chao_modelo(px, pz_):
    """Chão andável em XZ: o chão original da sala ou o meu terreno até 3 m acima dele (copas e topos ficam de fora)."""
    y1 = altura_terreno(px, pz_)
    y2 = altura_sala(px, pz_)
    if y2 is None:
        return y1
    if y1 is not None and y2 < y1 <= y2 + 3000:
        return y1
    return y2

def saltavel(centro, normal, topo=None):
    """Regra do jumpCheck do jogo: chão 3,8 m atrás da parede dentro de ±1,5 m do chão da frente."""
    nx_, nz_ = normal[0], normal[2]
    h = math.hypot(nx_, nz_)
    if h < 1e-3:
        return False
    nx_, nz_ = nx_ / h, nz_ / h
    yf = altura_chao_modelo(centro[0] + nx_ * 500, centro[2] + nz_ * 500)
    yb = altura_chao_modelo(centro[0] - nx_ * 3800, centro[2] - nz_ * 3800)
    return yf is not None and yb is not None and abs(yb - yf) <= 1500 and (topo is None or 800 <= topo - yf <= 1900)

# grade do terreno (meu) para altura_terreno — definida antes da seção de paredes da sala
CELG = 2000.0
grade_t = {}
for idx, ((a, b, cc), n) in enumerate(selecionados):
    xs_ = (a[0], b[0], cc[0]); zs_ = (a[2], b[2], cc[2])
    for gx in range(int(min(xs_) // CELG), int(max(xs_) // CELG) + 1):
        for gz in range(int(min(zs_) // CELG), int(max(zs_) // CELG) + 1):
            grade_t.setdefault((gx, gz), []).append(idx)
def altura_terreno(px, pz_):
    melhor = None
    for j in grade_t.get((int(px // CELG), int(pz_ // CELG)), ()):
        (a, b, cc), n = selecionados[j]
        def lado(p, q):
            return (q[0] - p[0]) * (pz_ - p[2]) - (q[2] - p[2]) * (px - p[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0):
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if melhor is None or y > melhor:
                melhor = y
    return melhor

# paredes ativas da sala (vértices) para saber onde a colisão já tem parede
pArray0, nArray0, size0 = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
d0 = md.ler_bloco(c, pArray0, 0x34)
vtx0, _, _, poly0 = struct.unpack_from("<IIII", d0, 0xC)
nv0, npoly0, nfloor0, nslope0, nwall0 = struct.unpack_from("<HHHHH", d0, 0x1C)
vs0 = md.ler_bloco(c, vtx0, nv0 * 12)
ps0 = md.ler_bloco(c, poly0, npoly0 * 0x14)
CELW = 1500.0
grade_w = {}
for i in range(nfloor0 + nslope0, npoly0):
    for k in struct.unpack_from("<HHH", ps0, i * 0x14):
        pt = struct.unpack_from("<fff", vs0, k * 12)
        grade_w.setdefault((int(pt[0] // CELW), int(pt[2] // CELW)), []).append(pt)
def parede_sala_perto(px, py, pz_):
    gx, gz = int(px // CELW), int(pz_ // CELW)
    for ix in (gx - 1, gx, gx + 1):
        for iz in (gz - 1, gz, gz + 1):
            for pt in grade_w.get((ix, iz), ()):
                if abs(pt[1] - py) < 2500 and math.hypot(pt[0] - px, pt[2] - pz_) < 1500:
                    return True
    return False
novas = []
for (a, b, cc), n in paredes:
    cx_, cy_, cz_ = ((a[k] + b[k] + cc[k]) / 3 for k in range(3))
    if parede_sala_perto(cx_, cy_, cz_):
        continue
    # descarta só faces claramente altas (copa): todos os vértices com chão conhecido e mais de 2,5 m acima dele
    altas = 0
    for pt in (a, b, cc):
        ch = altura_chao_modelo(pt[0], pt[2])
        if ch is not None and pt[1] > ch + 2500:
            altas += 1
    if altas == 3:
        continue
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = cc[0] - a[0], cc[1] - a[1], cc[2] - a[2]
    area = 0.5 * math.sqrt((uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2)
    maior_aresta = max(math.dist(a, b), math.dist(b, cc), math.dist(cc, a))
    if maior_aresta > 6000:  # faces gigantes (fundo, encostas do vale) empurram o jogador por metros: fora
        continue
    novas.append((area, ((a, b, cc), n)))
novas.sort(key=lambda t: -t[0])
paredes_novas = []
for _, ((a, b, cc), n) in novas[:8000]:  # dois lados por face: o de frente para o jogador empurra, o outro é ignorado
    paredes_novas.append(((a, b, cc), n))
    paredes_novas.append(((a, cc, b), (-n[0], -n[1], -n[2])))
print(f"faces íngremes do modelo sem parede na colisão da sala, ao alcance do jogador: {len(paredes_novas)} de {len(paredes)}")
limite_paredes = 0 if "--sem-paredes" in sys.argv else int(next((a[len('--paredes='):] for a in sys.argv if a.startswith('--paredes=')), 16000))
print(f"vou registrar {min(len(paredes_novas), limite_paredes)} paredes novas")
def centro_(t):
    (a, b, cc), n = t
    return tuple((a[j] + b[j] + cc[j]) / 3 for j in range(3))
marcas_base = [saltavel(centro_(t), t[1], max(t[0][0][1], t[0][1][1], t[0][2][1])) for t in paredes_novas]
CELS = 1000.0
grade_s = {}
for t, m in zip(paredes_novas, marcas_base):
    if m:
        cx_, cy_, cz_ = centro_(t)
        grade_s.setdefault((int(cx_ // CELS), int(cz_ // CELS)), []).append((cx_, cy_, cz_))
def marcada_perto(px, py, pz_, raio=800.0):
    gx, gz = int(px // CELS), int(pz_ // CELS)
    for ix in (gx - 1, gx, gx + 1):
        for iz in (gz - 1, gz, gz + 1):
            for cx_, cy_, cz_ in grade_s.get((ix, iz), ()):
                if abs(cy_ - py) < 1500 and math.hypot(cx_ - px, cz_ - pz_) < raio:
                    return True
    return False
marcas = [m or marcada_perto(*centro_(t)) for t, m in zip(paredes_novas, marcas_base)]  # a malha perto dos muros também leva a marca (o raio do ombro acerta ela primeiro)
# muros de salto explícitos: um retângulo por célula de 1,5 m com faces saltáveis (largura 1,6 m, base-20 cm ao topo)
celulas_s = {}
for t, m in zip(paredes_novas, marcas_base):
    if not m:
        continue
    (a, b, cc), n = t
    if n[1] * 0 + 1 and (n[0] ** 2 + n[2] ** 2) < 1e-6:
        continue
    cx_, cy_, cz_ = centro_(t)
    celulas_s.setdefault((int(cx_ // 1500), int(cz_ // 1500)), []).append((cx_, cy_, cz_, n, min(a[1], b[1], cc[1]), max(a[1], b[1], cc[1])))
muros = []
for itens in celulas_s.values():
    k_ = len(itens)
    cx_ = sum(i_[0] for i_ in itens) / k_; cz_ = sum(i_[2] for i_ in itens) / k_
    nx_ = sum(i_[3][0] for i_ in itens); nz_ = sum(i_[3][2] for i_ in itens)
    h_ = math.hypot(nx_, nz_)
    if h_ < 1e-3:
        continue
    nx_, nz_ = nx_ / h_, nz_ / h_
    base_ = min(i_[4] for i_ in itens); topo_ = max(i_[5] for i_ in itens)
    topo_ = min(topo_, base_ + 1900)
    tx_, tz_ = -nz_, nx_  # tangente
    p1 = (cx_ + tx_ * 800, base_ - 200, cz_ + tz_ * 800); p2 = (cx_ - tx_ * 800, base_ - 200, cz_ - tz_ * 800)
    p3 = (cx_ - tx_ * 800, topo_, cz_ - tz_ * 800); p4 = (cx_ + tx_ * 800, topo_, cz_ + tz_ * 800)
    nn_ = (nx_, 0.0, nz_); nn2 = (-nx_, 0.0, -nz_)
    muros += [((p1, p2, p3), nn_), ((p1, p3, p4), nn_), ((p1, p3, p2), nn2), ((p1, p4, p3), nn2)]
# validação de cada muro de salto com o chão do PRÓPRIO jogo (chão já registrado): frente e 3,8 m atrás dentro de ±1,5 m
P0v, P1v, CRv, PNv, TRv = (AREA_DO_MESTRE + o for o in (0x300, 0x310, 0x320, 0x330, 0x1000))
codigo_v = [0x3C080000 | (PNv >> 16), 0x35080000 | (PNv & 0xFFFF), 0x24090040, 0x240A0000, 0x08000000 | (0x1A3988 >> 2), 0]
c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRv + 4 * j, w)) for j, w in enumerate(codigo_v)))
def chao_jogo(px, py, pz_):
    md.escrever_bloco(c, P0v, struct.pack("<ffff", px, py + 2100, pz_, 1))
    md.escrever_bloco(c, P1v, struct.pack("<ffff", px, py - 100000, pz_, 1))
    r_ = c.chamar(TRv, (SATMGR, P0v, P1v, CRv), tempo_limite_ms=3000)
    return struct.unpack_from("<fff", md.ler_bloco(c, CRv, 12), 0)[1] if (r_.ok and r_.v0) else None
validos = []
for q in range(0, len(muros), 4):
    (p1_, p2_, p3_), nn_ = muros[q]
    cx_ = (p1_[0] + p2_[0]) / 2; cz_ = (p1_[2] + p2_[2]) / 2; base_ = p1_[1] + 200
    fr = chao_jogo(cx_ + nn_[0] * 500, base_, cz_ + nn_[2] * 500)
    tr = chao_jogo(cx_ - nn_[0] * 3800, base_, cz_ - nn_[2] * 3800)
    if fr is not None and tr is not None and abs(tr - fr) <= 1500 and abs(fr - base_) < 1200:
        validos += muros[q:q + 4]
print(f"paredes novas saltáveis: {sum(marcas_base)} diretas -> {len(muros) // 4} muros de salto, {len(validos) // 4} válidos pelo chão do jogo")
muros = validos
paredes_novas = muros + paredes_novas
marcas = [True] * len(muros) + marcas
for k in range(0, min(len(paredes_novas), limite_paredes), 8000):
    arquivo, nv_, nb_ = montar(paredes_novas[k:k + 8000][:limite_paredes - k], parede=True, marcas=marcas[k:k + 8000][:limite_paredes - k])
    end, peca = registrar(arquivo, faixa=1)
    print(f"paredes {k//8000}: {len(paredes_novas[k:k+8000][:limite_paredes - k])} triângulos, {nb_} blocos, {len(arquivo)} bytes -> dados {end:#x} peça {peca:#x} | status {c.status().name}", flush=True)
    if not peca:
        print("alocação ou registro falhou; parando")
        break
    criadas += 1
if paredes:
    arq, _, _ = montar(paredes[:3000], parede=True)
    Path(__file__).with_name("paredes_3000.sat").write_bytes(arq)
    arq2, _, _ = montar(selecionados[:3000])
    Path(__file__).with_name("chao_3000.sat").write_bytes(arq2)
    print("arquivos de paredes e chão (3000) gravados para análise")
print(f"{criadas} peças de terreno registradas")
r = type("R", (), {"ok": criadas > 0, "v0": criadas})()
if not r.ok:
    c.fechar()
    sys.exit(1)

# paredes da sala: desliga para o jogador só as ENTERRADAS sob o meu terreno (cercas das encostas); as demais ficam
pArray, nArray, size = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
sala = pArray
d = md.ler_bloco(c, sala, 0x34)
vtx, _, _, poly = struct.unpack_from("<IIII", d, 0xC)
nv, npoly, nfloor, nslope, nwall = struct.unpack_from("<HHHHH", d, 0x1C)
vs = md.ler_bloco(c, vtx, nv * 12)
ps = md.ler_bloco(c, poly, npoly * 0x14)
# faces visuais íngremes (troncos, pedras, barrancos): grade de vértices para saber se uma parede da colisão é visível
CELP = 1500.0
grade_p = {}
for (a, b, cc), n in paredes:
    for pt in (a, b, cc):
        grade_p.setdefault((int(pt[0] // CELP), int(pt[2] // CELP)), []).append(pt)
def face_visual_perto(px, py, pz_, raio_xz=1500.0, dy=2500.0):
    gx, gz = int(px // CELP), int(pz_ // CELP)
    for ix in (gx - 1, gx, gx + 1):
        for iz in (gz - 1, gz, gz + 1):
            for pt in grade_p.get((ix, iz), ()):
                if abs(pt[1] - py) < dy and math.hypot(pt[0] - px, pt[2] - pz_) < raio_xz:
                    return True
    return False
undo = json.loads(UNDO.read_text(encoding="utf-8"))["paredes"] if UNDO.exists() else []
originais = {e: v for e, v in undo}
desligadas = 0
religadas = 0
saltaveis_ = 0
novos_undo = []
for i in range(nfloor + nslope, npoly):
    v = struct.unpack_from("<HHH", ps, i * 0x14)
    e = poly + i * 0x14 + 0x10
    st = struct.unpack_from("<I", ps, i * 0x14 + 0x10)[0]
    original = originais.get(e, st & ~PL_NOHIT)
    pts_ = [struct.unpack_from("<fff", vs, k * 12) for k in v]
    cx_, cy_, cz_ = (sum(pt[j] for pt in pts_) / 3 for j in range(3))
    enterrada = not face_visual_perto(cx_, cy_, cz_)
    alvo = (original | PL_NOHIT) if enterrada else original
    if not enterrada:
        ni_ = struct.unpack_from("<H", ps, i * 0x14 + 6)[0]
        nrm_ = struct.unpack_from("<fff", md.ler_bloco(c, struct.unpack_from("<I", d, 0x10)[0] + ni_ * 12, 12), 0)
        if saltavel((cx_, cy_, cz_), nrm_, max(pt[1] for pt in pts_)) or marcada_perto(cx_, cy_, cz_):
            alvo |= JUMPOVER
            saltaveis_ += 1
    if alvo != st:
        c.pedir(p.comando(p.Codigo.WRITE32, struct.pack("<II", e, alvo)))
    if enterrada:
        desligadas += 1
        novos_undo.append((e, original))
    elif st & PL_NOHIT:
        religadas += 1
UNDO.write_text(json.dumps({"paredes": novos_undo}), encoding="utf-8")
paredes_sala_export = []
for i in range(nfloor + nslope, npoly):
    v = struct.unpack_from("<HHH", ps, i * 0x14)
    st = struct.unpack_from("<I", ps, i * 0x14 + 0x10)[0]
    e = poly + i * 0x14 + 0x10
    ativa = not any(e == e2 for e2, _ in novos_undo)
    paredes_sala_export.append([[list(struct.unpack_from("<fff", vs, k * 12)) for k in v], ativa])
print(f"paredes da sala: {desligadas} sem geometria visual perto desligadas para o jogador, {religadas} religadas, {nwall - desligadas} ativas, {saltaveis_} marcadas como saltáveis")
# chão completo (sala + meu) para a gravidade em Python, e a faixa gravada para o vigia de integridade
Path(__file__).with_name("triangulos_chao.json").write_text(json.dumps({
    "meus": [[list(a), list(b), list(cc), list(n)] for (a, b, cc), n in selecionados],
    "sala": [[list(a), list(b), list(cc), list(n)] for a, b, cc, n in chao_sala],
    "faixa": [FAIXAS[0][0], FAIXAS[0][2]],
    "faixas": [[fx[0], fx[2]] for fx in FAIXAS if fx[2] > fx[0]],
    "paredes_registradas": [[list(a), list(b), list(cc), list(n)] for (a, b, cc), n in paredes_novas[:limite_paredes]],
    "paredes_sala": paredes_sala_export,
    "paredes_visuais": [[list(a), list(b), list(cc), list(n)] for (a, b, cc), n in paredes],
}), encoding="utf-8")
c.fechar()
