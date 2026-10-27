"""Prova medida S8-00: câmera e lista de entidades do jogo de abertura, com o cliente no controle.

Dois comandos:

  foto <rotulo>      pausa o jogo pelo canal, fotografa a memória inteira e a lista da cena do último quadro,
                     retoma, e grava tudo na pasta da prova. Rótulos esperados, na ordem do roteiro:
                     parado1, andou, parado2, virou, parado3, inimigo1, inimigo2, inimigo3
  analisar           compara as fotos: o que muda ao andar e ao virar (jogador), só ao virar (câmera),
                     e sozinho entre as fotos de inimigo (entidades); procura matrizes com linhas unitárias
                     e estruturas repetidas com passo constante; grava o resultado em JSON.

Uso: python -m iaemps2.bancada.prova_memoria foto parado1 [--pasta ~/IAEmPS2/medicoes/s8-00]
     python -m iaemps2.bancada.prova_memoria analisar [--pasta ...]
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

from iaemps2.bancada.varrer_memoria import MEMORIA_EE, fotografar
from iaemps2.ponte.cliente import Cliente

PASTA_PADRAO = Path.home() / "IAEmPS2" / "medicoes" / "s8-00"
ROTEIRO = ["parado1", "andou", "parado2", "virou", "parado3", "inimigo1", "inimigo2", "inimigo3"]


def foto(rotulo: str, pasta: Path) -> int:
    pasta.mkdir(parents=True, exist_ok=True)
    c = Cliente(porta=28011, tempo_limite_s=20.0)
    c.conectar()
    c.pausar(True)
    time.sleep(0.3)
    t0 = time.monotonic()
    memoria = fotografar(c)
    quadro, cena = c.cena_lista()
    c.pausar(False)
    c.fechar()
    (pasta / f"{rotulo}.bin").write_bytes(memoria)
    (pasta / f"{rotulo}.cena.json").write_text(
        json.dumps({"quadro": quadro, "desenhos": [a.__dict__ for a in cena]}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"foto {rotulo}: {len(memoria) // (1024 * 1024)} MB em {time.monotonic() - t0:.1f} s, {len(cena)} desenhos na cena; jogo retomado"
    )
    return 0


def _floats(b: bytes) -> memoryview:
    return memoryview(b)


def muda(a: bytes, b: bytes, endereco: int, minimo: float = 1e-3, maximo: float = 5e4) -> bool:
    (x,) = struct.unpack_from("<f", a, endereco)
    (y,) = struct.unpack_from("<f", b, endereco)
    if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > 1e6 or abs(y) > 1e6:
        return False
    return bool(minimo < abs(x - y) < maximo)


def igual(a: bytes, b: bytes, endereco: int) -> bool:
    return a[endereco : endereco + 4] == b[endereco : endereco + 4]


def plausivel(a: bytes, endereco: int, maximo: float = 1e6) -> bool:
    (x,) = struct.unpack_from("<f", a, endereco)
    return math.isfinite(x) and abs(x) < maximo


def agrupar(enderecos: list[int], passo_maximo: int = 16) -> list[tuple[int, int]]:
    blocos: list[tuple[int, int]] = []
    for e in enderecos:
        if blocos and e - (blocos[-1][0] + (blocos[-1][1] - 1) * 4) <= passo_maximo:
            blocos[-1] = (blocos[-1][0], blocos[-1][1] + 1)
        else:
            blocos.append((e, 1))
    return blocos


def linhas_unitarias(b: bytes, endereco: int) -> bool:
    """Três floats seguidos com norma 1 (linha de uma matriz de rotação)."""
    v = struct.unpack_from("<fff", b, endereco)
    if not all(math.isfinite(x) and abs(x) <= 1.0001 for x in v):
        return False
    return bool(abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 0.01)


def matriz_candidata(b: bytes, endereco: int) -> bool:
    """4x4 por linhas de 4 floats: três linhas unitárias nos 3 primeiros e a quarta com uma posição."""
    return all(linhas_unitarias(b, endereco + 16 * i) for i in range(3)) and plausivel(b, endereco + 48)


def analisar(pasta: Path) -> int:
    fotos: dict[str, bytes] = {}
    cenas: dict[str, list[dict[str, object]]] = {}
    for rotulo in ROTEIRO:
        arq = pasta / f"{rotulo}.bin"
        if arq.exists():
            fotos[rotulo] = arq.read_bytes()
            cenas[rotulo] = json.loads((pasta / f"{rotulo}.cena.json").read_text(encoding="utf-8"))[
                "desenhos"
            ]
    print("fotos:", list(fotos))
    resultado: dict[str, object] = {"fotos": list(fotos)}
    faltam = [r for r in ("parado1", "andou", "parado2", "virou", "parado3") if r not in fotos]
    if faltam:
        print("faltam fotos do roteiro:", faltam)
        return 2
    p1, an, p2, vi, p3 = (fotos[r] for r in ("parado1", "andou", "parado2", "virou", "parado3"))

    # classes de endereço (floats alinhados a 4)
    jogador, camera = [], []
    for e in range(0, MEMORIA_EE - 16, 4):
        if not plausivel(p1, e):
            continue
        # ruído: muda entre duas paradas sem ninguém fazer nada -> fora
        if muda(p1, p2, e, minimo=1e-6) and muda(p2, p3, e, minimo=1e-6) and not muda(an, p2, e):
            continue
        andou = muda(p1, an, e) and muda(an, p2, e, minimo=0.0) is not None and muda(p1, p2, e)
        virou = muda(p2, vi, e) and muda(p2, p3, e)
        if andou and virou:
            jogador.append(e)
        elif virou and not muda(p1, p2, e):
            camera.append(e)
    print("muda ao andar e ao virar (jogador e câmera que segue):", len(jogador))
    print("muda só ao virar (câmera):", len(camera))
    bj, bc = agrupar(jogador), agrupar(camera)
    resultado["jogador"] = {
        "enderecos": len(jogador),
        "blocos": len(bj),
        "por_tamanho": dict(sorted(Counter(q for _, q in bj).items())),
    }
    resultado["camera"] = {
        "enderecos": len(camera),
        "blocos": len(bc),
        "por_tamanho": dict(sorted(Counter(q for _, q in bc).items())),
    }

    # matrizes candidatas a câmera: entre os blocos que mudam só ao virar
    matrizes = []
    for inicio, quantidade in bc:
        for e in range(inicio - 48, inicio + quantidade * 4, 4):
            if (
                e >= 0
                and e + 64 <= MEMORIA_EE
                and matriz_candidata(p3, e)
                and matriz_candidata(p1, e)
                and not igual(p2, vi, e)
            ):
                matrizes.append(e)
    matrizes = sorted(set(matrizes))
    resultado["matrizes_camera"] = [
        {
            "endereco": f"{e:08x}",
            "parado1": [round(x, 3) for x in struct.unpack_from("<16f", p1, e)],
            "virou": [round(x, 3) for x in struct.unpack_from("<16f", vi, e)],
        }
        for e in matrizes[:12]
    ]
    print("matrizes 4x4 que mudam só ao virar:", len(matrizes), [f"{e:08x}" for e in matrizes[:12]])

    # vetores de posição do jogador: blocos de 3 ou 4 que mudam ao andar e ao virar, com valores grandes (unidades do jogo)
    posicoes = []
    for inicio, quantidade in bj:
        if quantidade in (3, 4):
            v1 = struct.unpack_from("<fff", p1, inicio)
            v2 = struct.unpack_from("<fff", p2, inicio)
            if all(abs(x) < 1e5 for x in v1) and max(abs(a - b) for a, b in zip(v1, v2, strict=False)) > 1.0:
                posicoes.append(
                    {
                        "endereco": f"{inicio:08x}",
                        "parado1": [round(x, 2) for x in v1],
                        "parado2": [round(x, 2) for x in v2],
                        "parado3": [round(x, 2) for x in struct.unpack_from("<fff", p3, inicio)],
                    }
                )
    resultado["posicoes_jogador"] = posicoes[:40]
    print("vetores candidatos a posição do jogador:", len(posicoes))
    for item in posicoes[:12]:
        print("  ", item)

    # entidades: entre as fotos de inimigo, o que anda sozinho (jogador parado): blocos de 3 com passo constante
    inimigos = [fotos[r] for r in ("inimigo1", "inimigo2", "inimigo3") if r in fotos]
    if len(inimigos) >= 2:
        anda = [
            e
            for e in range(0, MEMORIA_EE - 16, 4)
            if plausivel(inimigos[0], e)
            and all(muda(a, b, e, minimo=0.5, maximo=2e3) for a, b in itertools.pairwise(inimigos))
            and not muda(p1, p2, e, minimo=1e-6)
        ]
        blocos = [b for b in agrupar(anda) if b[1] >= 3]
        inicios = [i for i, _ in blocos]
        passos = Counter(b - a for a, b in itertools.pairwise(inicios) if 0 < b - a < 0x8000)
        entidades: dict[str, object] = {
            "enderecos": len(anda),
            "blocos_3+": len(blocos),
            "passos_mais_comuns": passos.most_common(8),
            "exemplos": [
                {
                    "endereco": f"{i:08x}",
                    "tamanho": q,
                    "valores": [[round(x, 2) for x in struct.unpack_from("<fff", f, i)] for f in inimigos],
                }
                for i, q in blocos[:30]
            ],
        }
        print(
            "anda sozinho entre fotos de inimigo:",
            len(anda),
            "| blocos 3+:",
            len(blocos),
            "| passos:",
            passos.most_common(6),
        )
        resultado["entidades"] = entidades
        for ex in list(entidades["exemplos"])[:12]:  # type: ignore[call-overload]
            print("  ", ex)
    else:
        print("sem fotos de inimigo suficientes para a lista de entidades")

    (pasta / "analise.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print("gravado em", pasta / "analise.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("comando", choices=["foto", "analisar"])
    parser.add_argument("rotulo", nargs="?", default=None)
    parser.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    args = parser.parse_args(argv)
    if args.comando == "foto":
        if not args.rotulo:
            print("foto precisa de um rótulo:", ", ".join(ROTEIRO))
            return 2
        return foto(args.rotulo, args.pasta)
    return analisar(args.pasta)


if __name__ == "__main__":
    sys.exit(main())
