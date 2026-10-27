"""Abrir a sessão (card S3-06; caso E01): do emulador rodando ao primeiro ciclo.

Ordem: sondar o canal e esperar o jogo, identificar jogo e modo, aviso e aceite (E02), tom e intensidade,
sessão viva em pasta própria, catálogo, um estado salvo já no começo (para a recarga ter de onde voltar),
e a sessão pronta para o laço. A escolha de tom e intensidade por tela é o caso C01; aqui vêm por argumento.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from iaemps2.catalogo import catalogo as cat
from iaemps2.config import Config
from iaemps2.olho.captura import Captura, Capturador, Retangulo
from iaemps2.ponte import emulador
from iaemps2.ponte.cliente import CanalError, Cliente
from iaemps2.ponte.protocolo import Status
from iaemps2.registro import banco
from iaemps2.servicos import criar
from iaemps2.servicos.base import Servico
from iaemps2.sessao import aviso
from iaemps2.sessao.ciclo import Capturar, PainelDaSessao, Sessao, emulador_vivo
from iaemps2.sessao.relogio import Contador


class AberturaRecusadaError(RuntimeError):
    """A sessão não abre: aviso recusado, sem canal, sem jogo."""


def abrir(
    config: Config,
    painel: PainelDaSessao,
    *,
    pedir_aceite: Callable[[str], bool],
    tom: cat.Tom = cat.TOM_PADRAO,
    intensidade: cat.Intensidade = cat.INTENSIDADE_PADRAO,
    servico: Servico | None = None,
    capturar: Capturar | None = None,
    contador: Contador | None = None,
    cliente: Cliente | None = None,
    pasta_sessoes: Path | None = None,
    encerrar_apos_s: float | None = None,
    processo_vivo: Callable[[], bool] | None = None,
) -> Sessao:
    pasta_sessoes = pasta_sessoes or config.sessoes.caminho()
    cliente = cliente or Cliente(config.canal.host, config.canal.porta, config.canal.tempo_limite_s)
    try:
        cliente.conectar()
    except CanalError as erro:
        raise AberturaRecusadaError(f"canal não encontrado: {erro.detalhe}") from erro
    versao = cliente.versao()
    if cliente.esperar_jogo(limite_s=config.canal.espera_jogo_s) != Status.RODANDO:
        raise AberturaRecusadaError("nenhum jogo rodando no emulador")
    jogo = emulador.identificar(cliente)

    servico = servico or criar(config.servico.ativo)
    if aviso.precisa_perguntar(pasta_sessoes, servico.nome):
        aceito = pedir_aceite(aviso.texto(servico.nome))
        aviso.registrar(pasta_sessoes, servico.nome, aceito)
        if not aceito:
            raise AberturaRecusadaError(
                "aviso recusado: sem aceite nada sai da máquina e o mestre não enxerga"
            )

    sessao_id = banco.novo_id_sessao()
    pasta = pasta_sessoes / sessao_id
    con = banco.criar(pasta / "sessao.sqlite")
    banco.abrir_sessao(
        con,
        jogo_titulo=jogo.identificacao.titulo,
        jogo_serial=jogo.identificacao.serial,
        jogo_crc=jogo.identificacao.crc,
        jogo_versao=jogo.identificacao.versao_jogo,
        emulador_versao=versao,
        modo=jogo.modo,
        tom=tom.value,
        intensidade=intensidade.value,
        servico=servico.nome,
        aceite_versao=aviso.VERSAO_AVISO,
        config_json=json.dumps(config.model_dump(mode="json"), ensure_ascii=False),
        id_=sessao_id,
    )
    aceite = aviso.ler(pasta_sessoes)
    if aceite is not None:
        banco.inserir(
            con,
            "aceites",
            {
                "aceito_em_utc": aceite.aceito_em_utc,
                "aviso_versao": aceite.aviso_versao,
                "servico": aceite.servico,
                "aceito": 1 if aceite.aceito else 0,
            },
        )

    catalogo = cat.montar(jogo.capacidades, tom, intensidade)
    if capturar is None:
        capturador = Capturador(config.captura.largura_px, config.captura.qualidade_jpeg)

        def capturar_real(overlay: Retangulo | None) -> Captura:
            return capturador.capturar(overlay)

        capturar = capturar_real
    sessao = Sessao(
        config=config,
        cliente=cliente,
        jogo=jogo,
        con=con,
        sessao_id=sessao_id,
        pasta=pasta,
        servico=servico,
        capturar=capturar,
        painel=painel,
        catalogo=catalogo,
        contador=contador or Contador(),
        tom=tom,
        intensidade=intensidade,
        encerrar_apos_s=encerrar_apos_s,
        processo_vivo=processo_vivo if processo_vivo is not None else emulador_vivo,
    )
    # um estado salvo logo no começo: a recarga precisa de um slot com contexto antes do primeiro período
    sessao.executor.salvar_periodico(None)
    sessao.ultimo_salvamento_ms = sessao.contador.agora_ms()
    return sessao
