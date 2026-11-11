"""Andarilho: verificação automática da colisão. Salva o estado no slot 95, teleporta o jogador para pontos
espalhados pelo chão gerado, anda em 4 direções escrevendo a posição a cada 10 cm (o jogo aplica parede e chão
a cada quadro), e classifica o que aconteceu: barrado, subiu/desceu, flutuando (y acima do chão do modelo),
afundado (y abaixo), atravessou face visual íngreme (bug de parede). No fim recarrega o estado 95.
Uso: andarilho.py [pontos=60] [passos=30] [direcoes=4]"""

import json
import math
import random
import struct
import sys
import time
from pathlib import Path

from iaemps2.bancada import modulos as md, personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

N_PONTOS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
N_PASSOS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
N_DIR = int(sys.argv[3]) if len(sys.argv) > 3 else 4
PASSO = 100.0
random.seed(7)

dados = json.loads(Path(__file__).with_name("triangulos_chao.json").read_text(encoding="utf-8"))
chao = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in dados["meus"] + dados["sala"]]
paredes = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in dados.get("paredes_visuais", [])]
CEL = 2000.0


def grade_de(lista):
    g = {}
    for i, (a, b, cc, n) in enumerate(lista):
        xs = (a[0], b[0], cc[0]); zs = (a[2], b[2], cc[2])
        for gx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for gz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                g.setdefault((gx, gz), []).append(i)
    return g


gc, gp = grade_de(chao), grade_de(paredes)


def chao_em(px, py, pz_):
    melhor = None
    for i in gc.get((int(px // CEL), int(pz_ // CEL)), ()):
        a, b, cc, n = chao[i]
        def lado(p_, q):
            return (q[0] - p_[0]) * (pz_ - p_[2]) - (q[2] - p_[2]) * (px - p_[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if y <= py + 600 and (melhor is None or y > melhor):
                melhor = y
    return melhor


def cruza_parede(p0, p1):
    """Segmento p0->p1 (à altura do peito: +900) atravessa alguma face visual íngreme?"""
    a0 = (p0[0], p0[1] + 900, p0[2]); a1 = (p1[0], p1[1] + 900, p1[2])
    d = (a1[0] - a0[0], a1[1] - a0[1], a1[2] - a0[2])
    cels = {(int(a0[0] // CEL), int(a0[2] // CEL)), (int(a1[0] // CEL), int(a1[2] // CEL))}
    for cel in cels:
        for i in gp.get(cel, ()):
            a, b, cc, n = paredes[i]
            den = n[0] * d[0] + n[1] * d[1] + n[2] * d[2]
            if abs(den) < 1e-9:
                continue
            t = (n[0] * (a[0] - a0[0]) + n[1] * (a[1] - a0[1]) + n[2] * (a[2] - a0[2])) / den
            if t < 0 or t > 1:
                continue
            q = (a0[0] + d[0] * t, a0[1] + d[1] * t, a0[2] + d[2] * t)
            # dentro do triângulo (coordenadas baricêntricas)
            v0 = (cc[0] - a[0], cc[1] - a[1], cc[2] - a[2]); v1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2]); v2 = (q[0] - a[0], q[1] - a[1], q[2] - a[2])
            d00 = sum(x * y for x, y in zip(v0, v0)); d01 = sum(x * y for x, y in zip(v0, v1)); d02 = sum(x * y for x, y in zip(v0, v2))
            d11 = sum(x * y for x, y in zip(v1, v1)); d12 = sum(x * y for x, y in zip(v1, v2))
            den2 = d00 * d11 - d01 * d01
            if abs(den2) < 1e-9:
                continue
            u = (d11 * d02 - d01 * d12) / den2; v = (d00 * d12 - d01 * d02) / den2
            if u >= -0.02 and v >= -0.02 and u + v <= 1.02:
                # só conta se a face cobre a faixa da esfera do jogador (y+473..y+1273); muretas baixas são passáveis
                topo = max(a[1], b[1], cc[1]); base = min(a[1], b[1], cc[1])
                if topo >= p0[1] + 700 and base <= p0[1] + 1100:
                    return True
    return False


c = Cliente(porta=28011, tempo_limite_s=30.0)
c.conectar()
c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
time.sleep(2.0)
origem = pz.ler_vec3(c, pz.VETOR + 0xC0)


def escrever_pos(x, y, z, com_old=False):
    cmds = [p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0xC0, x)),
            p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0xC4, y)),
            p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0xC8, z))]
    if com_old:  # a varredura de parede vai da posição de mundo ANTERIOR das partes até a nova: no teleporte, igualar tudo
        cmds += [p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0x130 + 4 * k, v)) for k, v in enumerate((x, y, z))]
        q = struct.unpack_from("<I", md.ler_bloco(c, pz.VETOR + 0x110, 4), 0)[0]
        for _ in range(40):
            if not (0x100000 < q < 0x2000000):
                break
            for off in (0x80, 0x90, 0xA0):
                cmds += [p.comando(p.Codigo.WRITE32, struct.pack("<If", q + off + 4 * k, v)) for k, v in enumerate((x, y, z))]
            q = struct.unpack_from("<I", md.ler_bloco(c, q + 0x110, 4), 0)[0]
    c.pedir(*cmds)


