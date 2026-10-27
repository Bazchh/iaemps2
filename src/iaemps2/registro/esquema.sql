-- Migração 0001 · a sessão viva (Blueprint Técnico, capítulo 3).
-- Roda uma vez por sessão, ao criar o arquivo. Só de acréscimo: os gatilhos ficam em banco.py.

create table sessoes (
  id              text primary key,            -- identificador ordenável pelo tempo
  aberta_em_utc   text not null,
  fechada_em_utc  text,                        -- nulo = sessão sem fim (E05 retoma)
  jogo_titulo     text not null,
  jogo_serial     text not null,               -- SLUS-21134
  jogo_crc        text not null,               -- 013e349d
  jogo_versao     text,
  emulador_versao text not null,
  modo            text not null check (modo in ('completo','reduzido')),
  tom             text not null,
  intensidade     text not null,
  servico         text not null,               -- nome do adaptador em uso
  aceite_versao   text not null,               -- versão do texto do aviso aceito (E02)
  config_json     text not null
);

create table catalogo_versoes (
  id            integer primary key,
  sessao_id     text not null references sessoes (id),
  versao        integer not null,
  criado_ms     integer not null,              -- contador da sessão
  motivo        text not null,                 -- abertura, alavanca indisponível, emulador reiniciado
  catalogo_json text not null,                 -- alavancas, faixas, disponibilidade, motivos padrão
  unique (sessao_id, versao)
);

create table ciclos (
  id            integer primary key,
  sessao_id     text not null references sessoes (id),
  numero        integer not null,
  inicio_ms     integer not null,
  fim_ms        integer,
  status_emu    text not null check (status_emu in ('rodando','pausado','desligado','sem_canal')),
  estado_mestre text not null,                 -- estado da máquina do capítulo 4 no início do ciclo
  lacuna        text,                          -- nulo, ou o motivo de não haver observação
  unique (sessao_id, numero)
);

create table capturas (
  id           integer primary key,
  ciclo_id     integer not null references ciclos (id),
  arquivo      text not null,                  -- capturas/000123.jpg, relativo à pasta da sessão
  largura      integer not null,
  altura       integer not null,
  bytes        integer not null,
  digest       text not null,                  -- impressão digital da imagem reduzida
  diferenca    real,                           -- medida contra a última enviada (B03)
  enviada      integer not null check (enviada in (0,1)),
  motivo_envio text                            -- mudança, intervalo vencido, releitura
);

create table situacoes (
  id             integer primary key,
  captura_id     integer not null references capturas (id),
  descricao      text not null,
  fase           text not null check (fase in ('exploracao','combate','menu','video','carregamento','morte','sistema')),
  aperto         integer not null check (aperto between 0 and 4),
  confianca      real not null check (confianca between 0 and 1),
  suspeita       text,                         -- nulo, ou por que contradiz o estado do emulador (B02 E3)
  latencia_ms    integer not null,
  resposta_bruta text not null                 -- o JSON como veio, para a bancada
);

create table decisoes (
  id              integer primary key,
  ciclo_id        integer not null references ciclos (id),
  situacao_id     integer references situacoes (id),  -- nulo quando a decisão é "nada" por falta de situação
  catalogo_versao integer not null,
  alavanca        text not null,               -- 'nada' ou uma do catálogo
  parametros_json text not null,
  motivo          text not null,
  motivo_origem   text not null check (motivo_origem in ('servico','padrao','ausente')),
  origem          text not null check (origem in ('servico','descarte','ritmo','bloqueio','falha')),
  descarte_motivo text,                        -- fora do catálogo, fora da faixa, regra de mesa, situação velha
  pedido_bruto    text not null,
  resposta_bruta  text,
  latencia_ms     integer
);

create table intervencoes (
  id                 integer primary key,
  decisao_id         integer not null references decisoes (id),
  alavanca           text not null,
  parametros_json    text not null,
  origem             text not null check (origem in ('mestre','reversao_jogador','encerramento')),
  estado_antes_json  text not null,            -- status, velocidade, slot mais recente, situação
  comando_ms         integer not null,
  confirmado_ms      integer,                  -- nulo = não confirmado
  estado_depois_json text,
  resultado          text not null check (resultado in ('pendente','confirmada','falhou','descartada','cancelada_jogador')),
  fim_ms             integer,                  -- para ações com duração: quando voltou ao normal
  reversivel         integer not null check (reversivel in (0,1)),
  revertida_por      integer references intervencoes (id),
  caminho_volta_json text                      -- ex.: slot de volta da recarga (A06)
);

create table estados_reservados (
  id             integer primary key,
  sessao_id      text not null references sessoes (id),
  slot           integer not null check (slot between 90 and 99),
  salvo_ms       integer not null,
  confirmado_ms  integer,                      -- tamanho estável em duas leituras (LC-11)
  arquivo        text not null,
  bytes          integer,
  situacao_id    integer references situacoes (id), -- contexto para a recarga
  motivo         text not null,                -- periodico, antes_recarga, fim_sessao
  sobrescrito_ms integer,                      -- quando a fila avançou por cima dele
  suspeito       integer not null default 0
);

create table falhas (
  id           integer primary key,
  ciclo_id     integer references ciclos (id),
  ocorrido_ms  integer not null,
  origem       text not null check (origem in ('servico','emulador','captura','registro')),
  classe       text not null,                  -- lista fechada do capítulo 5
  detalhe      text not null,
  visivel      integer not null check (visivel in (0,1)),  -- apareceu no overlay (RN-10)
  resolvida_ms integer
);

create table metricas (
  id             integer primary key,
  ciclo_id       integer not null references ciclos (id),
  etapa          text not null check (etapa in ('captura','descrever','decidir','executar','confirmar')),
  latencia_ms    integer not null,
  tokens_entrada integer,
  tokens_saida   integer,
  custo_estimado real                          -- na moeda da tabela de preço configurada
);

create table marcos (
  id       integer primary key,
  ciclo_id integer not null references ciclos (id),
  tipo     text not null check (tipo in ('morte','mudanca_fase','reversao','pausa_mestre','retomada','lacuna','pausa_por_falhas','queda_emulador')),
  detalhe  text
);

create table aceites (
  id            integer primary key,
  aceito_em_utc text not null,
  aviso_versao  text not null,
  servico       text not null,
  aceito        integer not null check (aceito in (0,1))
);
