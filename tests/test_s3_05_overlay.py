"""Card S3-05: overlay, aviso e teclas.

Critério de aceite: dado uma intervenção confirmada, quando ela acontece, então ação e motivo aparecem no painel
no mesmo segundo; e Ctrl+Alt+P pausa o mestre sem pausar o jogo. A parte sem monitor é provada aqui; a parte
Tk é provada onde há tela (pulada no CI sem monitor).
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Iterator
from pathlib import Path

import pytest

from iaemps2.sessao import aviso
from iaemps2.sessao.overlay import Overlay, Painel, formatar_historico, teclas_pressionadas

# ---------- puro ----------


def test_aviso_versionado_e_nomeia_o_servico() -> None:
    t = aviso.texto("provedor_g")
    assert '"provedor_g"' in t and "Ctrl+Alt+P" in t and "BIOS" in t and "nunca sai" in t
    assert aviso.VERSAO_AVISO == "1"


def test_aceite_pergunta_na_primeira_vez_e_depois_nao(tmp_path: Path) -> None:
    assert aviso.precisa_perguntar(tmp_path, "falso")
    a = aviso.registrar(tmp_path, "falso", True)
    assert a.aceito and a.aviso_versao == "1" and aviso.ler(tmp_path) == a
    assert not aviso.precisa_perguntar(tmp_path, "falso")


def test_aceite_volta_a_perguntar_se_servico_ou_texto_mudam(tmp_path: Path) -> None:
    aviso.registrar(tmp_path, "falso", True)
    assert aviso.precisa_perguntar(tmp_path, "provedor_g")  # serviço trocado (E02 A1)
    assert aviso.precisa_perguntar(tmp_path, "falso", versao="2")  # texto novo
    aviso.registrar(tmp_path, "falso", False)
    assert aviso.precisa_perguntar(tmp_path, "falso")  # recusa não vale como aceite


def test_aceite_corrompido_vira_pergunta(tmp_path: Path) -> None:
    aviso.arquivo_de_aceite(tmp_path).write_text("{nada", encoding="utf-8")
    assert aviso.ler(tmp_path) is None and aviso.precisa_perguntar(tmp_path, "falso")


def test_painel_linhas() -> None:
    p = Painel()
    assert p.linha_de_acao(5000) == "Iniciando..." and p.linha_de_janela() == "pode intervir"
    p.ultima_acao, p.acao_em_ms = "camera lenta", 2000
    assert p.linha_de_acao(7500) == "camera lenta  ·  há 5s"
    p.proxima_janela_ms = 12_400
    assert p.linha_de_janela() == "próxima janela em 12s"
    p.pausado = True
    assert p.linha_de_janela() == "mestre pausado" and p.cor_do_estado() == "#ffb300"
    p.pausado, p.falha = False, "serviço fora do ar"
    assert p.linha_de_janela() == "mestre em silêncio" and p.cor_do_estado() == "#f44336"


def test_historico_formatado_do_mais_recente() -> None:
    assert formatar_historico([]) == "nenhuma"
    assert formatar_historico(["a", "b", "c"]) == "c  ›  b  ›  a"
    assert formatar_historico([str(i) for i in range(9)], maximo=3) == "8  ›  7  ›  6"


def test_teclas_globais_exigem_ctrl_e_alt() -> None:
    def leitor(pressionadas: set[int]):  # type: ignore[no-untyped-def]
        return lambda vk: vk in pressionadas

    assert teclas_pressionadas(leitor({0x5A})) is None  # Z sozinho
    assert teclas_pressionadas(leitor({0x11, 0x5A})) is None  # Ctrl+Z
    assert teclas_pressionadas(leitor({0x11, 0x12, 0x5A})) == "reverter"
    assert teclas_pressionadas(leitor({0x11, 0x12, 0x50})) == "pausar"
    assert teclas_pressionadas(leitor({0x11, 0x12, 0x51})) == "encerrar"
    assert teclas_pressionadas(leitor({0x11, 0x12})) is None


# ---------- com tela ----------


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("sem monitor para o Tk")
    r.withdraw()
    yield r
    with contextlib.suppress(tk.TclError):
        r.destroy()


def test_acao_e_motivo_aparecem_no_mesmo_tick(root: tk.Tk) -> None:
    gestos: list[str] = []
    agora = [10_000]
    o = Overlay(gestos.append, agora_ms=lambda: agora[0], leitor_de_tecla=lambda vk: False, root=root)
    o.atualizar(jogo="Resident Evil 4", modo="reduzido", estado="observando", enviando=True)
    o.mostrar_acao("camera_lenta", "O tempo pesa.")
    o._desenhar()
    assert o._lbl_acao.cget("text") == "[mestre] camera lenta  ·  há 0s"
    assert o._lbl_motivo.cget("text") == "O tempo pesa."
    assert "Resident Evil 4" in o._lbl_jogo.cget("text") and "enviando" in o._lbl_envio.cget("text")
    assert o._lbl_hist.cget("text") == "histórico: camera_lenta"
    o.mostrar_nada("Sem razão para intervir.")
    o._desenhar()
    assert (
        o._lbl_acao.cget("text").startswith("[mestre] observando")
        and o._lbl_hist.cget("text") == "histórico: camera_lenta"
    )


def test_tecla_de_pausa_enfileira_o_gesto_uma_vez_por_pressao(root: tk.Tk) -> None:
    gestos: list[str] = []
    pressionadas: set[int] = set()
    o = Overlay(gestos.append, leitor_de_tecla=lambda vk: vk in pressionadas, root=root)
    o._tick()
    assert gestos == []
    pressionadas.update({0x11, 0x12, 0x50})  # Ctrl+Alt+P segurado
    o._tick()
    o._tick()
    assert gestos == ["pausar"]  # uma vez, não a cada volta
    pressionadas.clear()
    o._tick()
    pressionadas.update({0x11, 0x12, 0x5A})
    o._tick()
    assert gestos == ["pausar", "reverter"]


def test_botao_de_pausa_muda_para_retomar(root: tk.Tk) -> None:
    o = Overlay(lambda g: None, leitor_de_tecla=lambda vk: False, root=root)
    o.atualizar(pausado=True)
    o._desenhar()
    assert o._btn_pausar.cget("text").startswith("Retomar")


def test_area_e_recolher(root: tk.Tk) -> None:
    o = Overlay(lambda g: None, leitor_de_tecla=lambda vk: False, posicao=(100, 50), root=root)
    root.deiconify()
    a = o.area()
    assert a.esquerda == 100 and a.topo == 50 and a.largura > 0 and a.altura > 0
    o.recolher()
    root.update_idletasks()
    assert o.area().altura < a.altura
    o.recolher()


def test_atualizar_recusa_campo_desconhecido(root: tk.Tk) -> None:
    o = Overlay(lambda g: None, leitor_de_tecla=lambda vk: False, root=root)
    with pytest.raises(AttributeError):
        o.atualizar(inexistente=1)
