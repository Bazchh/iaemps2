# Estruturas e tabelas do jogo de abertura (Resident Evil 4, SLUS-21134 1.01)

Documento gerado de `perfis/memoria/SLUS-21134.json` (bloco `estruturas`, versão 2, 2026-11-11) por
`docs/fonte/gerar_estruturas.py`. Não editar à mão: mudar o perfil e gerar de novo. Entrega do card S9-02.

Fonte única do documento de estruturas (S9-02): docs/fonte/gerar_estruturas.py gera docs/Estruturas-SLUS-21134.md daqui. Deslocamentos em hexadecimal; endereços estáticos são do executável SLUS-21134 1.01; o que é dinâmico (heap, módulo realocado) vem com a raiz estática e o caminho. Provas: decompilado = lido no C decompilado do PS2 (S9-01); vigia = vigia de escrita do fork (S8-01); foto = diferença entre fotos da memória (S8-00); ao_vivo = lido ou escrito pelo canal com efeito conferido; publica = fonte pública conferida ao vivo; gc = só o nome ou o papel vem da decompilação do GameCube, sem prova no PS2. Conferência ao vivo (11/11/2026): reversa/estruturas/conferir.py lê cada campo pelo canal e confere por relação independente do perfil (EM_LIST × cEm, soma das classes de polígonos, matriz × inversa, projeção da câmera, AFS lido na ISO, lista de áreas pela raiz do código); só leitura, estados 96 (jogo do cliente) e 95 (gravado pelos scripts de 30/10), sala 0x0100, uma execução de cada; três campos por estrutura sorteados com semente registrada. O aceite do card é do cliente e continua pendente: a conferência automática só prepara a lista do que ele olha.

## Cobertura

Uma linha por estrutura: campos descritos, campos com prova no PS2 (não só nome do GameCube), campos com quem
escreve e quem lê determinados por prova (células marcadas '(gc)' ou '(inferido)' não contam), o resultado da
conferência ao vivo automática e o estado. As estruturas sem campo são as que ninguém leu ainda.

Conferência ao vivo automática (2026-11-11; estados 95, 96; uma execução por estado):
126 campos batem com a relação anotada, 34 foram lidos sem relação
independente, 2 divergem e 1 não eram conferíveis nesses estados.
'Bate' significa que o valor lido satisfez a relação escrita ao lado dele, que pode ser um cruzamento com outra
estrutura ou com a ISO, uma faixa, ou a constante que o perfil já afirmava; 'lido' é só o valor, sem relação
disponível. A força de cada 'bate' é a da relação escrita. Os resultados valem para esses estados e essa
sala, não para o jogo inteiro. O critério de aceite do card (três campos por estrutura conferidos ao vivo pelo
cliente) continua pendente em 21 de 21 estruturas: os três campos sorteados por estrutura estão
listados na seção de cada uma, com o valor lido, para o cliente olhar.

