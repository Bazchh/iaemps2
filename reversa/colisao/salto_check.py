"""Verifica a ação nativa de saltar muro sem o cliente no controle: lê as paredes marcadas com SAT_ATTR_JUMPOVER (0x80000) nas
peças vivas do SatMgr, teleporta o jogador para 50 cm à frente de cada uma (do lado da normal), vira o Leon para
o muro e chama a própria função do jogo que decide o salto (jumpCheck, 0x246538, com o jogador parado).
Uso: salto_check.py [amostras=40]. Salva/recarrega o estado 95."""

import math
import random
import struct
import sys
import time

from iaemps2.bancada import modulos as md, personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

SATMGR, JUMP_CHECK, JUMPOVER = 0x0041AF10, 0x00246538, 0x00080000
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
random.seed(3)

import json
from pathlib import Path
_dados = json.loads(Path(__file__).with_name("triangulos_chao.json").read_text(encoding="utf-8"))
_chao = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in _dados["meus"] + _dados["sala"]]
_CEL = 2000.0
_grade = {}
for _i, (_a, _b, _c, _n) in enumerate(_chao):
    for gx in range(int(min(_a[0], _b[0], _c[0]) // _CEL), int(max(_a[0], _b[0], _c[0]) // _CEL) + 1):
        for gz in range(int(min(_a[2], _b[2], _c[2]) // _CEL), int(max(_a[2], _b[2], _c[2]) // _CEL) + 1):
            _grade.setdefault((gx, gz), []).append(_i)
def chao_modelo(px, pz_):
    melhor = None
    for i in _grade.get((int(px // _CEL), int(pz_ // _CEL)), ()):
        a, b, cc, n = _chao[i]
        def lado(p_, q):
            return (q[0] - p_[0]) * (pz_ - p_[2]) - (q[2] - p_[2]) * (px - p_[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if melhor is None or y > melhor:
                melhor = y
    return melhor

c = Cliente(porta=28011, tempo_limite_s=30.0)
c.conectar()
c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
time.sleep(2.0)

pArray, nArray, size = struct.unpack_from("<III", md.ler_bloco(c, SATMGR, 12), 0)
marcadas = []
for i in range(nArray):
    b = pArray + i * size
    h = md.ler_bloco(c, b, 0x34)
    if not (h[0] & 1) or not (h[0x2A] & 4):
        continue
    vtx, nrm, _, poly = struct.unpack_from("<IIII", h, 0xC)
    nv, npoly, nfl, nsl, nwl, _, nn = struct.unpack_from("<HHHHHHH", h, 0x1C)
    if nwl == 0:
        continue
    vs = md.ler_bloco(c, vtx, nv * 12)
    ns = md.ler_bloco(c, nrm, nn * 12)
    ps = md.ler_bloco(c, poly, npoly * 0x14)
    for k in range(nfl + nsl, npoly):
        st = struct.unpack_from("<I", ps, k * 0x14 + 0x10)[0]
        if not (st & JUMPOVER):
            continue
        v = struct.unpack_from("<HHH", ps, k * 0x14)
        ni = struct.unpack_from("<H", ps, k * 0x14 + 6)[0]
        pts = [struct.unpack_from("<fff", vs, j * 12) for j in v]
        n = struct.unpack_from("<fff", ns, ni * 12)
        cen = tuple(sum(pt[j] for pt in pts) / 3 for j in range(3))
        largura = max(math.hypot(p1[0] - p2[0], p1[2] - p2[2]) for p1 in pts for p2 in pts)
        altura = max(pt[1] for pt in pts) - min(pt[1] for pt in pts)
        if not (1500 < largura < 1700 and altura >= 600):
            continue  # só os muros de salto explícitos (retângulos de 1,6 m)
        marcadas.append((i, k, cen, n, min(pt[1] for pt in pts), max(pt[1] for pt in pts)))
print(f"paredes marcadas como saltáveis nas peças vivas: {len(marcadas)}", flush=True)
random.shuffle(marcadas)


def escrever_pos(x, y, z):
    cmds = [p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + off + 4 * k, v)) for off in (0xC0, 0x130) for k, v in enumerate((x, y, z))]
    q = struct.unpack_from("<I", md.ler_bloco(c, pz.VETOR + 0x110, 4), 0)[0]
    for _ in range(40):
        if not (0x100000 < q < 0x2000000):
            break
        for off in (0x80, 0x90, 0xA0):
            cmds += [p.comando(p.Codigo.WRITE32, struct.pack("<If", q + off + 4 * k, v)) for k, v in enumerate((x, y, z))]
        q = struct.unpack_from("<I", md.ler_bloco(c, q + 0x110, 4), 0)[0]
    c.pedir(*cmds)


ok = 0
nao = 0
exemplos = []
for i, k, cen, n, ymin, ymax in marcadas[:N]:
    h = math.hypot(n[0], n[2])
    if h < 1e-3:
        continue
    nx, nz = n[0] / h, n[2] / h
    # lado de fora = onde há chão do modelo perto da base do muro
    cands = []
    for sinal in (1, -1):
        qx, qz = cen[0] + sinal * nx * 500, cen[2] + sinal * nz * 500
        ch = chao_modelo(qx, qz)
        if ch is not None and abs(ch - ymin) < 1200:
            cands.append((abs(ch - ymin), sinal, qx, qz, ch))
    if not cands:
        exemplos.append(("sem chão em nenhum lado", i, k, round(cen[0]), round(ymin), round(cen[2])))
        continue
    _, sinal, px, pz_, py = min(cands)
    nx, nz = sinal * nx, sinal * nz
    c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([95])))
    time.sleep(2.5)
    ang = math.atan2(-nx, -nz)  # frente = (sin ang, cos ang) apontando para o muro
    for _ in range(3):
        escrever_pos(px, py, pz_)
        c.pedir(p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0xD4, ang)))
        time.sleep(0.02)
    time.sleep(0.4)
    x, y, z = pz.ler_vec3(c, pz.VETOR + 0xC0)
    if math.dist((x, z), (px, pz_)) > 400:
        exemplos.append(("teleporte falhou", i, k, round(px), round(py), round(pz_), round(x), round(y), round(z)))
        continue
    r = c.chamar(JUMP_CHECK, (pz.VETOR,), tempo_limite_ms=3000)
    if r.ok and r.v0:
        ok += 1
    else:
        nao += 1
        if len(exemplos) < 12:
            # reproduz os testes do jumpCheck: linhas nos dois ombros (±300, altura 400, 600 à frente), atributo e chão 3,8 m atrás
            fx, fz = math.sin(ang), math.cos(ang)
            rx, rz = math.cos(ang), -math.sin(ang)
            from iaemps2.ponte.cliente import AREA_DO_MESTRE
            P0, P1, CR, PN, TRAMP = (AREA_DO_MESTRE + o for o in (0x300, 0x310, 0x320, 0x330, 0x1000))
            codigo = [0x3C080000 | (PN >> 16), 0x35080000 | (PN & 0xFFFF), 0x24090000, 0x240A0000, 0x08000000 | (0x1A3988 >> 2), 0]
            c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMP + 4 * j, w)) for j, w in enumerate(codigo)))
            det = []
            for lado in (300, -300):
                a0 = (x + rx * lado, y + 400, z + rz * lado); a1 = (a0[0] + fx * 600, a0[1], a0[2] + fz * 600)
                md.escrever_bloco(c, P0, struct.pack("<ffff", *a0, 1)); md.escrever_bloco(c, P1, struct.pack("<ffff", *a1, 1))
                rr = c.chamar(TRAMP, (SATMGR, P0, P1, CR), tempo_limite_ms=3000)
                det.append(f"ombro {lado:+d}: attr {rr.v0:#x}")
            # chão 3,8 m atrás do muro, como o jumpCheck: linha de (y+1500+600) até -100 m, só chão (flag 0x40)
            bx, bz = x + fx * (500 + 3800), z + fz * (500 + 3800)
            codigo2 = [0x3C080000 | (PN >> 16), 0x35080000 | (PN & 0xFFFF), 0x24090040, 0x240A0000, 0x08000000 | (0x1A3988 >> 2), 0]
            c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMP + 4 * j, w)) for j, w in enumerate(codigo2)))
            md.escrever_bloco(c, P0, struct.pack("<ffff", bx, y + 1500 + 600, bz, 1)); md.escrever_bloco(c, P1, struct.pack("<ffff", bx, y + 1500 - 100000, bz, 1))
            rr = c.chamar(TRAMP, (SATMGR, P0, P1, CR), tempo_limite_ms=3000)
            atras = struct.unpack_from("<fff", md.ler_bloco(c, CR, 12), 0)[1] if rr.v0 else None
            det.append(f"chão 3,8 m atrás: {None if atras is None else round(atras - y)} (modelo: {None if chao_modelo(bx, bz) is None else round(chao_modelo(bx, bz) - y)})")
            exemplos.append(("sem salto", i, k, round(x), round(y), round(z), "altura do muro", round(ymax - y), "base", round(ymin - y), "|", *det))
print(f"salto disponível em {ok} de {ok + nao} muros marcados testados", flush=True)
for e in exemplos:
    print("  ", e)
c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([95])))
time.sleep(2.0)
c.fechar()
