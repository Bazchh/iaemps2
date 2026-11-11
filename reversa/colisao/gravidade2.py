"""Gravidade do mestre sem chamadas remotas: o chão é calculado em Python a partir de triangulos_chao.json (chão da
sala + terreno gerado), só com leitura e escrita de memória. Se o jogador ficar mais de 1 m acima do chão por 3
amostras seguidas, a altura do chão é escrita na posição dele. A cada 5 s confere a soma do arquivo do terreno na
memória e avisa se alguém escreveu em cima. Uso: gravidade2.py [minutos=30] [hz=5]."""

import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

from iaemps2.bancada import modulos as md, personagens as pz
from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

minutos = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
hz = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
dados = json.loads(Path(__file__).with_name("triangulos_chao.json").read_text(encoding="utf-8"))
tris = [(tuple(a), tuple(b), tuple(cc), tuple(n)) for a, b, cc, n in dados["meus"] + dados["sala"]]
faixas = dados.get("faixas", [dados["faixa"]])
CEL = 2000.0
grade = {}
for i, (a, b, cc, n) in enumerate(tris):
    xs = (a[0], b[0], cc[0]); zs = (a[2], b[2], cc[2])
    for gx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
        for gz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
            grade.setdefault((gx, gz), []).append(i)


def chao_sob(px, py, pz_):
    """Maior altura de chão abaixo de py + 600 (como o getFloor do jogo), ou None."""
    melhor = None
    for i in grade.get((int(px // CEL), int(pz_ // CEL)), ()):
        a, b, cc, n = tris[i]
        def lado(p_, q):
            return (q[0] - p_[0]) * (pz_ - p_[2]) - (q[2] - p_[2]) * (px - p_[0])
        s1, s2, s3 = lado(a, b), lado(b, cc), lado(cc, a)
        if ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)) and abs(n[1]) > 1e-6:
            y = a[1] - (n[0] * (px - a[0]) + n[2] * (pz_ - a[2])) / n[1]
            if y <= py + 600 and (melhor is None or y > melhor):
                melhor = y
    return melhor


c = Cliente(porta=28011, tempo_limite_s=30.0)
c.conectar()
def somas():
    return [hashlib.md5(md.ler_bloco(c, a, b - a)).hexdigest() for a, b in faixas]
soma0 = somas()
print(f"gravidade (Python) por {minutos:.0f} min a {hz:.0f} Hz; {len(tris)} triângulos; vigia das faixas {[(hex(a), hex(b)) for a, b in faixas]}", flush=True)
seguidas = 0
correcoes = 0
ultima_conferencia = time.time()
fim = time.time() + minutos * 60
while time.time() < fim:
    try:
        x, y, z = pz.ler_vec3(c, pz.VETOR + 0xC0)
        chao = chao_sob(x, y, z)
        if chao is not None and 1000 < y - chao < 30000:
            seguidas += 1
            if seguidas >= 3:
                c.pedir(p.comando(p.Codigo.WRITE32, struct.pack("<If", pz.VETOR + 0xC4, chao)))
                correcoes += 1
                print(f"{time.strftime('%H:%M:%S')} jogador a {y - chao:.0f} mm do chão em ({x:.0f}, {z:.0f}): posto no chão", flush=True)
                seguidas = 0
        else:
            seguidas = 0
        if time.time() - ultima_conferencia > 5.0:
            ultima_conferencia = time.time()
            soma = somas()
            if soma != soma0:
                print(f"{time.strftime('%H:%M:%S')} ATENÇÃO: o arquivo do terreno na memória foi alterado por alguém", flush=True)
                soma0 = soma
    except Exception as e:  # noqa: BLE001
        print("erro:", e, flush=True)
        time.sleep(2.0)
    time.sleep(1.0 / hz)
print(f"gravidade desligada; {correcoes} correções", flush=True)
c.fechar()
