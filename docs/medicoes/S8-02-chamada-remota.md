# S8-02 — chamada remota, criação de personagens e módulos carregados pelo mestre

Medição de 29/10/2026 na máquina do cliente, com o cliente no controle. Fotos e logs em
`~/IAEmPS2/medicoes/s8-02/` (não entram no repositório).

## O pedido e o caminho

"Spawna um mob." O jogo cria personagens por `EmSetEvent(struct de 32 bytes)` e `EmSetFromList2(i)` (entrada i da
lista da sala, 0x0042DEE4, formato no perfil). Não há como fazer isso escrevendo memória: é uma função. Por isso o
fork ganhou a **chamada remota** (código 0x8C, capacidade 32): no vsync o emulador salva os registradores do
processador, põe os argumentos em a0..a3, pilha própria e retorno num trampolim `b .`, e desvia para a função; ao
ver o processador no trampolim, lê v0/v1 e restaura tudo. Primeira prova: `EmListIsAlive(15)` = 1 e
`cItemMgr::num(pistola)` = 1, em 17 ms, jogo seguindo.

## O que foi criado e dado ao vivo

- Ganado aldeão (tipo 0x12) a 2 m do cliente, e mais três em volta; corvos; os tipos 0x2A e 0x21. Todos nascem onde
  a struct manda (posição em centímetros) e andam. Um Ganado criado andou 2,6 m na direção do cliente.
- Erva, 10 balas e a arma 0x2C pela função do próprio jogo "dar item se couber" (0x00261898), que encaixa na maleta.
- 5000 pesetas por `FUN_0011e610`, vida cheia escrevendo 0x0042DA76, teleporte do jogador escrevendo a posição da
  entidade (+0x40, +0xC0, +0x130), e o cenário escondido por 20 s pela camada de cena (45 materiais).

## Módulos: o limite e a saída

Cada tipo de personagem é um módulo de dois arquivos do `BIO4DAT.AFS`: `.dat` (modelos) e `.rel` (código
realocável, formato SNR2 da SN Systems). Só quatro ficam carregados; o jogo carrega do disco na tela de loading,
dormindo pelo escalonador, que é feito de threads do kernel com semáforos. Chamar isso pelo canal trava a thread
que executa (provado três vezes, inclusive ancorado na thread de jogo pelo memcheck da matriz da câmera).

A saída foi o mestre fazer o trabalho do carregador: ler os dois arquivos da ISO, pedir memória ao `mem_alloc` do
jogo (seis argumentos, por um trampolim de sete instruções), escrever os bytes, preencher a entrada da tabela de
módulos e pedir ao jogo que ligue e inicialize (`FUN_00262bb0`, que não dorme). `SearchEmModule` confirma. Com o
módulo residente, `EmSetEvent` cria em 8 a 17 ms. Validado com `pl11`, `pl14`, `pl0e`, `pl0f`, `em25` e `pl12`.

## Identidade dos tipos, lida nos arquivos

As tabelas de seções dos `.rel` trazem os nomes das classes: tipo 2 = `cSubLeon`, 3 = `cSubAshley` (três trajes),
4 = `cSubLuis`, 0xE e 0xF = as lanchas (`cPl0e`, `cPl0f`), `pl02` = `cPlAda` (jogável), `pl12` = `cSubAda` (de cena),
`pl06` = `cPlHunk`, `pl0a` = `cPlKlauser`, `pl0d` = `cPlWesker`. Nas dez listas de inimigos da campanha do Leon não
existe entrada da Ada: ela só aparece em eventos de cena.

O cliente viu na tela: a lancha do Del Lago criada na frente dele (e andou nela), o tipo 0x25 desenhado como um
emaranhado de linhas, o Leon com o cabelo trocado depois de carregar `pl10` (os módulos de personagem disputam as
mesmas vagas de textura).

## O que travou e por quê

| tentativa | resultado | causa lida |
|---|---|---|
| `EmSetEvent` de tipo sem módulo residente | jogo congelado | o carregador dorme por `TaskSleep`; a thread sequestrada nunca volta |
| `TaskExec` numa vaga livre (7 e 1) | tarefa fica pendente | só o escalonador do jogo inicia tarefas, em condições que não foram lidas |
| carregar com endereço fixo | jogo congelado | sobrescreveu o módulo vivo da lancha (corrigido: memória pelo `mem_alloc`) |
| destruir a lancha com o cliente em cima | jogo congelado | nunca liberar um tipo com que o jogador interage |
| criação de `cSubLeon` (tipo 2) | thread perdida | a ligação do módulo não terminou; ainda não determinado |
| `cSubAda` com o modelo `pl02` | nasce, anda, e o jogo congela segundos depois em `cSatMgr::hitCheck2` | a Ada de cena não tem `.dat` próprio; o sistema de cenas prepara colisão e animação de outro modo |

Recuperação sempre por estado salvo antes de cada experimento (slots 95 a 99 do mestre).

## O que fica

- Ferramentas: `bancada/personagens.py` (listar, criar), `bancada/modulos.py` (listar, liberar, carregar, inclusive
  por índice de arquivo), `bancada/inventario.py`, `vigia_dano.py armar/ler`.
- Fork: `IAEmCall` (chamada imediata e ancorada por pc ou por acesso de memória), 0x8C.
- Perfil: seções `entidades.lista_da_sala`, `entidades.tipos`, `modulos`.
- Pendente: a Ada de cena pelo sistema de cenas (`evm`, `SceAt*`); a ligação do tipo 2; nomes dos em10..em4f.

## Decisão do cliente (29/10)

Mapear o jogo inteiro de forma sistemática, não sob demanda: decompilação de todas as funções (10.673 no
executável e módulos carregados, sem falhas), módulos da ISO realocados pelo próprio mestre, índice por subsistema
e documento de estruturas. Entra no Blueprint como etapa S9, antes das ações de mundo.
