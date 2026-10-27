"""O overlay (card S3-05; casos E03, E02, D03, D05, E04; decisões DC-18 e DC-19).

Um painel Tk sem borda, sempre por cima, arrastável, que mostra o que o mestre vê, o que fez e por quê,
e dá ao jogador os três gestos: desfazer, pausar e retomar o mestre, encerrar. As teclas globais são lidas
por sondagem do teclado a cada volta do Tk, sem gancho no sistema. O painel só enfileira: quem decide é o
laço da sessão. Toda atualização de tela passa por `after`, na thread do Tk.

Tudo que não é Tk (formatar linhas, o estado mostrado, a área ocupada) é puro e testado sem monitor.
"""

from __future__ import annotations

import contextlib
import os
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from iaemps2.olho.captura import Retangulo

FUNDO = "#0d0d0d"
FUNDO2 = "#1a1a2e"
ROXO = "#e0aaff"
OURO = "#ffd700"
CINZA = "#888888"
VERDE = "#00e676"
VERMELHO = "#f44336"
AMBAR = "#ffb300"
FONTE = ("Consolas", 9)
FONTE_N = ("Consolas", 9, "bold")
FONTE_P = ("Consolas", 8)

TECLAS = {"reverter": "Ctrl+Alt+Z", "pausar": "Ctrl+Alt+P", "encerrar": "Ctrl+Alt+Q"}
_VK = {"Z": 0x5A, "P": 0x50, "Q": 0x51, "CTRL": 0x11, "ALT": 0x12}


@dataclass
class Painel:
    """O que está na tela, como dado. O Tk só desenha isto."""

    jogo: str = "sem jogo"
    modo: str = "reduzido"
    estado: str = "abrindo"
    situacao: str = ""
    ultima_acao: str = "Iniciando..."
    motivo: str = ""
    acao_em_ms: int | None = None
    enviando: bool = False
    proxima_janela_ms: int = 0
    falha: str | None = None
    pausado: bool = False
    historico: list[str] = field(default_factory=list)

    def linha_de_acao(self, agora_ms: int) -> str:
        if self.acao_em_ms is None:
            return self.ultima_acao
        ha = max(0, agora_ms - self.acao_em_ms) // 1000
        return f"{self.ultima_acao}  ·  há {ha}s"

    def linha_de_janela(self) -> str:
        if self.pausado:
            return "mestre pausado"
        if self.falha:
            return "mestre em silêncio"
        s = self.proxima_janela_ms // 1000
        return "pode intervir" if s == 0 else f"próxima janela em {s}s"

    def cor_do_estado(self) -> str:
        if self.falha:
            return VERMELHO
        if self.pausado:
            return AMBAR
        return VERDE if self.estado in ("observando", "decidindo", "executando") else CINZA


def formatar_historico(acoes: list[str], maximo: int = 5) -> str:
    return "  ›  ".join(reversed(acoes[-maximo:])) if acoes else "nenhuma"


def teclas_pressionadas(estado_tecla: Callable[[int], bool]) -> str | None:
    """Qual gesto está sendo pressionado agora, dado um leitor de tecla virtual (injetável nos testes)."""
    if not (estado_tecla(_VK["CTRL"]) and estado_tecla(_VK["ALT"])):
        return None
    for gesto, letra in (("reverter", "Z"), ("pausar", "P"), ("encerrar", "Q")):
        if estado_tecla(_VK[letra]):
            return gesto
    return None


def _user32() -> Any:
    """A user32 do Windows. cast porque o typeshed de outras plataformas não declara windll."""
    import ctypes

    return cast(Any, ctypes).windll.user32


