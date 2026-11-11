"""Módulos de personagem do jogo de abertura (SLUS-21134): carregar um módulo na memória sem passar pelo disco.

O que o código do jogo diz (lido em 29/10, card S8-02): cada tipo de personagem vive num módulo de dois arquivos
do `BIO4DAT.AFS` da ISO, ``<nome>.dat`` (modelos e dados, entra na memória como está) e ``<nome>.rel`` (código
realocável, cabeçalho "SNR2"). A tabela de arquivos por tipo fica no executável (0x00328458, 8 bytes por tipo:
índice do .dat, índice do .rel, alternativo, usado). O jogo mantém só quatro módulos carregados (tabela em
0x00455E50, entradas de 0x98 bytes: +0x80 tipo, +0x82 flags, +0x84 .dat, +0x88 .rel, +0x8C e +0x90 tamanhos
arredondados a 0x800, +0x94 função de inicialização) e carrega do disco só na tela de loading, dormindo pelo
escalonador, o que não dá para forçar no meio do jogo. Aqui o mestre faz o trabalho do carregador: lê os dois
arquivos da ISO, escreve-os numa área livre da memória (0x01E00000 em diante, sempre vazia nas fotos), preenche a
entrada da tabela e pede ao jogo, pela chamada remota, que realoque e inicialize o módulo (``FUN_00262bb0``, que
não dorme). A partir daí ``EmSetEvent`` cria o personagem na hora. A memória dos dois arquivos vem do alocador do
próprio jogo (``mem_alloc``), e a entrada fica marcada como o carregador marca as dele, para ``InitModule``
liberar; escrever num endereço fixo sobrescreveria um módulo vivo (aconteceu em 29/10 e travou o jogo).

Cuidados: nunca ``liberar`` um tipo com que o jogador está interagindo (destruir a lancha com o jogador em cima
travou o jogo); salvar o estado antes.

Comandos:
  listar [--iso ISO]          as quatro entradas da tabela de módulos e os arquivos de cada tipo pedido.
  liberar <tipo>              destrói os personagens do tipo (SceDestroyEm) e reinicializa a entrada dele.
  carregar <tipo> [--iso ISO] carrega o módulo do tipo numa entrada livre e inicializa pelo jogo.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from iaemps2.ponte import protocolo as p
from iaemps2.ponte.cliente import AREA_DO_MESTRE, Cliente

ISO_PADRAO = Path(r"C:\Users\mikael\Jogos\PS2\Resident Evil 4 (USA).iso")
AFS_SETOR = 446273  # BIO4DAT.AFS na ISO (setor de 2048 bytes)
TABELA_ARQUIVOS = {0: 0x00328458, 1: 0x00328458, 2: 0x003286D8, 3: 0x00328958, 4: 0x00328BD8, 5: 0x00328958}
TABELA_MODULOS = 0x00455E50
ENTRADAS = 4
TAMANHO_ENTRADA = 0x98
MEM_ALLOC = 0x00229338  # mem_alloc(tamanho, nome, 0, 1, 0xd, alinhamento): 6 argumentos, por isso o trampolim
TRAMPOLIM_ALOCAR = AREA_DO_MESTRE + 0x1000  # página do mestre: a0 = tamanho; os outros 5 argumentos fixos
CODIGO_ALOCAR = [
    0x2408000D,  # addiu t0, zero, 0xd      (5º argumento)
    0x24090080,  # addiu t1, zero, 0x80     (6º: alinhamento)
    0x00002821,  # addu a1, zero, zero      (nome)
    0x00003021,  # addu a2, zero, zero
    0x24070001,  # addiu a3, zero, 1
    0x0808A4CE,  # j mem_alloc              (volta direto ao trampolim da chamada, ra intacto)
    0x00000000,  # nop
]
FLAGS_ALOCADO = 0x4 | 0x1  # como o carregador do jogo marca .dat e .rel alocados: InitModule libera os dois
REGISTRAR_MODULO = 0x00262BB0  # realoca o .rel, chama a inicialização do módulo e grava +0x94
SEARCH_EM_MODULE = 0x00262D68
INIT_MODULE = 0x00262570
SCE_DESTROY_EM = 0x002710C8
PERSONAGEM = 0x0042DA8A  # pG + 0x7EEA: modo de personagem (escolhe a tabela de arquivos)
ESCRITAS_POR_PEDIDO = 40_000


@dataclass(frozen=True)
class ArquivoAfs:
    indice: int
    nome: str
    deslocamento: int
    tamanho: int


@dataclass(frozen=True)
class EntradaModulo:
    indice: int
    tipo: int
    flags: int
    dat: int
    rel: int
    tamanho_dat: int
    tamanho_rel: int
    inicializacao: int

    @property
    def livre(self) -> bool:
        return self.tipo == 0 and self.dat == 0


def arredondar(n: int, a: int = 0x800) -> int:
    return (n + a - 1) & ~(a - 1)


class Afs:
    """Leitor do BIO4DAT.AFS dentro da ISO: cabeçalho "AFS", n, pares (deslocamento, tamanho), nomes de 48 bytes."""

    def __init__(self, iso: Path, setor: int = AFS_SETOR) -> None:
        self.iso = iso
        self.base = setor * 2048
        with iso.open("rb") as f:
            f.seek(self.base)
            cab = f.read(8)
            if cab[:4] != b"AFS\0":
                raise ValueError("BIO4DAT.AFS não encontrado no setor esperado")
            self.n = int(struct.unpack_from("<I", cab, 4)[0])
            tab = f.read(8 * (self.n + 1))
            self.entradas = [struct.unpack_from("<II", tab, 8 * i) for i in range(self.n + 1)]
            off, tam = self.entradas[self.n]
            f.seek(self.base + off)
            nomes = f.read(tam)
        self.nomes = [nomes[i * 48 : i * 48 + 32].split(b"\0", 1)[0].decode("latin-1") for i in range(self.n)]

    def arquivo(self, indice: int) -> ArquivoAfs:
        off, tam = self.entradas[indice]
        return ArquivoAfs(indice, self.nomes[indice], int(off), int(tam))

    def ler(self, indice: int) -> bytes:
        a = self.arquivo(indice)
        with self.iso.open("rb") as f:
            f.seek(self.base + a.deslocamento)
            return f.read(a.tamanho)


def ler_bloco(c: Cliente, inicio: int, tamanho: int) -> bytes:
    partes = []
    for lote in range(inicio, inicio + tamanho, 2000 * 8):
        fim = min(inicio + tamanho, lote + 2000 * 8)
        partes.append(
            c.pedir(*(p.comando(p.Codigo.READ64, struct.pack("<I", e)) for e in range(lote, fim, 8)))
        )
    return b"".join(partes)[:tamanho]


def escrever_bloco(c: Cliente, endereco: int, dados: bytes) -> None:
    """Escreve em palavras de 8 bytes (o resto em bytes), em pedidos de até 40 mil escritas."""
    inteiro = len(dados) & ~7
    for lote in range(0, inteiro, ESCRITAS_POR_PEDIDO * 8):
        fim = min(inteiro, lote + ESCRITAS_POR_PEDIDO * 8)
        c.pedir(
            *(
                p.comando(
                    p.Codigo.WRITE64, struct.pack("<IQ", endereco + i, struct.unpack_from("<Q", dados, i)[0])
                )
                for i in range(lote, fim, 8)
            )
        )
    if inteiro < len(dados):
        c.pedir(
            *(
                p.comando(p.Codigo.WRITE8, struct.pack("<IB", endereco + i, dados[i]))
                for i in range(inteiro, len(dados))
            )
        )


def entradas(c: Cliente) -> list[EntradaModulo]:
    saida = []
    for i in range(ENTRADAS):
        e = TABELA_MODULOS + i * TAMANHO_ENTRADA
        campos = struct.unpack_from("<HHIIIII", ler_bloco(c, e + 0x80, 24), 0)
        saida.append(EntradaModulo(i, *campos))
    return saida


def arquivos_do_tipo(c: Cliente, tipo: int) -> tuple[int, int]:
    """Índices do .dat e do .rel no AFS para o tipo, na tabela do modo de personagem corrente."""
    modo = c.pedir(p.comando(p.Codigo.READ8, struct.pack("<I", PERSONAGEM)))[0]
    tabela = TABELA_ARQUIVOS.get(modo, TABELA_ARQUIVOS[0])
    dat, rel = struct.unpack_from("<HH", ler_bloco(c, tabela + tipo * 8, 8), 0)
    return int(dat), int(rel)


def liberar(c: Cliente, tipo: int) -> EntradaModulo | None:
    c.chamar(SCE_DESTROY_EM, (tipo, tipo), tempo_limite_ms=3000)
    entrada = next((e for e in entradas(c) if e.tipo == tipo), None)
    if entrada is not None:
        c.chamar(INIT_MODULE, (TABELA_MODULOS + entrada.indice * TAMANHO_ENTRADA,), tempo_limite_ms=3000)
    return entrada


def alocar(c: Cliente, tamanho: int) -> int:
    """Pede memória ao alocador do jogo pela chamada remota (trampolim com os argumentos fixos)."""
    c.pedir(
        *(
            p.comando(p.Codigo.WRITE32, struct.pack("<II", TRAMPOLIM_ALOCAR + 4 * i, w))
            for i, w in enumerate(CODIGO_ALOCAR)
        )
    )
    r = c.chamar(TRAMPOLIM_ALOCAR, (tamanho,), tempo_limite_ms=3000)
    if not r.ok or r.v0 == 0:
        raise RuntimeError(f"mem_alloc({tamanho:#x}) falhou: {r.estado}, v0 {r.v0:#x}")
    return r.v0


def carregar(c: Cliente, tipo: int, afs: Afs, arquivos: tuple[int, int] | None = None) -> EntradaModulo:
    """Carrega o módulo do tipo; ``arquivos`` (índices do .dat e do .rel no AFS) sobrepõe a tabela do jogo, o que
    permite registrar sob um número de tipo um módulo que a tabela deste modo não lista (ex.: pl12, a Ada de cena)."""
    livre = next((e for e in entradas(c) if e.livre), None)
    if livre is None:
        raise ValueError("as quatro entradas de módulo estão em uso; libere uma com `liberar <tipo>`")
    dat_i, rel_i = arquivos if arquivos else arquivos_do_tipo(c, tipo)
    if dat_i == 0 or rel_i == 0:
        raise ValueError(f"o tipo {tipo:#x} não tem arquivos de módulo neste modo de personagem")
    dat, rel = afs.ler(dat_i), afs.ler(rel_i)
    if rel[:4] != b"SNR2":
        raise ValueError(f"{afs.nomes[rel_i]} não tem cabeçalho SNR2")
    tam_dat, tam_rel = arredondar(len(dat)), arredondar(len(rel))
    base_dat = alocar(c, tam_dat)
    base_rel = alocar(c, tam_rel)
    escrever_bloco(c, base_dat, dat)
    escrever_bloco(c, base_rel, rel)
    e = TABELA_MODULOS + livre.indice * TAMANHO_ENTRADA
    escrever_bloco(c, e, bytes(0x80))
    escrever_bloco(
        c, e + 0x80, struct.pack("<HHIIIII", tipo, FLAGS_ALOCADO, base_dat, base_rel, tam_dat, tam_rel, 0)
    )
    r = c.chamar(REGISTRAR_MODULO, (e,), tempo_limite_ms=5000)
    if not r.ok:
        raise RuntimeError(f"a inicialização do módulo pelo jogo não voltou: {r.estado}")
    achado = c.chamar(SEARCH_EM_MODULE, (tipo,), tempo_limite_ms=3000)
    if achado.v0 != e:
        raise RuntimeError(
            f"o jogo não reconhece o módulo do tipo {tipo:#x} (SearchEmModule devolveu {achado.v0:#x})"
        )
    return entradas(c)[livre.indice]


def _cliente() -> Cliente:
    c = Cliente(porta=28011, tempo_limite_s=60.0)
    c.conectar()
    return c


def _linha(e: EntradaModulo) -> str:
    return f"entrada {e.indice}: tipo {e.tipo:#04x} flags {e.flags:#x} dat {e.dat:#x} ({e.tamanho_dat:#x}) rel {e.rel:#x} ({e.tamanho_rel:#x}) init {e.inicializacao:#x}"


def listar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        for e in entradas(c):
            print("  ", _linha(e))
        if args.tipos:
            afs = Afs(args.iso)
            for tipo in args.tipos:
                dat, rel = arquivos_do_tipo(c, tipo)
                print(
                    f"   tipo {tipo:#04x}: {afs.arquivo(dat) if dat else None} {afs.arquivo(rel) if rel else None}"
                )
    finally:
        c.fechar()
    return 0


def cmd_liberar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        e = liberar(c, args.tipo)
        print("liberada:", _linha(e) if e else "o tipo não estava carregado")
    finally:
        c.fechar()
    return 0


def cmd_carregar(args: argparse.Namespace) -> int:
    c = _cliente()
    try:
        c.pedir(p.comando(p.Codigo.SAVE_STATE, bytes([95])))
        arquivos = (args.dat, args.rel) if args.dat and args.rel else None
        e = carregar(c, args.tipo, Afs(args.iso), arquivos)
        print("carregado:", _linha(e))
    finally:
        c.fechar()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("listar")
    s.add_argument("tipos", nargs="*", type=lambda x: int(x, 0))
    s.add_argument("--iso", type=Path, default=ISO_PADRAO)
    s.set_defaults(func=listar)
    s = sub.add_parser("liberar")
    s.add_argument("tipo", type=lambda x: int(x, 0))
    s.set_defaults(func=cmd_liberar)
    s = sub.add_parser("carregar")
    s.add_argument("tipo", type=lambda x: int(x, 0))
    s.add_argument("--iso", type=Path, default=ISO_PADRAO)
    s.add_argument("--dat", type=int, default=0, help="índice do .dat no AFS (sobrepõe a tabela do jogo)")
    s.add_argument("--rel", type=int, default=0, help="índice do .rel no AFS (sobrepõe a tabela do jogo)")
    s.set_defaults(func=cmd_carregar)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