# pontos de amostra: centros de triângulos meus, espalhados numa grade de 8 m
# pontos no chão original da sala e no meu terreno até 3 m acima do chão original (evita copas e topos de árvore)
sala_tris = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in dados["sala"]]
gs = grade_de(sala_tris)
def chao_sala_em(px, pz_):
    melhor = None
    for i in gs.get((int(px // CEL), int(pz_ // CEL)), ()):
        a, b, cc, n = sala_tris[i]
        def lado(p_, q):
            return (q[0] - p_[0]) * (pz_ - p_[2]) - (q[2] - p_[2]) * (px - p_[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if melhor is None or y > melhor:
                melhor = y
    return melhor
meus = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in dados["meus"]]
celulas = {}
for a, b, cc, n in sala_tris + meus:
    cx, cy, cz = ((a[k] + b[k] + cc[k]) / 3 for k in range(3))
    if n[1] < 0.9:
        continue
    ref = chao_sala_em(cx, cz)
    if ref is None or cy > ref + 3000:
        continue
    celulas.setdefault((int(cx // 8000), int(cz // 8000)), []).append((cx, cy, cz))
pontos = [random.choice(v) for v in celulas.values()]
random.shuffle(pontos)
pontos = pontos[:N_PONTOS]
print(f"{len(pontos)} pontos de partida; {N_PASSOS} passos de {PASSO:.0f} mm em {N_DIR} direções", flush=True)

contagem = {"teleporte_rejeitado": 0, "barrado": 0, "atravessou_face": 0, "flutuando": 0, "afundado": 0, "sem_chao_modelo": 0, "livre": 0}
achados = []
for pi, (sx, sy, sz) in enumerate(pontos):
    c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([95])))  # estado limpo a cada ponto (eventos, quedas, animações presas)
    time.sleep(2.5)
    for di in range(N_DIR):
        ang = 2 * math.pi * di / N_DIR + 0.3
        dx, dz = math.sin(ang), math.cos(ang)
        for _ in range(3):
            escrever_pos(sx, sy + 20, sz, com_old=True)
            time.sleep(0.02)
        time.sleep(0.25)
        x, y, z = pz.ler_vec3(c, pz.VETOR + 0xC0)
        if math.dist((x, z), (sx, sz)) > 300:
            contagem["teleporte_rejeitado"] += 1
            achados.append(("teleporte_rejeitado", round(sx), round(sy), round(sz), round(math.dist((x, z), (sx, sz))), round(x), round(y), round(z)))
            break  # o jogo rejeitou o ponto (empurrado para longe)
        parado = 0
        for k in range(N_PASSOS):
            nx, nz = x + dx * PASSO, z + dz * PASSO
            escrever_pos(nx, y, nz)
            time.sleep(0.04)
            x2, y2, z2 = pz.ler_vec3(c, pz.VETOR + 0xC0)
            avancou = (x2 - x) * dx + (z2 - z) * dz
            if cruza_parede((x, y, z), (x2, y2, z2)) and avancou > 40:
                contagem["atravessou_face"] += 1
                achados.append(("atravessou_face", round(x2), round(y2), round(z2)))
            if avancou < 40:
                parado += 1
                if parado >= 3:
                    contagem["barrado"] += 1
                    break
            else:
                parado = 0
            cm = chao_em(x2, y2, z2)
            if cm is None:
                contagem["sem_chao_modelo"] += 1
            elif y2 - cm > 1000:
                contagem["flutuando"] += 1
                achados.append(("flutuando", round(x2), round(y2), round(z2), round(y2 - cm)))
            elif cm - y2 > 600:
                contagem["afundado"] += 1
                achados.append(("afundado", round(x2), round(y2), round(z2), round(cm - y2)))
            else:
                contagem["livre"] += 1
            x, y, z = x2, y2, z2
    if (pi + 1) % 10 == 0:
        print(f"  {pi + 1}/{len(pontos)} pontos: {contagem}", flush=True)

print("resumo:", contagem)
piores = {}
for a in achados:
    piores.setdefault(a[0], []).append(a[1:])
for tipo, lista in piores.items():
    print(f"  {tipo}: {len(lista)} ocorrências; exemplos: {lista[:6]}")
Path(__file__).with_name("andarilho_resultado.json").write_text(json.dumps({"contagem": contagem, "achados": achados}), encoding="utf-8")
c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([95])))
time.sleep(2.0)
print("estado 95 recarregado; jogador de volta em", tuple(round(v) for v in pz.ler_vec3(c, pz.VETOR + 0xC0)), "(origem", tuple(round(v) for v in origem), ")")
c.fechar()