def _leitor_do_windows() -> Callable[[int], bool]:
    user32 = _user32()

    def pressionada(vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    return pressionada


def _janela_em_foco() -> int:
    """O hwnd da janela em primeiro plano (0 fora do Windows ou se não houver)."""
    if (
        os.name != "nt"
    ):  # os.name, e não sys.platform: o mypy fixa sys.platform e marca o outro ramo como inalcançável
        return 0
    return int(_user32().GetForegroundWindow())


class Overlay:
    """A janela. `ao_gesto` recebe 'reverter' | 'pausar' | 'encerrar' e só enfileira."""

    def __init__(
        self,
        ao_gesto: Callable[[str], None],
        agora_ms: Callable[[], int] = lambda: int(time.monotonic() * 1000),
        leitor_de_tecla: Callable[[int], bool] | None = None,
        posicao: tuple[int, int] = (20, 20),
        root: tk.Tk | None = None,
    ) -> None:
        self.ao_gesto = ao_gesto
        self.agora_ms = agora_ms
        self.painel = Painel()
        self._leitor = leitor_de_tecla
        self._gesto_anterior: str | None = None
        self._recolhido = False
        self.area_atual: Retangulo | None = None  # escrita pelo tick do Tk, lida pela thread do laço
        self._foco_anterior = _janela_em_foco()
        self.root = root or tk.Tk()
        self.root.title("IAEmPS2 · mestre")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.overrideredirect(True)
        self.root.configure(bg=FUNDO)
        self.root.geometry(f"340x250+{posicao[0]}+{posicao[1]}")
        self._montar()
        self._arrastavel(self._cabecalho)
        self._nao_roubar_foco()
        self.root.after(150, self._tick)

    def _nao_roubar_foco(self) -> None:
        """Windows: a janela nunca é ativada, nem ao aparecer nem ao ser clicada; o teclado continua no jogo.

        Os gestos vêm por GetAsyncKeyState, que não depende de foco; o arrasto e os botões recebem o mouse
        normalmente. O Tk ativa a janela ao mapeá-la, então o foco é devolvido a quem o tinha antes.
        """
        if os.name != "nt":
            return
        self.root.update()  # mapeia a janela; o hwnd só é definitivo depois do overrideredirect ser aplicado
        user32 = _user32()
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        gwl_exstyle, ws_ex_noactivate, ws_ex_toolwindow = -20, 0x08000000, 0x00000080
        estilo = user32.GetWindowLongW(hwnd, gwl_exstyle)
        user32.SetWindowLongW(hwnd, gwl_exstyle, estilo | ws_ex_noactivate | ws_ex_toolwindow)
        hwnd_topmost = -1
        swp_nosize_nomove_noactivate_framechanged = 0x0001 | 0x0002 | 0x0010 | 0x0020
        user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_nosize_nomove_noactivate_framechanged)
        if self._foco_anterior:
            user32.SetForegroundWindow(self._foco_anterior)

    # ---------- montagem ----------
    def _montar(self) -> None:
        r = self.root
        self._cabecalho = tk.Frame(r, bg=FUNDO2, cursor="fleur")
        self._cabecalho.pack(fill="x")
        self._lbl_titulo = tk.Label(self._cabecalho, text="⚔  IAEmPS2", bg=FUNDO2, fg=ROXO, font=FONTE_N)
        self._lbl_titulo.pack(side="left", padx=8, pady=4)
        self._lbl_estado = tk.Label(self._cabecalho, text="●", bg=FUNDO2, fg=CINZA, font=FONTE_N)
        self._lbl_estado.pack(side="right", padx=6)
        btn_recolher = tk.Label(self._cabecalho, text="▁", bg=FUNDO2, fg=CINZA, font=FONTE_N, cursor="hand2")
        btn_recolher.pack(side="right", padx=4)
        btn_recolher.bind("<Button-1>", lambda _e: self.recolher())

        self._corpo = tk.Frame(r, bg=FUNDO)
        self._corpo.pack(fill="both", expand=True)
        self._lbl_jogo = tk.Label(self._corpo, text="", bg=FUNDO, fg=OURO, font=FONTE_P, anchor="w")
        self._lbl_jogo.pack(fill="x", padx=10, pady=(6, 0))
        self._lbl_situacao = tk.Label(
            self._corpo,
            text="",
            bg=FUNDO,
            fg="#cccccc",
            font=FONTE_P,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._lbl_situacao.pack(fill="x", padx=10, pady=(2, 4))
        tk.Frame(self._corpo, bg="#333333", height=1).pack(fill="x", padx=10)
        self._lbl_acao = tk.Label(self._corpo, text="", bg=FUNDO2, fg=ROXO, font=FONTE_N, anchor="w", padx=8)
        self._lbl_acao.pack(fill="x", padx=10, pady=(6, 0))
        self._lbl_motivo = tk.Label(
            self._corpo,
            text="",
            bg=FUNDO,
            fg="#aaaaaa",
            font=FONTE_P,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._lbl_motivo.pack(fill="x", padx=10, pady=(0, 4))
        linha = tk.Frame(self._corpo, bg=FUNDO)
        linha.pack(fill="x", padx=10)
        self._lbl_envio = tk.Label(linha, text="", bg=FUNDO, fg=CINZA, font=FONTE_P)
        self._lbl_envio.pack(side="left")
        self._lbl_janela = tk.Label(linha, text="", bg=FUNDO, fg=CINZA, font=FONTE_P)
        self._lbl_janela.pack(side="right")
        self._lbl_falha = tk.Label(
            self._corpo,
            text="",
            bg=FUNDO,
            fg=VERMELHO,
            font=FONTE_N,
            anchor="w",
            wraplength=320,
            justify="left",
        )
        self._lbl_falha.pack(fill="x", padx=10)
        tk.Frame(self._corpo, bg="#333333", height=1).pack(fill="x", padx=10, pady=4)
        self._lbl_hist = tk.Label(
            self._corpo, text="", bg=FUNDO, fg="#555555", font=("Consolas", 7), anchor="w"
        )
        self._lbl_hist.pack(fill="x", padx=10)
        botoes = tk.Frame(self._corpo, bg=FUNDO)
        botoes.pack(fill="x", padx=10, pady=(4, 8))
        self._btn_pausar = self._botao(botoes, f"Pausar  {TECLAS['pausar']}", lambda: self.ao_gesto("pausar"))
        self._botao(botoes, f"Desfazer  {TECLAS['reverter']}", lambda: self.ao_gesto("reverter"))
        self._botao(botoes, f"Encerrar  {TECLAS['encerrar']}", self._confirmar_encerrar)

    def _botao(self, pai: tk.Frame, texto: str, comando: Callable[[], None]) -> tk.Button:
        b = tk.Button(
            pai,
            text=texto,
            bg=FUNDO2,
            fg=ROXO,
            font=FONTE_P,
            relief="flat",
            cursor="hand2",
            activebackground="#2a2a4e",
            activeforeground=ROXO,
            command=comando,
        )
        b.pack(side="left", padx=(0, 4))
        return b

    def _arrastavel(self, alca: tk.Widget) -> None:
        self._dx = self._dy = 0

        def inicio(e: tk.Event) -> None:
            self._dx, self._dy = e.x, e.y

        def mover(e: tk.Event) -> None:
            self.root.geometry(
                f"+{self.root.winfo_x() + e.x - self._dx}+{self.root.winfo_y() + e.y - self._dy}"
            )

        alca.bind("<ButtonPress-1>", inicio)
        alca.bind("<B1-Motion>", mover)
        self._lbl_titulo.bind("<ButtonPress-1>", inicio)
        self._lbl_titulo.bind("<B1-Motion>", mover)

    # ---------- gestos ----------
    def _confirmar_encerrar(self) -> None:
        """E04 e DC-18: encerrar pede confirmação; nunca fecha o emulador."""
        janela = tk.Toplevel(self.root)
        janela.title("Encerrar a sessão?")
        janela.attributes("-topmost", True)
        janela.configure(bg=FUNDO)
        janela.geometry(f"+{self.root.winfo_x() + 20}+{self.root.winfo_y() + 60}")
        tk.Label(
            janela,
            text="Encerrar a sessão do mestre?\nO jogo continua; só o mestre sai.",
            bg=FUNDO,
            fg="#dddddd",
            font=FONTE,
            justify="left",
        ).pack(padx=14, pady=(12, 6))
        linha = tk.Frame(janela, bg=FUNDO)
        linha.pack(pady=(0, 12))

        def sim() -> None:
            janela.destroy()
            self.ao_gesto("encerrar")

        tk.Button(
            linha, text="Encerrar", bg=FUNDO2, fg=VERMELHO, font=FONTE_P, relief="flat", command=sim
        ).pack(side="left", padx=6)
        tk.Button(
            linha, text="Voltar", bg=FUNDO2, fg=ROXO, font=FONTE_P, relief="flat", command=janela.destroy
        ).pack(side="left", padx=6)

    def _tick(self) -> None:
        try:
            leitor = self._leitor or _leitor_do_windows()
            self._leitor = leitor
            gesto = teclas_pressionadas(leitor)
            if gesto and gesto != self._gesto_anterior:
                if gesto == "encerrar":
                    self._confirmar_encerrar()
                else:
                    self.ao_gesto(gesto)
            self._gesto_anterior = gesto
            self._desenhar()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.area_atual = Retangulo(x, y, x + self.root.winfo_width(), y + self.root.winfo_height())
            if self.painel.estado == "encerrada":
                self.root.quit()
                return
        except tk.TclError:
            return
        self.root.after(150, self._tick)

    # ---------- atualização (só pela thread do Tk) ----------
    def atualizar(self, **campos: object) -> None:
        """Pode ser chamada de qualquer thread: o desenho acontece no `after`."""
        for nome, valor in campos.items():
            if not hasattr(self.painel, nome):
                raise AttributeError(f"painel não tem {nome}")
            setattr(self.painel, nome, valor)

    def mostrar_acao(self, alavanca: str, motivo: str) -> None:
        self.painel.ultima_acao = alavanca.replace("_", " ")
        self.painel.motivo = motivo
        self.painel.acao_em_ms = self.agora_ms()
        self.painel.historico.append(alavanca)

    def mostrar_nada(self, motivo: str) -> None:
        """C03: discreto, sem entrar no histórico de ações."""
        self.painel.ultima_acao = "observando"
        self.painel.motivo = motivo
        self.painel.acao_em_ms = self.agora_ms()

    def _desenhar(self) -> None:
        p = self.painel
        self._lbl_jogo.config(text=f"{p.jogo}  ·  modo {p.modo}")
        self._lbl_situacao.config(text=p.situacao or "…")
        self._lbl_acao.config(text=f"[mestre] {p.linha_de_acao(self.agora_ms())}")
        self._lbl_motivo.config(text=p.motivo)
        self._lbl_envio.config(
            text="● enviando capturas" if p.enviando else "○ sem envio", fg=VERDE if p.enviando else CINZA
        )
        self._lbl_janela.config(text=p.linha_de_janela())
        self._lbl_falha.config(text=f"⚠ {p.falha}" if p.falha else "")
        self._lbl_hist.config(text=f"histórico: {formatar_historico(p.historico)}")
        self._lbl_estado.config(text=f"● {p.estado}", fg=p.cor_do_estado())
        self._btn_pausar.config(text=f"{'Retomar' if p.pausado else 'Pausar'}  {TECLAS['pausar']}")

    # ---------- geometria ----------
    def area(self) -> Retangulo:
        """Onde o painel está, em coordenadas de tela, para a captura recortar (B01)."""
        self.root.update_idletasks()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        return Retangulo(x, y, x + self.root.winfo_width(), y + self.root.winfo_height())

    def recolher(self) -> None:
        """E03 A2: reduz a um indicador mínimo; os gestos continuam pelas teclas."""
        self._recolhido = not self._recolhido
        if self._recolhido:
            self._corpo.pack_forget()
            self.root.geometry("340x28")
        else:
            self._corpo.pack(fill="both", expand=True)
            self.root.geometry("340x250")

    def fechar(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.root.destroy()


def pedir_aceite(texto_do_aviso: str, root: tk.Tk | None = None) -> bool:
    """E02: a tela do aviso, antes da primeira captura. Devolve True se aceitou."""
    proprio = root is None
    janela = root or tk.Tk()
    janela.title("IAEmPS2 · o que sai da sua máquina")
    janela.attributes("-topmost", True)
    janela.configure(bg=FUNDO)
    resposta = {"aceito": False}
    tk.Label(
        janela, text=texto_do_aviso, bg=FUNDO, fg="#dddddd", font=FONTE, justify="left", wraplength=520
    ).pack(padx=18, pady=(16, 10))
    linha = tk.Frame(janela, bg=FUNDO)
    linha.pack(pady=(0, 16))

    def decidir(valor: bool) -> None:
        resposta["aceito"] = valor
        janela.quit()

    tk.Button(
        linha,
        text="Aceitar e abrir a sessão",
        bg=FUNDO2,
        fg=VERDE,
        font=FONTE_N,
        relief="flat",
        command=lambda: decidir(True),
    ).pack(side="left", padx=8)
    tk.Button(
        linha,
        text="Recusar",
        bg=FUNDO2,
        fg=VERMELHO,
        font=FONTE_N,
        relief="flat",
        command=lambda: decidir(False),
    ).pack(side="left", padx=8)
    janela.protocol("WM_DELETE_WINDOW", lambda: decidir(False))
    janela.mainloop()
    if proprio:
        janela.destroy()
    else:
        for filho in janela.winfo_children():
            filho.destroy()
    return resposta["aceito"]
