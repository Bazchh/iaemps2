"""Dá chão a um morro à frente do jogador e desliga as paredes invisíveis dele para o jogador.

1. Cria uma laje de colisão (cSatMgr::create com flag 0x200 = createFloorSat) de 4 cantos: a borda de perto nos pés
   do jogador, a borda de longe a <comprimento> m à frente e <subida> m mais alta, com <largura> m de largura.
2. Nos polígonos de PAREDE da peça de colisão da sala (grupo C), marca SAT_ATTR_PL_NOHIT (0x00400000) nos que caem
   dentro da caixa XZ da laje, para o teste de parede do jogador (SAT_TYPE_PL) pular esses polígonos. Os valores
   originais vão para morro_undo.json para desfazer.

Uso: morro.py [comprimento_m=12] [subida_m=6] [largura_m=4] [--sem-paredes] [--desfazer]
Salva o estado no slot 95 antes.
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

SATMGR = 0x0041AF10  # cSatMgr SatMgr (personagens); 0x41AF30 é o EatMgr (balas e objetos)
CREATE_QUAD = 0x001A33A8  # cSatMgr::create(this, pPos, pAng, pVec, f12 height, attr, flag)
PL_NOHIT = 0x00400000
UNDO = Path(__file__).with_name("morro_undo.json")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
comprimento = float(args[0]) * 1000.0 if len(args) > 0 else 12000.0
subida = float(args[1]) * 1000.0 if len(args) > 1 else 6000.0
largura = float(args[2]) * 1000.0 if len(args) > 2 else 4000.0
sem_paredes = "--sem-paredes" in sys.argv
desfazer = "--desfazer" in sys.argv

c = Cliente(porta=28011, tempo_limite_s=30.0)
c.conectar()


def peca_da_sala():
    pArray, nArray, size = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
    melhor = None
    for i in range(nArray):
        b = pArray + i * size
        d = md.ler_bloco(c, b, 0x34)
        if not (d[0] & 1):
            continue
        npoly = struct.unpack_from("<H", d, 0x1E)[0]
        if melhor is None or npoly > melhor[1]:
            melhor = (b, npoly)
    return melhor[0]


if desfazer:
    undo = json.loads(UNDO.read_text(encoding="utf-8"))
    for end, valor in undo["paredes"]:
        c.pedir(p.comando(p.Codigo.WRITE32, struct.pack("<II", end, valor)))
    print(f"{len(undo['paredes'])} paredes restauradas (a laje criada fica até a sala recarregar)")
    c.fechar()
    sys.exit(0)

c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
time.sleep(1.5)

pos = pz.ler_vec3(c, pz.VETOR + 0xC0)
olho, alvo = pz.ler_vec3(c, pz.CAMERA_OLHO), pz.ler_vec3(c, pz.CAMERA_ALVO)
dx, dz = alvo[0] - olho[0], alvo[2] - olho[2]
n = math.hypot(dx, dz) or 1.0
fx, fz = dx / n, dz / n  # direção de frente no plano
lx, lz = -fz, fx  # lateral
meia = largura / 2.0
px, py, pz_ = pos
# cantos: 0 perto-esquerda, 1 perto-direita, 2 longe-direita, 3 longe-esquerda (ordem de createFloorSat: 0,2,1 / 2,0,3)
cantos = [
    (px - fx * 500 + lx * meia, py - 50.0, pz_ - fz * 500 + lz * meia),
    (px - fx * 500 - lx * meia, py - 50.0, pz_ - fz * 500 - lz * meia),
    (px + fx * comprimento - lx * meia, py + subida, pz_ + fz * comprimento - lz * meia),
    (px + fx * comprimento + lx * meia, py + subida, pz_ + fz * comprimento + lz * meia),
]
print("jogador em", tuple(round(v) for v in pos), "| frente", (round(fx, 2), round(fz, 2)))
print("laje:", [tuple(round(v) for v in cc) for cc in cantos])

QUAD, ZERO, TRAMP = AREA_DO_MESTRE + 0x200, AREA_DO_MESTRE + 0x240, AREA_DO_MESTRE + 0x1000
md.escrever_bloco(c, QUAD, b"".join(struct.pack("<ffff", *cc, 1.0) for cc in cantos))  # Vec do PS2 tem 16 bytes
md.escrever_bloco(c, ZERO, bytes(16))
# a0 = SatMgr, a1 = &pos(0), a2 = &ang(0), a3 = &quad; t0 = attr 0, t1 = flag 0x200; f12 = 0.0
codigo = [
    0x24080000,  # addiu t0, zero, 0
    0x24090200,  # addiu t1, zero, 0x200
    0x44806000,  # mtc1 zero, f12
    0x08000000 | (CREATE_QUAD >> 2),  # j create
    0x00000000,
]
c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMP + 4 * i, w)) for i, w in enumerate(codigo)))
r = c.chamar(TRAMP, (SATMGR, ZERO, ZERO, QUAD), tempo_limite_ms=5000)
print(f"create laje: {r.estado} v0={r.v0:#x} {r.duracao_ms} ms | status {c.status().name}")

if sem_paredes or not r.ok or not r.v0:
    c.fechar()
    sys.exit(0)

# paredes da sala dentro da caixa XZ da laje (com folga de 1 m)
xs = [cc[0] for cc in cantos]
zs = [cc[2] for cc in cantos]
x0, x1, z0, z1 = min(xs) - 1000, max(xs) + 1000, min(zs) - 1000, max(zs) + 1000
sala = peca_da_sala()
d = md.ler_bloco(c, sala, 0x34)
vtx, _, _, poly = struct.unpack_from("<IIII", d, 0xC)
nv, npoly, nfloor, nslope, nwall = struct.unpack_from("<HHHHH", d, 0x1C)
vs = md.ler_bloco(c, vtx, nv * 12)
ps = md.ler_bloco(c, poly, npoly * 0x14)
alterados = []
for i in range(nfloor + nslope, npoly):
    v = struct.unpack_from("<HHH", ps, i * 0x14)
    st = struct.unpack_from("<I", ps, i * 0x14 + 0x10)[0]
    dentro = 0
    for k in v:
        x, _, z = struct.unpack_from("<fff", vs, k * 12)
        if x0 <= x <= x1 and z0 <= z <= z1:
            dentro += 1
    if dentro >= 1 and not (st & PL_NOHIT):
        end = poly + i * 0x14 + 0x10
        alterados.append((end, st))
        c.pedir(p.comando(p.Codigo.WRITE32, struct.pack("<II", end, st | PL_NOHIT)))
anteriores = json.loads(UNDO.read_text(encoding="utf-8"))["paredes"] if UNDO.exists() else []
UNDO.write_text(json.dumps({"paredes": anteriores + alterados}), encoding="utf-8")
print(f"peça da sala {sala:#x}: {npoly} polígonos ({nfloor} chão, {nslope} rampa, {nwall} parede); {len(alterados)} paredes desligadas para o jogador")
c.fechar()