| estrutura | raiz | campos | com prova no PS2 | com escreve e lê | conferência ao vivo | estado |
|---|---|---|---|---|---|---|
| [Bloco global do jogo (pG, GLOBAL_WK)](#pg) | 0x00425BA0 (apontado por 0x00325308); estático | 15 | 15 | 4 | 11 batem, 3 lidos, 1 divergem, 0 não conferíveis | parcial |
| [Gerente de personagens (EmMgr, cManager<cEm>)](#emmgr) | 0x004203B0; estático. Ponteiro do jogador pPL em 0x004203D0 | 6 | 4 | 1 | 4 batem, 2 lidos, 0 divergem, 0 não conferíveis | lida |
| [Personagem (cEm; cUnit → cCoord → cModel → cEm)](#cem) | EmMgr+0 + 0xED0 × vaga; dinâmico (heap). Vaga 0 = jogador (pPL) | 28 | 28 | 4 | 26 batem, 2 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Corpo de colisão do personagem (cAtariInfo, em cEm+0x320)](#catariinfo) | cEm+0x320 | 11 | 7 | 1 | 7 batem, 4 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Entrada da lista de inimigos da sala (EM_LIST, 32 bytes)](#em_list) | pG+0x8344 + 0x20 × i (0x0042DEE4); arquivos emleon00..09.esl do AFS (emgirl* nas partes da Ashley) | 12 | 11 | 11 | 6 batem, 6 lidos, 0 divergem, 0 não conferíveis | lida |
| [Inventário: gerenciador de itens (cItemMgr) e item](#citemmgr) | 0x003CE148; estático. Vetor de itens no heap (0x010F6540 no estado 91), lido por +0x14 | 14 | 14 | 7 | 13 batem, 1 lidos, 0 divergem, 0 não conferíveis | lida |
| [Tabelas de peças e de armas](#tabelas_itens) | peças 0x00326DE8 (ITEM_PIECE_INFO); armas 0x003A99C0 (43 entradas, contagem em 0x002F0200); alocações do inventário 0x00433F80; estáticas | 10 | 10 | 6 | 9 batem, 1 lidos, 0 divergem, 0 não conferíveis | lida |
| [Módulos de personagem (tabela de módulos, arquivos por tipo, SNR2)](#modulos) | tabela de módulos 0x00455E50 (4 entradas de 0x98); arquivos por tipo 0x00328458 (+tipo × 8; 0x003286D8 / 0x00328958 / 0x00328BD8 por modo de personagem); estáticas. Código e dados dos módulos no heap (mem_alloc) | 11 | 11 | 8 | 9 batem, 2 lidos, 0 divergem, 0 não conferíveis | lida |
| [Arquivos da ISO (BIO4DAT.AFS)](#afs) | ISO, setor 446273 (2048 bytes por setor) | 4 | 4 | 2 | 4 batem, 0 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Tarefas e threads (escalonador do jogo)](#tarefas) | tabela de tarefas 0x00451688 (20 entradas de 0x350); tarefa corrente em 0x00451680; semáforos do kernel 0x004558CC / 0x004558D0; estáticas | 8 | 8 | 2 | 3 batem, 4 lidos, 1 divergem, 0 não conferíveis | parcial |
| [Sistema de cenas: áreas de roteiro (SceAt) e eventos (Event/EventMgr)](#cenas) | lista ordenada com cabeça em *0x004563F0 + 0x8C (sceAtSetOtStart), percorrida por sceAtGetOtAddr 0x002661C0; registros SCE_AT_DATA de 0xA0 bytes (itens SCE_AT_ITEM de 0xB0) vindos dos blocos AEV/ITA da sala | 15 | 9 | 7 | 8 batem, 7 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Colisão de cenário (SatMgr, EatMgr, cSat, cSatFile)](#colisao) | SatMgr 0x0041AF10 (personagens), EatMgr 0x0041AF30 (balas, objetos, câmera); SEck 0x0041B578; estáticos. Peças (cSat de 0xF0) no vetor de 20 vagas de cada gerente; a da sala é a primeira | 18 | 18 | 2 | 18 batem, 0 lidos, 0 divergem, 0 não conferíveis | lida |
| [Câmera](#camera) | olho 0x003CA220, alvo 0x003CA230, matriz visão-projeção 0x004327C0, transformação de tela 0x00432840; estáticos | 4 | 4 | 0 | 4 batem, 0 lidos, 0 divergem, 0 não conferíveis | lida |
| [Modelo visual (.bin) e objetos de cenário](#modelo_visual) | scrObjTbl 0x004568AC aponta para um vetor no heap de ponteiros cObj (105 na sala 0x0100); os cObj vivem no segundo gerente de objetos cObjMgr 0x00431D40 (cManager: vetor × 293 vagas de 0x4F0; o primeiro, 0x00431D20, tem 100); SMD em 0x004568A0; estáticos. Modelos no heap | 4 | 4 | 3 | 2 batem, 1 lidos, 0 divergem, 1 não conferíveis | lida |
| [Efeitos (EstSet, tabela Est)](#efeitos) | gerente em *0x004203A4; tabela Est em gerente+0x7400 (0xC por id); Esp em gerente+0x6000 | 1 | 1 | 0 | 1 batem, 0 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Controle (joystick)](#controle) | 0x00431948; estático | 1 | 1 | 0 | 0 batem, 1 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Eventos e cutscenes (Event, EventMgr, blocos EVS)](#eventos) | EventMgr (0x00205B90..0x00207470 nomeadas no índice); raiz dos dados não localizada | 0 | 0 | 0 | sem campos | não lida |
| [Arquivo de sala (blocos SMD/SMX, LIT, SAR, EFF, TEX, ITM/ETM/ETS, CAM, BLK, EVS/FSE/AEV/ITA)](#blocos_sala) | não localizada no PS2 (no GameCube, pG->pRoom e pCore) | 0 | 0 | 0 | sem campos | não lida |
| [Tabuleiro da maleta (pzlPlayer, pzlBoard, pzlPiece)](#pzl) | criado pela tela da maleta 0x0111F4E0 (módulo do menu); vive só com a tela aberta | 0 | 0 | 0 | sem campos | não lida |
| [Cabeçalho SNR2 do módulo realocável (.rel)](#snr2) | início de cada .rel (tabela de módulos +0x88) | 1 | 1 | 0 | 1 batem, 0 lidos, 0 divergem, 0 não conferíveis | parcial |
| [Tabela de tipos de inimigo (0x003C8F40)](#tipos_inimigo) | 0x003C8F40; estática | 0 | 0 | 0 | sem campos | não lida |
| **total** | | **163** | **150** | **58** | | 8 lidas, 9 parciais, 4 não lidas |

Legenda das provas: **decompilado** = lido no C decompilado do PS2; **vigia** = vigia de escrita do fork; **foto** = diferença entre fotos da memória; **ao_vivo** = lido ou escrito pelo canal com efeito conferido; **publica** = fonte pública conferida ao vivo; **gc** = nome ou papel vindo da decompilação do GameCube, sem prova no PS2.

<a id="pg"></a>
## Bloco global do jogo (pG, GLOBAL_WK)

- **Raiz:** 0x00425BA0 (apontado por 0x00325308); estático
- **Tamanho:** ≥ 0xB3B4 (o C decompilado lê até +0xB3B0)
- **Estado:** parcial

Estado global da partida: sala, vida, dificuldade, personagem, lista de inimigos da sala e sinalizadores. A decompilação do GameCube nomeia o equivalente (GLOBAL_WK), mas os deslocamentos do PS2 são outros; os nomes abaixo entre parênteses são os do GameCube quando o papel bate.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x5C` | u32 | sinalizadores de sistema | a função de dano testa o bit 0x40000000 (com pSys+8 == 0) e readEmList o bit 0x2000; nome não determinado | não lido | LifeDownSet2, readEmList | decompilado |
| `0x70` | s32 | não nomeado | readEmList recarrega a lista quando este valor é negativo e a lista mudou; papel não determinado | não lido | readEmList | decompilado |
| `0x7EB8` | u16 | sala (room_id) | byte baixo = sala, byte alto = estágio; chave de cRoomData::checkPassed e das tabelas por sala | troca de sala (não lida) | EmSetFromList2, readEmList, MercSysInitRoom, cRoomData::checkPassed e dezenas de funções | decompilado, ao_vivo |
| `0x7EC4` | u8 | dificuldade adaptativa (Game_level) | 0 a 10; fator do jogador 0,1·dif + 0,5; do inimigo 2,0 − 0,2·dif abaixo de 6, senão 1,0 − 0,03·(dif − 5) | não lido (GameAddPoint no GameCube) | LifeDownSet2 | decompilado, ao_vivo |
| `0x7ED5` | s8 | lista de inimigos carregada (em_list_no) | número do arquivo .esl em memória; −1 = nenhuma | readEmList | EmSetFromList2, readEmList | decompilado |
| `0x7ED6` | s16 | vida do jogador (pl_life) | 0 a 2400; 1200 no início | LifeDownSet2 (instrução 0x1C27FC), recuperação 0x119E48 | HUD, LifeDownSet2 | vigia, decompilado, ao_vivo |
| `0x7ED8` | s16 | vida máxima do jogador (pl_life_max) | teto da recuperação | não lido | 0x119E48, LifeDownSet2 | decompilado, ao_vivo |
| `0x7EDA` | s16 | vida da parceira (ashley_life) | 600 no início | LifeDownSet2 | LifeDownSet2 | decompilado, ao_vivo |
| `0x7EDC` | s16 | vida máxima da parceira | — | não lido | LifeDownSet2 | decompilado |
| `0x7EE8` | u8 | traje (pl_costume) | 0 a 5 | não lido | escolha da tabela de arquivos por tipo | publica |
| `0x7EEA` | u8 | personagem (pl_type) | 0 Leon, 1 Ashley, 2 Ada, 3 HUNK, 4 Krauser, 5 Wesker (nomes do GameCube); escolhe a tabela de arquivos de módulo | não lido | LifeDownSet2 (== 1), bancada/modulos.py | decompilado, ao_vivo |
| `0x7EED` | u8 | não nomeado | LifeDownSet2: com valor 2, o jogador de tipo 1 e a parceira de tipo 3 não perdem vida (reposta ao máximo). Era descrito como 'flags de invencibilidade de 64 bits em +0x7EE8'; o C mostra uma leitura de 8 bytes que testa só +0x7EEA e +0x7EED | não lido | LifeDownSet2 | decompilado |
| `0x7F60` | u32[12][8] | entradas da lista já usadas (Em_flg) | 32 bytes por lista de inimigos; um bit por entrada (bit 31 − índice da palavra); EmSetFromList2 recusa a entrada com o bit ligado. NÃO confirmado ao vivo: no estado 95, com as entradas 3..14, 18, 19, 29, 38 e 39 criadas, a lista 0 tinha só os bits 3, 4, 5, 16, 17 e 255 ligados (decodificação bit 31 − índice) — nem 'entradas criadas' nem 'entradas mortas' (3..8) nem a ordem de bits inversa explicam; relação não confirmada | não lido (morte do inimigo no GameCube) | EmSetFromList2 | decompilado |
| `0x8344` | EM_LIST[256] | lista de inimigos da sala (Em_list) | = 0x0042DEE4; 0x2000 bytes lidos do arquivo .esl pelo readEmList (cDvd, dorme pelo escalonador); zerada se a leitura falha | readEmList | EmSetFromList2, GetEmPtrFromList, GetEmIdFromList, EmListIsAlive | decompilado, ao_vivo |
| `0xB3B0` | s32 | não nomeado | readEmList recarrega a lista quando vale 3 | não lido | readEmList | decompilado |

Funções:

- `0x001C2618` LifeDownSet2 (dano): única função que desconta vida: jogador, parceira (ramo por tipo em cEm+0x11C) e inimigos
- `0x00276D60` readEmList: lê o .esl da sala para pG+0x8344 (dorme; não chamar pelo canal)
- `não indexado (objeto 0x004561F8)` cRoomData::checkPassed: sala já visitada; chamada por sala

Pendências:

- nomear +0x5C, +0x70, +0x7EED e +0xB3B0 pelo C (quem escreve)
- dinheiro (peseta), capítulo, tempo de jogo e sinalizadores de roteiro (Scenario_flg, Key_flg, Room_flg) no PS2: só os nomes do GameCube
- conferir ao vivo três campos sorteados (critério de aceite do S9-02)
- Em_flg (+0x7F60): a relação 'um bit por entrada criada' não bateu ao vivo; ler quem escreve no C

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x70` (estado 96): **bate** — lido 0; relação: negativo só quando a lista precisa ser recarregada
- sorteado `0x7ED6` (estado 96): **bate** — lido 1200; relação: cEm do jogador +0x4B0 = 1200; faixa 0..2400
- sorteado `0x7EDC` (estado 96): **bate** — lido 600; relação: ≥ vida da parceira 600
- divergência em `0x7F60` (estado 95): lido lista 0: 6 bits; relação: entradas criadas [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 29, 38, 39] ⊆ bits ligados [3, 4, 5, 16, 17, 255]

<a id="emmgr"></a>
## Gerente de personagens (EmMgr, cManager<cEm>)

- **Raiz:** 0x004203B0; estático. Ponteiro do jogador pPL em 0x004203D0
- **Tamanho:** 0x38
- **Estado:** lida

Pool fixo de 60 personagens de 0xED0 bytes; o vetor é alocado no heap (0x01789F40 no estado 91) e deve ser lido por +0 a cada sessão. Lista de vivos encadeada por cEm+0x4.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | ptr | pArray | vetor de personagens (heap) | arrayAlloc (gc) | EmSetEvent, EmSetFromList2, tudo que percorre personagens | decompilado, ao_vivo |
| `0x04` | u32 | nArray | 60 | arrayAlloc (gc) | at() (gc) | decompilado, ao_vivo |
| `0x08` | u32 | size | 0xED0 (passo do vetor) | construtor (gc) | at() (gc) | decompilado, ao_vivo |
| `0x0C` | u8 | flag | — | construtor | — | gc |
| `0x10` | ptr | pAlive | cabeça da lista de vivos (cEm+0x4 = próximo) | create/destroy | move, getEmPtr | gc, ao_vivo |
| `0x34` | u32 | Guid | próximo serial de modelo | construct | — | gc |

Funções:

- `0x00110378` função sem nome (criar vaga): recebe o EmMgr, pega uma vaga e constrói o cEm do tipo; para os tipos 0x0F e 0x25 é a 0x00117B00 (vagas do fim). Nomes não vêm da tabela de símbolos
- `0x001BD800` EmSetEvent(EM_LIST*): cria de uma struct avulsa; devolve o cEm ou errEm (0); marca a struct com 7 e chama o método virtual +0x2C do tipo
- `0x001BD538` EmSetFromList2(i, checar_usada): cria a entrada i da lista da sala; recusa se sala/estágio não batem, já criada, id 0 ou bit usado
- `0x001BD9E8 / 0x001BDAA8 / 0x001BDB38` GetEmPtrFromList / GetEmIdFromList / EmListIsAlive: consultas por índice da lista
- `0x002710C8` SceDestroyEm(tipo_ini, tipo_fim): destrói os personagens de uma faixa de tipos

Pendências:

- pSUB (parceira) e o restante do gerente (+0x14..+0x30) só com nome do GameCube

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x10` (estado 96): **bate** — lido 0x01795100; relação: cadeia por +0x4 tem 15 nós; vagas com be_flag vivo = 15
- sorteado `0x00` (estado 96): **bate** — lido 0x01789F40; relação: no heap; pPL 0x01789F40 = pArray (vaga 0 = jogador)
- sorteado `0x04` (estado 96): **bate** — lido 60; relação: 60 vagas

<a id="cem"></a>
## Personagem (cEm; cUnit → cCoord → cModel → cEm)

- **Raiz:** EmMgr+0 + 0xED0 × vaga; dinâmico (heap). Vaga 0 = jogador (pPL)
- **Tamanho:** 0xED0 por vaga (cEm mais a área livre do tipo, que começa em 0x3E0 no GameCube e não foi delimitada no PS2)
- **Estado:** parcial

Mesma estrutura para jogador, parceira, inimigos e objetos-inimigo (caixas, portas, árvores). Os deslocamentos do PS2 diferem dos do GameCube; só entram aqui os provados no PS2.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x000` | u32 | be_flag | bit 0 vivo; 0x200/0x400 pedido de morte (vivo = (be_flag & 0x201) == 1); bit 16 ligou nas duas mortes vistas; cabeçalho 0x0B002077 no jogador, 0x02002077 no aldeão | cManager (gc) | isAlive em todo laço de personagens (gc) | foto, vigia |
| `0x004` | ptr | pNext | próximo vivo (lista de EmMgr+0x10); a cadeia percorrida ao vivo cobre exatamente as vagas com be_flag vivo (15 e 35 nós) | cManager (gc) | cManager (gc) | gc, ao_vivo |
| `0x008` | ptr | tabela virtual | EmSetEvent chama *(vt+0x2C)(this + *(s16*)(vt+0x28)) logo após preencher a struct | construtor do tipo (inferido) | EmSetEvent | decompilado |
| `0x010` | mat4 | matriz de mundo (cCoord) | 4×4 de floats, conferida na foto inimigo1 (S8-00): três linhas unitárias da rotação em y (ang +0xD4 = 1,75 rad) e a linha +0x40 igual a pos; é o que S8-00 chamou de 'posição com cópias' | matUpdate a cada quadro (gc) | desenho, partes (inferido) | foto |
| `0x0C0` | vec3 | pos | posição dos pés em mm | EmSetEvent (lista ×10), movimento, colisão (encaixe no chão e empurrão de parede), canal (teleporte) | jumpCheck, EmSetEvent (distância ao jogador), tudo o mais (inferido) | decompilado, ao_vivo |
| `0x0D0` | vec3 | ang | rotação em radianos (lista × π/16384); +0xD4 = eixo y (frente) | EmSetEvent, movimento, canal | desenho, salto (jumpCheck) | decompilado, ao_vivo |
| `0x110` | ptr | pList (partes) | primeira cParts; em cada parte, +0x40 (4ª linha da matriz) é a posição de mundo, +0x80 o deslocamento local em relação ao pai (jogador: (0, 1076, 0) na raiz), +0x90 e +0xA0 iguais a +0x40 com o jogador parado (o papel de 'anterior' vem só do GameCube); +0x110 a próxima parte (lido ao vivo em 11/11; o teleporte de 30/10 escreveu posição de mundo também em +0x80 e funcionou, sem explicação medida) | partsWorldCalc a cada quadro (gc) | colisão (varredura anterior→atual), desenho | foto, ao_vivo |
| `0x11C` | u8 | id (tipo) | 0 jogador, 1 a 13 parceira e aliados, ≥ 16 inimigos (ramo da função de dano; tabela por tipo 0x003C8F40) | construtor do tipo (inferido) | LifeDownSet2 | decompilado, ao_vivo |
| `0x11D` | u8 | type (variante) | byte +2 da EM_LIST | EmSetEvent, EmSetFromList2 | rotinas do tipo (inferido) | decompilado |
| `0x130` | vec3 | pos_old | posição antes do movimento do quadro; EmSetEvent copia pos para cá | EmSetEvent, updateOldPos (gc) | colisão | decompilado, ao_vivo |
| `0x140` | vec3 | Wall_norm | normal da parede que empurrou o modelo; zero sem parede | colisão de cenário (gc) | movimento (gc) | gc, ao_vivo |
| `0x150` | ptr | pFloor_norm | normal do chão (câmera de ombro inclina com ela) | getFloor (gc) | câmera (gc) | gc, ao_vivo |
| `0x190` | ptr | pModelInfo | cModelInfo: +0xC model_addr (.bin do modelo em memória) | modelInit (gc) | desenho (inferido), terreno.py | ao_vivo |
| `0x290` | vec3 | cópia da posição | muda junto com +0xC0 nas fotos; papel não lido | não lido | não lido | foto |
| `0x2FC` | u16 | animação corrente | 118 andando, 184 reação ao tiro, 103 morto (aldeão); provisório | motionSet (gc) | — | foto |
| `0x320` | cAtariInfo | atari (corpo de colisão) | ver a estrutura cAtariInfo | cAtariInfo::init/move | SatMgr::check, EmAtCheck (gc) | decompilado, ao_vivo |
| `0x480` | ptr | base do módulo do tipo | — | construtor (inferido) | — | foto |
| `0x498` | f32 | l_pl | distância² ao jogador no plano xz (EmSetEvent calcula na criação) | EmSetEvent, move (gc) | rotinas do tipo (inferido) | decompilado |
| `0x49C` | f32 | l_sub | distância² à parceira; 1e16 na criação | EmSetEvent, move (gc) | rotinas do tipo (inferido) | decompilado |
| `0x4A4` | f32 | Guard_r | raio de guarda = EM_LIST+0x1A × 1000 | EmSetEvent, EmSetFromList2 | rotinas do tipo (inferido) | decompilado |
| `0x4AC` | u32 | flag | = EM_LIST+4 | EmSetEvent, EmSetFromList2 | rotinas do tipo (inferido) | decompilado |
| `0x4B0` | s16 | hp (vida) | = EM_LIST+8; aldeão 500, corvo 10, atores parados 1000, jogador 1200 (espelho da vida global) | EmSetEvent, LifeDownSet2 (instrução 0x1C2AA8) | LifeDownSet2, HUD do inimigo | vigia, decompilado, ao_vivo |
| `0x4B2` | s16 | hp_max | = EM_LIST+8 | EmSetEvent | — | decompilado, ao_vivo |
| `0x4BD` | u8 | set | = EM_LIST+3 | EmSetEvent | — | decompilado |
| `0x4C0` | u8 | emset_no | índice na lista da sala; 0xFF quando criado por EmSetEvent | EmSetEvent, EmSetFromList2 | bancada/personagens.py | decompilado, ao_vivo |
| `0x4CA` | u8 | Character | = EM_LIST+0xB | EmSetEvent | — | decompilado |
| `0x4D0` | struct | registro de acerto | preenchido por 0x001BB580; +0x3CA do registro (+0x89A da vaga) = dano restante | registrar_acerto | tratar_acerto_inimigo 0x01BADAF0 | vigia, decompilado |
| `0x710` | ptr | anexo (arma) | objeto preso no vetor de anexos 0x017BCDF0; zera na morte | não lido | não lido | foto |

Funções:

- `0x00246538` jumpCheck(cPlayer*): decide o salto de muro: parede 0x80000 nos dois ombros (±300 a 400 de altura, 600 à frente) e chão 3,8 m atrás dentro de ±1,5 m
- `0x01BADAF0 (módulo de inimigos)` tratar_acerto_inimigo: aplica o acerto de um tiro: calcular_dano_tiro 0x01BF4458 e LifeDownSet2

Pendências:

- cCoord (+0x10..+0xC0: matriz, escala, pai) só por nome do GameCube
- rotina r_no_0..3, Motion e LightInfo no PS2 não localizados
- área livre do tipo (trabalho do em10 etc.) não delimitada
- vetor de anexos 0x017BCDF0 (5 vagas): formato dado como igual, não lido

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x4A4` (estado 95): **bate** — lido 0; relação: EM_LIST[10]+0x1A × 1000 = 0
- sorteado `0x498` (estado 95): **bate** — lido 2.084e+10; relação: distância² xz ao jogador calculada 2.084e+10 (5 %; o jogo atualiza por quadro)
- sorteado `0x290` (estado 96): **bate** — lido [-96682, -295, -661]; relação: igual a pos
- observação: 17 cEm vindos da lista, 11 com vida > 0; afastamentos do ponto da lista (mm): [0, 0, 0, 0, 0, 4, 7, 10, 20, 33, 34, 44, 115, 422, 9018, 13136, 14945]

<a id="catariinfo"></a>
## Corpo de colisão do personagem (cAtariInfo, em cEm+0x320)

- **Raiz:** cEm+0x320
- **Tamanho:** 0x64 (Vec de 16 bytes no PS2)
- **Estado:** parcial

Layout do GameCube com o Vec de 12 bytes trocado pelo de 16: os deslocamentos abaixo foram conferidos ao vivo nos campos marcados.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | vec4 | m_offset | deslocamento em relação ao modelo | init (gc) | getPos (gc) | gc |
| `0x10` | f32 | m_radius | 400 no jogador (foto inimigo1: +0x330 da vaga 0 = 400,0) | cAtariInfo::move (interpola para +0x20 em +0x28 quadros), init/set (gc) | polySphereCk | decompilado, ao_vivo |
| `0x14` | f32 | m_radius2 | — | cAtariInfo::move (interpola para +0x24) | — | decompilado |
| `0x18` | f32 | m_height | meia altura | init (gc) | — | gc |
| `0x1C` | s16 | m_parts_no | parte que o corpo segue (+1), 0 = o modelo | init (gc) | getPos (gc) | gc |
| `0x1E` | u16 | m_flag | 0x1301 no jogador: 0x100 colide com cenário (Sca), 0x200 com personagens (Oba), bits 3-4 prioridade de empurrão, bit 0 linha | on/off/setPriority (gc) | SatMgr::check, EmAtCheck (gc) | ao_vivo |
| `0x20` | f32[2] | m_radius_n, m_radius2_n | raios-alvo da interpolação | set (gc) | cAtariInfo::move | decompilado |
| `0x28` | u16 | m_hokan | quadros restantes da interpolação dos raios | cAtariInfo::move (decrementa) | cAtariInfo::move | decompilado |
| `0x40` | vec4 | m_Pos | posição de mundo deste quadro (= cEm+0x360; foto inimigo1: pos com y + 876) | não lido no PS2 (EmAtCheck no GameCube); o move não escreve aqui | colisão | foto, ao_vivo |
| `0x50` | vec4 | m_oldPos | posição do quadro anterior (= cEm+0x370) | não lido no PS2 | colisão (varredura) | foto, ao_vivo |
| `0x60` | ptr | m_pList | próximo corpo da cadeia | init (gc) | DrawOba (gc) | gc |

Funções:

- `0x001A6078 / 0x001A60C8 / 0x001A6240 / 0x001A6348` cAtariInfo::init / set / move / setPriority: ciclo do corpo de colisão

Pendências:

- +0x2A stat, +0x2C pMod, +0x30 radius3 só por nome; quem escreve m_Pos/m_oldPos no PS2

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x50` (estado 96): **bate** — lido [-96682, 578, -661]; relação: igual a m_Pos parado
- sorteado `0x40` (estado 96): **bate** — lido [-96682, 578, -661]; relação: pos + (0, 874, 0)
- sorteado `0x28` (estado 96): **bate** — lido 0; relação: 0 quadros restantes com o jogador parado

<a id="em_list"></a>
## Entrada da lista de inimigos da sala (EM_LIST, 32 bytes)

- **Raiz:** pG+0x8344 + 0x20 × i (0x0042DEE4); arquivos emleon00..09.esl do AFS (emgirl* nas partes da Ashley)
- **Tamanho:** 0x20
- **Estado:** lida

O roteiro da sala cria a entrada i por EmSetFromList2(i); o mestre grava uma struct avulsa com o mesmo formato e chama EmSetEvent.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | u8 | be_flag | bit 0 vivo, bit 1 já criada (EmSetFromList2 recusa), bits 2/3 alternância; EmSetEvent grava 7; ao vivo (estado 96, nenhum cEm vindo da lista) havia entradas com 0x01 e 0x06: bit 0 não significa 'cEm vivo agora'; o que os bits significam não foi confirmado ao vivo | EmSetFromList2, EmSetEvent | EmSetFromList2 | decompilado |
| `0x01` | u8 | id (tipo) | 0 = vaga vazia; 0x0F e 0x25 nascem nas vagas do fim do vetor (alocador especial) | arquivo .esl | EmSetFromList2, EmSetEvent | decompilado, ao_vivo |
| `0x02` | u8 | type (variante) | → cEm+0x11D | arquivo | EmSetEvent | decompilado |
| `0x03` | u8 | set | → cEm+0x4BD | arquivo | EmSetEvent | decompilado |
| `0x04` | u32 | flag | → cEm+0x4AC | arquivo | EmSetEvent | decompilado |
| `0x08` | u16 | hp | → cEm+0x4B0 e +0x4B2 | arquivo | EmSetEvent | decompilado, ao_vivo |
| `0x0B` | u8 | Character | → cEm+0x4CA | arquivo | EmSetEvent | decompilado |
| `0x0C` | s16[3] | pos | centímetros (× 10 = mm) → cEm+0xC0 e +0x130 | arquivo | EmSetEvent | decompilado, ao_vivo |
| `0x12` | s16[3] | rot | × π/16384 rad → cEm+0xD0 | arquivo | EmSetEvent | decompilado |
| `0x18` | u16 | room | estágio << 8 \| sala; EmSetFromList2 exige igual a pG+0x7EB8 | arquivo | EmSetFromList2 | decompilado |
| `0x1A` | s16 | Guard_r | × 1000 → cEm+0x4A4 | arquivo | EmSetEvent | decompilado |
| `0x1C` | u8[4] | reserva | — | — | — | gc |

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x18` (estado 96): **bate** — lido ['0x00000100', '0x00000101', '0x00000102', '0x00000103', '0x00000104', '0x00000105', '0x00000106', '0x00000107', '0x00000108', '0x00000109', '0x0000010A', '0x0000010B', '0x0000010E']; relação: todas no estágio de pG+0x7EB8 (1)
- sorteado `0x0C` (estado 96): **bate** — lido 255 posições; x -8958..14235 cm; relação: dentro de ±300 m
- sorteado `0x03` (estado 96): **lido** — lido [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 26, 27, 31, 34, 35, 36, 37, 43]; relação: set
- observação: 255 entradas ocupadas, nenhuma criada em cEm: os cruzamentos com cEm ficam para um estado com inimigo da lista
- observação: 255 entradas ocupadas, 1 vazias; 17 criadas em cEm

<a id="citemmgr"></a>
## Inventário: gerenciador de itens (cItemMgr) e item

- **Raiz:** 0x003CE148; estático. Vetor de itens no heap (0x010F6540 no estado 91), lido por +0x14
- **Tamanho:** item de 14 bytes × 384 vagas
- **Estado:** lida

A maleta é um tabuleiro remontado a cada abertura a partir do vetor (pzlPlayer); a posição gravada no item é o centro da peça em meias-células.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x0C` | ptr | item equipado | ponteiro para a vaga do item equipado | equipar (inferido) | cItemMgr::bulletNumCurrent | decompilado, ao_vivo |
| `0x10` | u16 | id do item equipado | — | equipar (inferido) | — | decompilado |
| `0x14` | ptr | vetor de itens | 384 vagas de 14 bytes (heap) | construtor (inferido) | at, search, pzlPlayer::init | decompilado, ao_vivo |
| `0x18` | ptr | última vaga tocada | bancada/inventario.py aponta para a vaga dada | get | — | decompilado |
| `0x1C` | u32 | quantidade de vagas | 384 | construtor (inferido) | at | decompilado |
| `item+0x0` | u16 | id | 0x23 pistola, 0x04 balas de pistola, 0x05 erva verde, 0x7C faca, 0x35 lança-foguetes, 0xAC/0xAD tesouros ou chaves | construct | search, num, pzlPlayer::init | decompilado, ao_vivo |
| `item+0x2` | u16 | quantidade | reserva de munição no item de balas; 1 nas armas | get, reload | reload, HUD (inferido) | decompilado, ao_vivo |
| `item+0x4` | u8 | flags | bit 0 = vaga ocupada | construct | pzlPlayer::init | decompilado |
| `item+0x5` | u8 | dono | comparado com +0x13 do gerenciador | construct | pzlPlayer::init | decompilado |
| `item+0x6` | u16 | níveis | melhorias da arma em 4 bits cada | construct, loja (inferido) | arm (gc) | decompilado |
| `item+0x8` | u16 | balas no pente × 8 | valor >> 3; armas de carga (0x34, 0x37, 0x53) usam +0x6 | construct, reload, trigger | bulletNumCurrent (HUD) | decompilado, ao_vivo |
| `item+0xA` | u8[2] | centro da peça (x, y) | meias-células; canto = centro − centro da peça da tabela | pzlPlayer::save, dar_item_se_couber | pzlPlayer::init | decompilado, ao_vivo |
| `item+0xC` | u8 | orientação | 0 a 7 | pzlPlayer::save | pzlPlayer::init | decompilado |
| `item+0xD` | u8 | na maleta | 1 = tabuleiro da maleta, 0 = tabuleiro extra | pzlPlayer::save | pzlPlayer::init | decompilado, ao_vivo |

Funções:

- `0x00120450 / 0x001204F8 / 0x0011FC60 / 0x0011E960 / 0x0011FEC8` cItemMgr::bulletNumCurrent / bulletNum / reload / use / trigger: munição e uso
- `0x0011E630 / 0x0011DD88 / 0x0011E008 / 0x0011F0E0 / 0x0011E430` cItemMgr::get / construct / at / num / search: vetor de itens
- `0x00261898` dar_item_se_couber(id, qtd, 0): monta tabuleiro temporário, encaixa, chama get e grava a posição (provada pelo canal)
- `0x0025FD10 / 0x002601B0 / 0x002607D8 / 0x0025F438` pzlPlayer::init / save / putPiece; colocar_peca: tabuleiro da maleta
- `0x0011E610` somar_dinheiro(n): pesetas (provada pelo canal); o campo em pG não foi localizado

Pendências:

- item removido pelo jogo após aparecer (carga 0 na primeira gravação?)
- tipos de item 9 e 10 em +0x6/+0x8
- centro da peça girada (orientação 1)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x0C` (estado 96): **bate** — lido 0x010F654E; relação: vaga 1 do vetor tem id 0x00000023
- sorteado `item+0x6` (estado 96): **lido** — lido 0x00000000; relação: níveis da pistola
- sorteado `0x10` (estado 96): **bate** — lido 0x00000023; relação: igual ao id da vaga apontada por +0xC

<a id="tabelas_itens"></a>
## Tabelas de peças e de armas

- **Raiz:** peças 0x00326DE8 (ITEM_PIECE_INFO); armas 0x003A99C0 (43 entradas, contagem em 0x002F0200); alocações do inventário 0x00433F80; estáticas
- **Tamanho:** peça 0x58 bytes até o id 0xFFFF (64 entradas); arma 0x16 bytes
- **Estado:** lida

Dados fixos do executável: forma de cada item na maleta e capacidade do pente por nível.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `peça+0x0` | u16 | id | 0xFFFF encerra | executável | searchItemPieceData 0x0025E700 | decompilado, ao_vivo |
| `peça+0x4` | u8 | largura | — | executável | pzlPlayer::init | decompilado, ao_vivo |
| `peça+0x5` | u8 | altura | — | executável | pzlPlayer::init | decompilado, ao_vivo |
| `peça+0x8` | f32[2] | centro (x, y) | pistola 3×2 centro (1,0; 0,5) | executável | pzlPlayer::init | decompilado, ao_vivo |
| `peça+0x10` | u8[] | grade | '1' por célula; todas cheias | executável | — | decompilado |
| `arma+0x0` | u16 | id | — | executável | — | decompilado |
| `arma+0x3` | u8 | número da arma | lança-foguetes = 13 | executável | — | decompilado |
| `arma+0x4` | u8 | tipo | — | executável | — | decompilado |
| `arma+0x6` | u8 | id do item de munição | 0xFF = nenhum; pistola → 0x04 | executável | reload | decompilado |
| `arma+0x8` | u16[] | capacidade do pente por nível | pistola 10/13/16/19/22/25 | executável | construct, arm | decompilado, ao_vivo |

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `peça+0x4` (estado 96): **bate** — lido 3; relação: pistola 3
- sorteado `peça+0x10` (estado 96): **bate** — lido 111111; relação: largura × altura de '1'
- sorteado `arma+0x8` (estado 96): **bate** — lido [10, 13, 16, 19, 22, 25]; relação: 10/13/16/19/22/25

<a id="modulos"></a>
## Módulos de personagem (tabela de módulos, arquivos por tipo, SNR2)

- **Raiz:** tabela de módulos 0x00455E50 (4 entradas de 0x98); arquivos por tipo 0x00328458 (+tipo × 8; 0x003286D8 / 0x00328958 / 0x00328BD8 por modo de personagem); estáticas. Código e dados dos módulos no heap (mem_alloc)
- **Tamanho:** entrada 0x98
- **Estado:** lida

Cada tipo de personagem é um .dat (modelos) mais um .rel (código realocável SNR2) do BIO4DAT.AFS; só quatro ficam carregados; o jogo lê do disco na tela de loading, dormindo. O mestre carrega pelo mem_alloc e pela ligação do próprio jogo (bancada/modulos.py).

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x80` | u16 | tipo | 0 = vaga livre | carregador, bancada/modulos.py | SearchEmModule | decompilado, ao_vivo |
| `0x82` | u16 | flags | 1 .rel alocado, 2 ligado, 4 .dat alocado; InitModule libera os alocados; ao vivo a entrada do pl0e tinha só o bit 2 (ligado sem alocação por esta tabela) | carregador | InitModule | decompilado, ao_vivo |
| `0x84` | ptr | .dat | — | carregador | construtor do tipo (inferido) | decompilado, ao_vivo |
| `0x88` | ptr | .rel | — | carregador | ligador | decompilado, ao_vivo |
| `0x8C` | u32 | tamanho do .dat | arredondado a 0x800 | carregador | InitModule | decompilado |
| `0x90` | u32 | tamanho do .rel | arredondado a 0x800 | carregador | InitModule | decompilado |
| `0x94` | ptr | inicialização do objeto (EmInitFunc) | gravada por FUN_00262bb0 após ligar | FUN_00262bb0 | create do tipo | decompilado, ao_vivo |
| `arq+0x0` | u16 | índice do .dat no AFS | tabela por tipo | executável | carregador | decompilado, ao_vivo |
| `arq+0x2` | u16 | índice do .rel | — | executável | carregador | decompilado, ao_vivo |
| `arq+0x4` | u16 | alternativo | — | executável | — | decompilado |
| `arq+0x6` | u16 | usado | — | executável | — | decompilado |

Funções:

- `0x00229338` mem_alloc(tam, 0, 0, 1, 0xd, alin): alocador do jogo; NÃO confere limite (devolveu endereço sobre dados vivos em 30/10)
- `0x00262BB0` FUN_00262bb0 (registrar e ligar): realoca o .rel, chama a inicialização do módulo e grava +0x94; não dorme
- `0x00262570 / 0x00262D68` InitModule / SearchEmModule: liberar entrada / achar módulo residente
- `0x00262708` carregador do disco: dorme por TaskSleep: nunca pelo canal
- `0x002A56B8 (valida 0x002A4860, realoca 0x002A5108, aplica 0x002A4968, registra 0x002A54F8)` ligador SNR2: 35 funções sem nome em 0x2A40E0..0x2A5F68

Pendências:

- criação do tipo 2 (cSubLeon) deixa a thread perdida: ligação não termina
- cSubAda (pl12) não tem .dat próprio; o sistema de cenas prepara colisão e animação de outro modo (LC-18)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `arq+0x0` (estado 96): **bate** — lido [('0012', 440), ('002A', 560), ('0021', 524), ('000E', 428)]; relação: índice < 2628 e nome .dat no AFS: ['em12.dat', 'em2a.dat', 'em21.dat', 'pl0e.dat']
- sorteado `0x80` (estado 96): **bate** — lido ['0012', '002A', '0021', '000E']; relação: tipos vivos no vetor: ['0000', '000E', '0012', '0051', '0052', '0053', '0056']; ao menos um módulo residente tem personagem vivo
- sorteado `arq+0x6` (estado 96): **lido** — lido [1, 1, 1, 1]; relação: sem relação independente
- observação: tipo 0012: .rel em12.rel 444692 B no AFS; tabela +0x90 = 446464 (bate)
- observação: tipo 002A: .rel em2a.rel 48098 B no AFS; tabela +0x90 = 49152 (bate)
- observação: tipo 0021: .rel em21.rel 51905 B no AFS; tabela +0x90 = 53248 (bate)
- observação: tipo 000E: .rel pl0e.rel 57081 B no AFS; tabela +0x90 = 57344 (bate)

<a id="afs"></a>
## Arquivos da ISO (BIO4DAT.AFS)

- **Raiz:** ISO, setor 446273 (2048 bytes por setor)
- **Tamanho:** 2628 arquivos
- **Estado:** parcial

Cabeçalho 'AFS', contagem, pares (deslocamento, tamanho), nomes de 48 bytes no fim. Só os .dat/.rel de personagem e os .esl foram usados; os blocos da sala (SMD/SMX, LIT, SAR, EFF, TEX, ITM/ETM/ETS, CAM, BLK, EVS/FSE/AEV/ITA no GameCube) ainda não foram mapeados no PS2.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | char[4] | assinatura | 'AFS\0' | disco | cDvd (inferido) | ao_vivo |
| `0x04` | u32 | quantidade | 2628 | disco | — | ao_vivo |
| `0x08` | u32[2][n+1] | (deslocamento, tamanho) | última entrada aponta para os nomes | disco | bancada/modulos.py | ao_vivo |
| `nomes` | char[48][n] | nomes | 32 bytes de nome mais atributos | disco | bancada/modulos.py | ao_vivo |

Funções:

- `0x001B63F0 / 0x001B5C98 / 0x001B6060` cDvd::ReadCheck / FileExistCheck / ReadCancel: fila de leitura do disco (objeto 0x0041C138)
- `0x001B33E0; 0x0016BF18 / 0x0016BF20 / 0x0016BF28` DvdReadN; DVDOpenDir/ReadDir/CloseDir: leitura do disco

Pendências:

- mapa dos blocos do arquivo de sala no PS2 (SAR = colisão, SMD = objetos de cenário, ESL, EVS/AEV/ITA de roteiro)
- formato .tpl (texturas) para o conversor de modelos (LC-17)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x08` (estado 96): **bate** — lido última entrada (1537718272, 126144); relação: todas dentro da ISO; nomes = 48 × 2628 = 126144
- sorteado `0x00` (estado 96): **bate** — lido b'AFS\x00'; relação: lido na ISO
- sorteado `0x04` (estado 96): **bate** — lido 2628; relação: 2628

<a id="tarefas"></a>
## Tarefas e threads (escalonador do jogo)

- **Raiz:** tabela de tarefas 0x00451688 (20 entradas de 0x350); tarefa corrente em 0x00451680; semáforos do kernel 0x004558CC / 0x004558D0; estáticas
- **Tamanho:** entrada 0x350
- **Estado:** parcial

Cada tarefa do jogo é uma thread do kernel com semáforo; TaskSleep marca a tarefa corrente, sinaliza o escalonador e espera o próprio semáforo. Por isso uma função que dorme, chamada pela chamada remota, trava a thread sequestrada. Só o código foi lido; nada conferido ao vivo.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x04` | u8 | estado | TaskExec grava 1; TaskSleep grava (estado & 0x80) \| 2 | TaskExec, TaskSleep | SceExec, escalonador (inferido) | decompilado |
| `0x05` | u8 | tipo | 0x17 normal (TaskExec), 0x16 tarefa de roteiro (SceExec); escolhe o semáforo sinalizado em TaskSleep; ao vivo a vaga 6 tem 0x14 (função 0x001B59C8 → fila do disco cDvd 0x0041C138), valor não previsto pelo C lido | TaskExec, SceExec | TaskSleep | decompilado |
| `0x0C` | u32 | semáforo da tarefa | WaitSema em TaskSleep | criação | TaskSleep | decompilado |
| `0x10` | u8 | sinalizador (kind) | SceExec copia o da tarefa corrente ou grava 1 | SceExec | — | decompilado |
| `0x14` | u16 | contador de sono | quadros a dormir (TaskSleep) | TaskSleep | escalonador (inferido) | decompilado |
| `0x18` | u32 | argumento | 3º argumento de TaskExec | TaskExec | entrada da tarefa (inferido) | decompilado |
| `0x340` | ptr | função (cópia) | — | TaskExec | — | decompilado |
| `0x344` | ptr | função | 2º argumento de TaskExec | TaskExec | escalonador (inferido) | decompilado |

Funções:

- `0x00255F90 / 0x00256010 / 0x00256090 / 0x00256198` TaskExec(no, func, arg) / TaskSleep(quadros) / TaskChain / TaskKill: tarefas; TaskExec só prepara a entrada (0x002562B8 == 0), quem inicia é o escalonador
- `0x002746A8` SceExec(prioridade, func, arg, kind, lista, ...): tarefa de roteiro nas vagas 7..19 (tabela 0x0045679C, 0xC por vaga; listas por prioridade em 0x00456770); prioridade 0 chama a função direto
- `0x00274828 / 0x00274868 / 0x002748E0 / 0x002749F8` SceSleep / SceExit / SceKill / SceCTask: ciclo das tarefas de roteiro
- `0x0048A000` lista de tarefas do quadro: triplas (objeto, função 0x00257F98 ou 0x00258AC0, próxima): enumera os objetos ativos (foto S8-00)

Pendências:

- escalonador (0x002562B8, 0x002562E0) e o início de uma tarefa pendente (TaskExec numa vaga livre ficou pendente em 29/10)
- conferir a tabela ao vivo
- tipo 0x14 da vaga 6 (tarefa do disco): quem grava e o que muda no escalonador

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x14` (estado 96): **lido** — lido [1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1]; relação: quadros a dormir
- sorteado `0x0C` (estado 96): **bate** — lido [19, 20, 21, 22, 23, 24, 26, 35, 36, 37, 38]; relação: id de semáforo do kernel (pequeno)
- sorteado `0x340` (estado 96): **bate** — lido ['0x002177B0', '0x00257390', '0x0016BC50', '0x00257390', '0x00172AA8', '0x001B59C8', '0x00267AD8', '0x01188E60', '0x01187EA8', '0x011878F8', '0x01187BB0']; relação: cópia de +0x344
- divergência em `0x05` (estado 96): lido ['17', '17', '17', '17', '17', '17', '14', '16', '00', '00', '00', '00', '00', '00', '00', '00', '16', '16', '16', '16']; relação: 11 vagas com 0x16/0x17; outros valores vistos: [(6, '14', '0x001B59C8')]
- observação: tarefa corrente 0x451680 = 0x00452718 (na tabela)
- observação: tarefa corrente 0x451680 = 0x00451688 (na tabela)

<a id="cenas"></a>
## Sistema de cenas: áreas de roteiro (SceAt) e eventos (Event/EventMgr)

- **Raiz:** lista ordenada com cabeça em *0x004563F0 + 0x8C (sceAtSetOtStart), percorrida por sceAtGetOtAddr 0x002661C0; registros SCE_AT_DATA de 0xA0 bytes (itens SCE_AT_ITEM de 0xB0) vindos dos blocos AEV/ITA da sala
- **Tamanho:** 0xA0 por área
- **Estado:** parcial

Uma área de roteiro é um volume (AREA_HIT_DATA) com tipo, número, quem dispara e uma função executada como tarefa de roteiro (SceExec) quando o jogador entra. O cabeçalho do PS2 bate com o do GameCube até +0x5C (conferido em SceAtDataSet_exec e SceAtPtr); os dados por tipo começam em +0x60 no PS2. Os eventos (cutscenes, EventMgr::EvtReadExec) não foram lidos.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | u32 | tag | elo da lista ordenada: cabeça em *0x004563F0 + 0x8C, fim 0xFFFFFFFF; os nós acima da cabeça são as áreas (68 na sala 0x0100) | SceAtInit | sceAtGetOtAddr | gc, ao_vivo |
| `0x04` | AREA_HIT_DATA | area | volume do gatilho (0x30 bytes) | SceAtInit | SceAtHitCheck | gc |
| `0x34` | u8 | be_flg | bit 0 habilitada, bit 1 ativa, bit 2 alocada em tempo de execução (SceAtCreate*) | SceAtSetEnable | SceAtCheckEnable | gc |
| `0x35` | u8 | id (tipo da área) | 0 normal, 1 porta, 2 exec, 3 item, 4 sinalizador, 5 mensagem, 7 salto, 8 save, 9 sombra, 10 dano, 11 colisão de roteiro, 12 câmera, 13 campo, 14 agachar, 15 chave (SKEY), 16 escada, 17 usar, 18 esconder, 19 teleporte, 20 item-pai, 21 arame da Ada (nomes do GameCube; o 15 confere no PS2) | arquivo AEV (inferido) | SceAtDataSet_exec, SceAtExecute (inferido) | decompilado |
| `0x36` | u8 | no (número da área) | chave de SceAtPtr(no); itens do ITA + 0x80 | arquivo (inferido) | SceAtPtr | decompilado |
| `0x38` | u8 | trg_type | bits de estado que disparam (1/2/4), bit 3 botão de ação, bit 7 desativa após usar; SceAtDataSet_exec troca com cópia em +0x3B | SceAtDataSet_exec | SceAtExecute (inferido) | decompilado |
| `0x39` | u8 | target_type | 1 jogador, 2 inimigo, 8 parceira | arquivo | SceAtHitCheck | gc |
| `0x3A` | u8 | task_level | prioridade do SceExec (máx 0x14; 0 = chamar direto) | SceAtDataSet_exec | SceAtExecute (inferido) | decompilado |
| `0x3B` | u8 | trg_type_bak | — | SceAtDataSet_exec | SceAtDataReset (inferido) | decompilado |
| `0x3C` | ptr | pParam | argumento da função | SceAtDataSet_exec | SceAtExecute (inferido) | decompilado |
| `0x40` | ptr | pFunc | função da área (tarefa de roteiro) | SceAtDataSet_exec | SceAtExecute (inferido) | decompilado |
| `0x44` | u8 | priority | índice na tabela de ordenação (0..15) | arquivo | SceExec | gc |
| `0x45` | u8 | kind | sinalizador passado ao SceExec | SceAtDataSet_exec | SceExec (inferido) | decompilado |
| `0x4C` | ptr | pParent | modelo pai (a área acompanha) | SceAtSetParent | SceAtGetCenterPos | gc |
| `0x60` | u8[0x40] | dados por tipo | porta: posição, ângulo, estágio/sala destino, chave; item: posição, modelo, id, quantidade, sinalizador de salvamento; colisão de roteiro: pSat, pEat, atributos; tipo 15: +0x60 argumento, +0x64 função, +0x68 nível, +0x69 kind (lido no PS2) | arquivo, SceAtDataSet_* | função por tipo | gc |

Funções:

- `0x0026A750 / 0x0026A8A8` SceAtPtr(no) / SceAtDataSet_exec(no, nível, trg, func, arg, kind): achar e armar uma área: o 4º argumento vai para +0x40 (função) e o 5º para +0x3C (argumento); no tipo 15, +0x64 e +0x60
- `0x0026A9C8 / 0x0026AA80 / 0x0026AAB0 / 0x0026AAE0` SceAtSetEnable / SceAtCheckEnable / SceAtHitCheck / SceAtExecute: habilitar, testar e executar áreas
- `0x0026C458 / 0x0026C898 / 0x0026D790` SceAtCreateExecAt / SceAtCreateItemAt / SceAtSetItemModel: criar áreas e itens em tempo de execução (candidatas a ação do mestre)
- `0x0026B0C8 / 0x0026A868` SceAtExecRoomJump / SceAtSetDoorFunc: troca de sala por porta
- `0x00270328 / 0x00270570 / 0x00274F10; 0x00206280 / 0x00206740 / 0x00206EA0` SceEventStart / SceEventEnd / SceSetEventCancel; EventMgr::EvtReadExec / EvtFree / SetFunc: cutscenes: não lidas
- `0x002713C8 / 0x00270F00 / 0x00271F68 / 0x00272080` SceSetItemEvent / SceCheckEmAlive / SceSetChapterEnd / SceCamMove: roteiro de sala: não lidas

Pendências:

- AREA_HIT_DATA (+0x04..+0x34) e os dados por tipo no PS2
- onde a lista das áreas da sala fica em memória (raiz estática de sceAtSetOtStart)
- eventos (Event, EventMgr, blocos EVS) e como preparam colisão e animação dos personagens de cena (LC-18)
- sinalizadores de roteiro em pG (Scenario_flg, Room_flg, Key_flg) no PS2

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x45` (estado 96): **lido** — lido [0, 1, 2]; relação: kind
- sorteado `0x39` (estado 96): **bate** — lido [0, 1, 3]; relação: combinação de 1/2/8
- sorteado `0x44` (estado 96): **bate** — lido [2, 5, 8]; relação: 0..15
- observação: raiz *0x4563F0 = 0x00456270; lista a partir de 0x004562FC com 68 áreas (percorridas 83 nós)
- observação: raiz *0x4563F0 = 0x00456270; lista a partir de 0x004562FC com 69 áreas (percorridas 84 nós)

<a id="colisao"></a>
## Colisão de cenário (SatMgr, EatMgr, cSat, cSatFile)

- **Raiz:** SatMgr 0x0041AF10 (personagens), EatMgr 0x0041AF30 (balas, objetos, câmera); SEck 0x0041B578; estáticos. Peças (cSat de 0xF0) no vetor de 20 vagas de cada gerente; a da sala é a primeira
- **Tamanho:** cManager 0x20+; cSat 0xF0
- **Estado:** lida

Medido em S9-02-colisao-e-terreno: chão gerado do modelo visual e registrado como peça pelo create do jogo; aceito pelo jogo.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `mgr+0x00` | ptr | pArray | vetor de cSat | arrayAlloc (gc) | check, hitCheck2 | decompilado, ao_vivo |
| `mgr+0x04` | u32 | nArray | 20 vagas | — | — | ao_vivo |
| `mgr+0x08` | u32 | size | 0xF0 | — | — | ao_vivo |
| `mgr+0x10` | ptr | pAlive | lista de peças vivas | create/destroy | check (inferido) | ao_vivo |
| `mgr+0x1C` | u32 | type | 0 SatMgr, 1 EatMgr; copiado para SEck em hitCheck2; os filtros de atributo (PL_NOHIT 0x00400000 etc.) só valem com 0 | construtor (inferido) | hitCheck2 | decompilado, ao_vivo |
| `sat+0x00` | u32 | be_flag | bit 0 vivo | create/destroy | — | ao_vivo |
| `sat+0x0C` | ptr | vértices | Vec de 12 bytes no arquivo | create | polySphereCk | decompilado, ao_vivo |
| `sat+0x10` | ptr | normais | — | create | — | ao_vivo |
| `sat+0x14` | ptr | arestas | — | create | — | ao_vivo |
| `sat+0x18` | ptr | polígonos | 0x14 bytes: v0..v2, normal, e0..e2, reserva, status u32 (atributos: 0x40 chão, 0x80 parede, 0x80000 saltável, 0x400000 não colide com o jogador) | create | polySphereCk, hitCheck2 | decompilado, ao_vivo |
| `sat+0x1C` | u16 | nº de vértices | — | create | — | ao_vivo |
| `sat+0x1E` | u16 | nº de polígonos | máx 8192 (polyBit 0x400) | create | — | ao_vivo |
| `sat+0x20` | u16[3] | chão / rampa / parede | contagens por classe (polígonos ordenados assim) | create | getFloor (inferido) | ao_vivo |
| `sat+0x2A` | u16 | flag | 4 ativa, 2 arquivo alocado pelo gerente | create/destroy | check (inferido) | ao_vivo |
| `sat+0x30` | ptr | bloco raiz | blocos irmãos encadeados por deslocamento relativo em +0x20 | create | check (inferido) | ao_vivo |
| `sat+0x60` | ptr | arquivo (cSatFile) | cabeçalho 0x14 | create | — | ao_vivo |
| `sat+0x70` | mat4 | matriz | — | setMatrix (gc) | — | ao_vivo |
| `sat+0xB0` | mat4 | inversa | — | setMatrix (gc) | — | ao_vivo |

Funções:

- `0x001A32D0 / 0x001A33A8` cSatMgr::create(dados) / create(laje: pos, ang, 4 cantos de 16 B, altura, attr, 0x200): registrar peça (provadas pelo canal)
- `0x001A18E8 / 0x001A1D50 / 0x001A2500 / 0x001A26D0 / 0x001A38D0 / 0x001A3988 / 0x001A43B8` cSatMgr::check / checkAir / adjust / getFloor / hitCheck / hitCheck2 / destroy: consultas e empurrão
- `0x001A3490` polySphereCk: esfera do personagem (raio 400 a y+873) contra polígonos
- `0x002296D8` Mem_free: liberar arquivo de peça
- `0x00217358 / 0x00217418` FlrAtSetOnOff / FlrAtSetDefVal: áreas de chão do roteiro (não lidas)

Pendências:

- lacunas da LC-17: travessias de parede (1,4 % dos passos) e salto nativo (10 de 30 muros)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `sat+0x70` (estado 96): **bate** — lido translação [0, 0, 0]; relação: matriz × inversa = identidade
- sorteado `mgr+0x08` (estado 96): **bate** — lido 0x000000F0; relação: 0xF0
- sorteado `sat+0x1C` (estado 96): **bate** — lido 1249; relação: > 0
- observação: índices de vértice dos primeiros 256 polígonos < 1249: True

<a id="camera"></a>
## Câmera

- **Raiz:** olho 0x003CA220, alvo 0x003CA230, matriz visão-projeção 0x004327C0, transformação de tela 0x00432840; estáticos
- **Estado:** lida

Provada por projeção da raiz, pés e cabeça do inimigo dentro da caixa desenhada (S8-00). A matriz é escrita a cada quadro por quatro `sq` em 0x252830 (thread de jogo), que serve de âncora para a chamada remota.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x003CA220` | vec3 | olho | anda com o jogador e orbita quando ele vira | CameraMove (gc) | — | foto, ao_vivo |
| `0x003CA230` | vec3 | alvo | projeta no centro da tela; tronco do jogador | CameraMove (gc) | bancada/personagens.py (direção 'à frente') | foto, ao_vivo |
| `0x004327C0` | mat4 | visão-projeção | vetor-linha × matriz; w = distância ao olho em mm | 0x252830 (4 sq, todo quadro) | renderizador (inferido) | vigia, foto |
| `0x00432840` | mat4 | tela | x = 256 − (x/w)·1104,64; y = 224 + (y/w)·1706,67 (512×448) | — | — | foto |

Funções:

- `0x001006B8..0x00105D70; CameraMove 0x001AD418` CameraControl::* (33 funções nomeadas): cortes por sala (CAM), ombro (CameraQuasiFPS), mira, binóculo: não lidas

Pendências:

- cortes de câmera por sala e como forçar um corte (SceCamMove, CutCall)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x003CA220` (estado 96): **bate** — lido [-97478, 1470, 356]; relação: a 2749 mm do alvo
- sorteado `0x004327C0` (estado 96): **bate** — lido w = 2749; relação: w ≈ distância olho-alvo 2749
- sorteado `0x003CA230` (estado 96): **bate** — lido [-95389, 1045, -1382]; relação: a 1997 mm do jogador
- observação: matriz de tela: diagonal [-1104.64, 1706.67, -262144.0, 1.0]

<a id="modelo_visual"></a>
## Modelo visual (.bin) e objetos de cenário

- **Raiz:** scrObjTbl 0x004568AC aponta para um vetor no heap de ponteiros cObj (105 na sala 0x0100); os cObj vivem no segundo gerente de objetos cObjMgr 0x00431D40 (cManager: vetor × 293 vagas de 0x4F0; o primeiro, 0x00431D20, tem 100); SMD em 0x004568A0; estáticos. Modelos no heap
- **Estado:** lida

Formato da ferramenta pública RE4-PS2-BIN-TOOL, validado ao vivo (altura sob o jogador bate em 3 cm). É a base do terreno gerado (S9-02).

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `bin+0x00` | u8[0x50] | cabeçalho | assinatura em 0x30; +0xA nº de materiais; +0xC tabela de materiais (16 bytes cada, +12 ponteiro do nó) | arquivo | terreno.py | ao_vivo |
| `nó` | u16, u8, u8 | total, segmentos−1, ossos | — | arquivo | terreno.py | ao_vivo |
| `segmento` | cabeçalhos 0x10 | linhas e fator | pesos se h1[12]==0 && h1[14]>1; h2[0] nº de linhas; fator float em h2+0xC; linhas de 24 bytes com xyz int16; IndexComplement +14 == 0 fecha o triângulo da tira | arquivo | terreno.py | ao_vivo |
| `cObj+0x10` | mat4 | matriz do objeto | mundo = vértice × fator × matriz; a escala do objeto vem embutida na matriz (10 na maioria, 1 a 1,2 em alguns objetos da sala 0x0100); [3][3] = 1; cObj: +0 be_flag, +4 próximo, +8 tabela virtual | matUpdate (gc) | terreno.py | ao_vivo |

Funções:

- `0x00275E28 / 0x0022E7D8 / 0x0022E7A0` SetObjSmd / GetModelInfoAddr / GetPartsAddr: objetos de cenário e partes: não lidas

Pendências:

- texturas (.tpl) e conversor de modelo novo (LC-17)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `segmento` (estado 95): **não conferível** — lido —; relação: não decodificado nesta conferência
- sorteado `nó` (estado 96): **lido** — lido 0x20030818; relação: ponteiro do nó
- sorteado `bin+0x00` (estado 96): **bate** — lido modelo do jogador 0x00710C40: 7 materiais; relação: cabeçalho do .bin do jogador
- observação: cObjMgr 0x431D40: vetor 0x017E05F0 × 293 de 0x000004F0; 105 dos 105 objetos da tabela estão nele
- observação: SMD 0x4568A0 = 0x011C90A0; 105 ponteiros cObj no heap

<a id="efeitos"></a>
## Efeitos (EstSet, tabela Est)

- **Raiz:** gerente em *0x004203A4; tabela Est em gerente+0x7400 (0xC por id); Esp em gerente+0x6000
- **Estado:** parcial

EstSet(pai, idx=−1, &pos, &rot, est, kind, flags, u8) cria um efeito; est 0x58+id do objeto etc (caixa 0x59 kind 4, barril 0x6A kind 0, tocha kinds 1-3), 0x10 = conjunto da sala (162 kinds), 1 comum, 3 jogador, 0 sangue, 0xCD compartilhado. Provado pelo canal (efeito.py).

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `est+0x0` | u8[0xC] | entrada da tabela Est | entrada de 3 palavras: +0 dados, +4 índice (contagem u32 seguida de pares), +8 marcador (0xD6 = vazia); EspGetEstAddr 0x001B81F8 aceita id < 0xD7 e devolve dados + deslocamento do kind; 13 entradas usadas na sala 0x0100 | arquivo EFF (inferido) | EspGetEstAddr 0x001B81F8 | ao_vivo, decompilado |

Funções:

- `0x001FAF80` EstSet: criar efeito (provada pelo canal)
- `0x001FC058 / 0x002015A0 / 0x001FB408` GetEtcAddr / GetEtcFlgPtr / SetSstDispFlag: objetos etc e sinalizadores por sala: não lidas

Pendências:

- catálogo por dados dos kinds (a varredura visual foi abandonada)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `est+0x0` (estado 96): **bate** — lido gerente 0x0183ACC0: 13 de 215 entradas usadas; relação: EspGetEstAddr: 3ª palavra 0xD6 = vazia

<a id="controle"></a>
## Controle (joystick)

- **Raiz:** 0x00431948; estático
- **Estado:** parcial

Só o bit de tiro foi visto.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | u32 | botões | bit 0x80 = tiro; demais botões não mapeados | leitura do pad (inferido) | joyFireOn/Off/Trg 0x0024BE78..0x0024BF50 (inferido) | ao_vivo |

Pendências:

- mapear os botões (base do botão de salto da LC-17)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x00` (estado 96): **lido** — lido 0x00000000; relação: ninguém aperta botão nesta conferência

<a id="eventos"></a>
## Eventos e cutscenes (Event, EventMgr, blocos EVS)

- **Raiz:** EventMgr (0x00205B90..0x00207470 nomeadas no índice); raiz dos dados não localizada
- **Estado:** não lida

Nada lido no PS2. É o que prepara colisão e animação dos personagens de cena (LC-18).

Funções:

- `0x00206280 / 0x00206740 / 0x00206EA0 / 0x00206BE8; 0x00202DD8` EventMgr::EvtReadExec / EvtFree / SetFunc / SetBin; Event::RunEvtCancel: pontos de entrada pelo nome

Pendências:

- ler EvtReadExec e o formato dos blocos EVS

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sem campos no perfil: nada a conferir

<a id="blocos_sala"></a>
## Arquivo de sala (blocos SMD/SMX, LIT, SAR, EFF, TEX, ITM/ETM/ETS, CAM, BLK, EVS/FSE/AEV/ITA)

- **Raiz:** não localizada no PS2 (no GameCube, pG->pRoom e pCore)
- **Estado:** não lida

Só os nomes dos blocos vêm do GameCube. No PS2 só se leu o que já está em memória (colisão SAR, objetos SMD, lista ESL).

Pendências:

- achar o arquivo da sala no AFS e o índice de blocos em memória

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sem campos no perfil: nada a conferir

<a id="pzl"></a>
## Tabuleiro da maleta (pzlPlayer, pzlBoard, pzlPiece)

- **Raiz:** criado pela tela da maleta 0x0111F4E0 (módulo do menu); vive só com a tela aberta
- **Tamanho:** pzlPiece 0x2C; até 121 peças
- **Estado:** não lida

Lido só o suficiente para dar um item (peça: +0x14/+0x18 posição, +0x20 orientação, +0x24 item; tamanhos 10x6, 11x7, 12x8, 15x8, extra 6x12). Campos não tabelados.

Funções:

- `0x0025FD10 / 0x002601B0 / 0x002602A0 / 0x002607D8; 0x0025FB88` pzlPlayer::init / save / appendExtraPiece / putPiece; pzlBoard::cellState: lidas em 28/10 para a regra de encaixe

Pendências:

- tabelar pzlBoard e pzlPiece

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sem campos no perfil: nada a conferir

<a id="snr2"></a>
## Cabeçalho SNR2 do módulo realocável (.rel)

- **Raiz:** início de cada .rel (tabela de módulos +0x88)
- **Tamanho:** 16 palavras de cabeçalho
- **Estado:** parcial

Lido para o realocador próprio (bancada/snr2.py, validado contra os módulos vivos): +4 lista de realocações simbólicas e +8 contagem, +0xC tabela de seções de 12 bytes e +0x10 contagem, +0x18 entrada dos construtores, +0x20 tabela de ponteiros e +0x24 contagem, +0x28 alinhamento 0x80, +0x2C tamanho, +0x34 fluxo de realocações comprimido; seções tipo 0 endereço, 1 importado por nome, 2 e 3 definidos. Não tabelado campo a campo aqui.

| deslocamento | tipo | campo | significado | quem escreve | quem lê | prova |
|---|---|---|---|---|---|---|
| `0x00` | char[4] | assinatura | 'SNR2' no início de cada .rel residente (4 módulos conferidos ao vivo); as palavras seguintes são os campos do resumo (lista de realocações, contagens, tabela de seções), já com os ponteiros realocados para o heap | arquivo .rel do AFS; ponteiros realocados pelo ligador 0x002A56B8 | ligador 0x002A56B8 e bancada/snr2.py (inferido) | ao_vivo |

Funções:

- `0x002A56B8` ligador: ver módulos

Pendências:

- tabelar os 16 campos com quem lê cada um no ligador

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sorteado `0x00` (estado 96): **bate** — lido ['SNR2', 'SNR2', 'SNR2', 'SNR2']; relação: início de cada um dos 4 .rel residentes (tabela de módulos +0x88)
- observação: .rel do tipo 0012: SNR2 palavras ['0x01C054DC', '0x00001719', '0x01C16A08', '0x0000021A', '0x01C054BF', '0x01BF8E80', '0x01BF8E28']
- observação: .rel do tipo 002A: SNR2 palavras ['0x01C7170C', '0x00000126', '0x01C724D4', '0x0000011E', '0x01C716EF', '0x01C6AA20', '0x01C6A9C8']
- observação: .rel do tipo 0021: SNR2 palavras ['0x01CDC664', '0x0000012B', '0x01CDD468', '0x00000116', '0x01CDC647', '0x01CD5968', '0x01CD5910']
- observação: .rel do tipo 000E: SNR2 palavras ['0x01EF9718', '0x000001B2', '0x01EFAB70', '0x0000011F', '0x01EF96FD', '0x01EF2A18', '0x01EF29C0']

<a id="tipos_inimigo"></a>
## Tabela de tipos de inimigo (0x003C8F40)

- **Raiz:** 0x003C8F40; estática
- **Tamanho:** 64 entradas
- **Estado:** não lida

Tabela de salto por tipo usada pela função de dano; os 64 casos não foram nomeados.

Pendências:

- nomear os 64 casos pelo C decompilado (LifeDownSet2)

Conferência ao vivo (2026-11-11; estados 96, 95; sala 0x0100; semente 2026; aceite do cliente: pendente):

- sem campos no perfil: nada a conferir
- observação: primeiras 8 palavras: ['0x5F524D54', '0x00004843', '0x5F524D54', '0x004B4C43', '0x73696854', '0x54464320', '0x6E756620', '0x6F697463']

