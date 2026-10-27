"""Varredura da memória do jogo pelo canal (fase 2, prova de viabilidade do módulo H).

Tira fotos da RAM do PlayStation 2 (32 MB) pelo canal oficial, em lotes de leituras de 8 bytes, e compara
fotos tiradas em instantes diferentes para achar números de ponto flutuante que mudam aos poucos: posições
de entidades que se movem, câmera, tempo. Também confere endereços conhecidos de fontes públicas.

Uso: python -m iaemps2.bancada.varrer_memoria [--slot 91] [--fotos 4] [--intervalo 1.5] [--saida pasta/varredura.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import struct
import sys
import time
from collections import Counter
from pathlib import Path

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import Cliente

MEMORIA_EE = 32 * 1024 * 1024
LEITURAS_POR_PEDIDO = 50_000  # 50k x 8 bytes = 400 KB de resposta, abaixo do limite do canal

# Fontes públicas (códigos "raw" para SLUS-21134, versão americana), a conferir contra o jogo em execução.
ENDERECOS_PUBLICOS = {
    "vida_leon": (0x0042DA76, "<H"),
    "vida_ashley": (0x0042DA7A, "<H"),
    "primeiro_save": (0x0042DA5A, "<B"),
    "costume": (0x0042DA88, "<B"),
    "personagem": (0x0042DA8A, "<B"),
}


def fotografar(c: Cliente) -> bytes:
    """A RAM inteira, em pedidos de 50 mil leituras de 8 bytes."""
    partes = []
    for inicio in range(0, MEMORIA_EE, LEITURAS_POR_PEDIDO * 8):
        comandos = [
            p.comando(p.Codigo.READ64, struct.pack("<I", endereco))
            for endereco in range(inicio, min(MEMORIA_EE, inicio + LEITURAS_POR_PEDIDO * 8), 8)
        ]
        partes.append(c.pedir(*comandos))
    return b"".join(partes)


def floats_que_mudam_aos_poucos(
    fotos: list[bytes], limite_abs: float = 1.0e5, minimo_delta: float = 1e-3
) -> list[int]:
    """Endereços (alinhados a 4) cujo float32 é finito, pequeno, e muda em toda foto por um passo pequeno."""
    n = len(fotos)
    candidatos = []
    vistas = [memoryview(f) for f in fotos]
    for endereco in range(0, MEMORIA_EE, 4):
        valores = []
        ok = True
        for v in vistas:
            (x,) = struct.unpack_from("<f", v, endereco)
            if not math.isfinite(x) or abs(x) > limite_abs:
                ok = False
                break
            valores.append(x)
        if not ok:
            continue
        deltas = [abs(valores[i + 1] - valores[i]) for i in range(n - 1)]
        if all(minimo_delta < d < limite_abs * 0.01 for d in deltas):
            candidatos.append(endereco)
    return candidatos


def agrupar(enderecos: list[int], passo_maximo: int = 16) -> list[tuple[int, int]]:
    """Blocos de endereços próximos: (início, quantidade). Um vetor x,y,z aparece como bloco de 3."""
    blocos: list[tuple[int, int]] = []
    for e in enderecos:
        if blocos and e - (blocos[-1][0] + (blocos[-1][1] - 1) * 4) <= passo_maximo:
            blocos[-1] = (blocos[-1][0], blocos[-1][1] + 1)
        else:
            blocos.append((e, 1))
    return blocos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, default=None)
    parser.add_argument("--fotos", type=int, default=4)
    parser.add_argument("--intervalo", type=float, default=1.5)
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args(argv)
    resultado: dict[str, object] = {}

    c = Cliente(porta=28011, tempo_limite_s=20.0)
    c.conectar()
    if args.slot is not None:
        c.pedir(p.comando(p.Codigo.LOAD_STATE, bytes([args.slot])))
        time.sleep(6)

    # 1. endereços públicos, lidos como estão
    publicos = {}
    for nome, (endereco, formato) in ENDERECOS_PUBLICOS.items():
        corpo = c.pedir(p.comando(p.Codigo.READ64, struct.pack("<I", endereco)))
        publicos[nome] = {
            "endereco": f"{endereco:08x}",
            "valor": struct.unpack_from(formato, corpo, 0)[0],
            "bytes": corpo.hex(),
        }
    resultado["publicos"] = publicos
    print("endereços públicos:", json.dumps(publicos))

    # 2. fotos da RAM
    tempos = []
    fotos = []
    for _ in range(args.fotos):
        t0 = time.monotonic()
        fotos.append(fotografar(c))
        tempos.append(round(time.monotonic() - t0, 2))
        time.sleep(args.intervalo)
    resultado["foto_segundos"] = tempos
    print("fotos:", len(fotos), "tempos", tempos)

    # 3. floats que mudam aos poucos, agrupados
    candidatos = floats_que_mudam_aos_poucos(fotos)
    blocos = agrupar(candidatos)
    tamanhos = Counter(q for _, q in blocos)
    resultado["candidatos"] = len(candidatos)
    resultado["blocos"] = len(blocos)
    resultado["blocos_por_tamanho"] = dict(sorted(tamanhos.items()))
    print(
        "floats que mudam aos poucos:",
        len(candidatos),
        "| blocos:",
        len(blocos),
        "| por tamanho:",
        dict(sorted(tamanhos.items())),
    )
    detalhe = []
    for inicio, quantidade in blocos:
        if quantidade < 2:
            continue
        valores = [
            [round(struct.unpack_from("<f", f, inicio + 4 * i)[0], 3) for i in range(min(quantidade, 4))]
            for f in fotos
        ]
        detalhe.append({"endereco": f"{inicio:08x}", "tamanho": quantidade, "valores_por_foto": valores})
    resultado["blocos_detalhe"] = detalhe[:200]
    for d in detalhe[:40]:
        print(d["endereco"], d["tamanho"], d["valores_por_foto"])
    # distâncias entre blocos de tamanho >= 3: estruturas iguais repetidas (lista de entidades) aparecem como passo constante
    inicios = [i for i, q in blocos if q >= 3]
    passos = Counter(b - a for a, b in itertools.pairwise(inicios) if 0 < b - a < 0x10000)
    resultado["passos_entre_blocos"] = passos.most_common(8)
    print("passos mais comuns entre blocos de 3+:", passos.most_common(8))

    c.fechar()
    if args.saida:
        args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
        print("gravado em", args.saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
