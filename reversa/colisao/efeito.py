"""Dispara efeitos de partícula numa posição à frente do jogador, como a caixa faz ao quebrar:
EstSet(0, -1, &pos, &rot, est, kind, flags, 0). O "est" é o conjunto (tabela +0x7400 do gerente de efeitos) e o
"kind" é o efeito dentro dele. Uso: efeito.py <est> <kind>[-<kind_fim>] [distancia_m=2.0] [intervalo_s=2.0]
[flags=1]. Com faixa de kinds, dispara um por vez e imprime qual está na tela. Salva o estado no slot 95 antes."""

import struct
import sys
import time

from iaemps2.bancada import modulos as md, personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente

EST_SET = 0x001FAF80
est = int(sys.argv[1], 0)
faixa = sys.argv[2].split("-")
kinds = range(int(faixa[0], 0), int(faixa[-1], 0) + 1)
dist = float(sys.argv[3]) * 1000.0 if len(sys.argv) > 3 else 2000.0
intervalo = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
flags = int(sys.argv[5], 0) if len(sys.argv) > 5 else 1
repeticoes = int(sys.argv[6]) if len(sys.argv) > 6 else 1
POS, ROT, TRAMP = AREA_DO_MESTRE + 0x100, AREA_DO_MESTRE + 0x110, AREA_DO_MESTRE + 0x1000

c = Cliente(porta=28011, tempo_limite_s=30.0)
c.conectar()
c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
time.sleep(1.5)
pos = pz.a_frente(pz.ler_vec3(c, pz.VETOR + 0xC0), pz.ler_vec3(c, pz.CAMERA_OLHO), pz.ler_vec3(c, pz.CAMERA_ALVO), dist)
md.escrever_bloco(c, POS, struct.pack("<ffff", *pos, 1.0))
md.escrever_bloco(c, ROT, bytes(16))
print(f"posição {tuple(round(v) for v in pos)}; est {est:#x}")
for kind in kinds:
    # a0 = 0, a1 = -1 (da chamada), a2 = &pos, a3 = &rot; t0 = est, t1 = kind, t2 = flags, t3 = 0; j EstSet
    codigo = [
        0x24080000 | (est & 0xFFFF),
        0x24090000 | (kind & 0xFFFF),
        0x240A0000 | (flags & 0xFFFF),
        0x240B0000,
        0x08000000 | (EST_SET >> 2),
        0x00000000,
    ]
    c.pedir(*(p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMP + 4 * i, w)) for i, w in enumerate(codigo)))
    for _ in range(repeticoes):
        r = c.chamar(TRAMP, (0, 0xFFFFFFFF, POS, ROT), tempo_limite_ms=5000)
        if repeticoes > 1 and r.estado == "ok":
            time.sleep(0.5)
    print(f"  kind {kind:#04x}: {r.estado} {r.duracao_ms} ms | status {c.status().name}", flush=True)
    if r.estado != "ok":
        break
    if len(kinds) > 1:
        time.sleep(intervalo)
c.fechar()
