# Catálogo de capacidades do jogo de abertura (Resident Evil 4, SLUS-21134 1.01)

Documento gerado de `perfis/memoria/SLUS-21134.json` (bloco `capacidades`, versão 1, 2026-11-11) por
`docs/fonte/gerar_capacidades.py`. Não editar à mão: mudar o perfil e gerar de novo. Entrega do card S9-03.

Catálogo de capacidades (S9-03): o que o mestre pode acionar no jogo de abertura pela chamada remota, por escrita de memória ou pela camada de cena, com argumentos, pré-condições, efeito, volta e risco. Fonte única: docs/fonte/gerar_capacidades.py gera docs/Capacidades-SLUS-21134.md daqui. Estados: 'provada' = chamada ou escrita com registro datado e comando em src/ (python -m iaemps2.bancada…) que roda hoje; 'provada_sem_ferramenta' = registro datado, sem ferramenta; 'provada_em_script' = só em script de reversa/colisao (uma execução, 30/10); 'candidata' = lida no C, nunca acionada; 'trava' = acionar congela o jogo ou não faz nada (causa registrada). Só 'provada' entra no sorteio do aceite e no catálogo de ações do S8-03. Substitui modulos.chamada_remota.funcoes_provadas.

**Regra geral:** funções que dormem pelo escalonador do jogo (carga do disco, SceSleep, TaskSleep) nunca são chamadas; chamadas só com o jogador parado; em partida só leitura e escrita de memória; estado salvo num slot do mestre antes de cada ação com efeito (o slot 95 é evidência da conferência do S9-02: copiar o .p2s antes de regravar).

## Resumo

| estado | quantas | o que significa |
|---|---|---|
| provada | 11 | provada (registro datado e ferramenta em src/) |
| provada_sem_ferramenta | 2 | provada, sem ferramenta em src/ |
| provada_em_script | 4 | provada só em script de reversa (uma execução) |
| candidata | 7 | candidata (lida no C, nunca acionada) |
| trava | 6 | trava (nunca acionar) |
| **total** | **30** | 11 entram no sorteio do aceite |

Critério de aceite do card (o cliente escolhe três capacidades ao acaso, sem semente, e cada uma funciona ao vivo
como descrita, com o jogo seguindo): **aceito em 2026-11-11: vida, esconder cenário e criar personagem vistos na tela pelo cliente (escolha delegada ao autor); a vida caiu de novo depois por golpe do aldeão criado, não pela escrita**. As escolhíveis são as de estado 'provada'. O que
está marcado 'trava' não entra no catálogo de ações do S8-03.

## Tabela

| capacidade | função | endereço | via | argumentos | trampolim | ferramenta | estado | prova | ensaio |
|---|---|---|---|---|---|---|---|---|---|
| [Criar um personagem à frente do jogador](#criar_personagem) | EmSetEvent | 0x001BD800 | chamada remota | 1 | não | python -m iaemps2.bancada.personagens criar <tipo> [--vida N] [--distancia M] [--variante V] | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Destruir todos os personagens de uma faixa de tipos](#destruir_tipo) | SceDestroyEm | 0x002710C8 | chamada remota | 2 | não | python -m iaemps2.bancada.modulos liberar <tipo> (chama antes de InitModule) | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Carregar da ISO o módulo de um tipo de personagem (sem tela de loading)](#carregar_modulo) | mem_alloc + registrar módulo + SearchEmModule | 0x00229338, 0x00262BB0, 0x00262D68 | chamada remota | 6 | sim | python -m iaemps2.bancada.modulos carregar <tipo> [--dat N --rel N] | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Liberar a entrada de um módulo residente](#liberar_modulo) | InitModule | 0x00262570 | chamada remota | 1 | não | python -m iaemps2.bancada.modulos liberar <tipo> | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Saber se o módulo de um tipo está residente](#consultar_modulo) | SearchEmModule | 0x00262D68 | chamada remota | 1 | não | python -m iaemps2.bancada.modulos listar (lê a tabela; a chamada é usada por carregar) | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Saber se a entrada i da lista da sala está viva](#lista_viva) | EmListIsAlive | 0x001BDB38 | chamada remota | 1 | não | python -m iaemps2.bancada.capacidades lista-viva <i> | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Quantidade de um item no inventário](#contar_item) | cItemMgr::num | 0x0011F0E0 | chamada remota | 2 | não | python -m iaemps2.bancada.capacidades contar-item <id> | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Dar um item pela função do próprio jogo (encaixa na maleta)](#dar_item_pela_funcao) | dar_item_se_couber | 0x00261898 | chamada remota | 3 | não | nenhuma: bancada/inventario.py dar escreve a vaga direto (ver dar_item_por_escrita) | provada_sem_ferramenta | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | — |
| [Somar pesetas](#somar_dinheiro) | somar_dinheiro | 0x0011E610 | chamada remota | 1 | não | nenhuma | provada_sem_ferramenta | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | — |
| [Mudar a vida do jogador](#vida) | escrita em pG+0x7ED6 | 0x0042DA76 | escrita de memória | 0 | não | python -m iaemps2.bancada.capacidades vida <valor> | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Teleportar o jogador](#teleporte) | escrita em cEm (vaga 0) | 0x004203B0 | escrita de memória | 0 | não | python -m iaemps2.bancada.capacidades teleporte <x> <y> <z> [--relativo] | provada | 29/10/2026 (receita +0x40/+0xC0/+0x130, com o cliente no controle) e 30/10/2026 (andarilho, 10 459 passos) | 11/11/2026 |
| [Dar um item escrevendo a vaga do inventário](#dar_item_por_escrita) | escrita no vetor de itens | 0x003CE148 | escrita de memória | 0 | não | python -m iaemps2.bancada.inventario dar <id> [--qtd N] | provada | 28/10/2026 (docs/medicoes/S8-01-vigia.md) | 11/11/2026 |
| [Esconder ou mostrar pedaços do cenário pela camada de cena](#esconder_cenario) | regra de cena (código 0x85) | — | camada de cena | 0 | não | python -m iaemps2.bancada.capacidades esconder <hash> [--segundos S] (materiais lista os hashes; mostrar remove) | provada | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |
| [Registrar uma peça de colisão (chão ou laje) no SatMgr](#criar_peca_de_colisao) | cSatMgr::create | 0x001A32D0, 0x001A33A8 | chamada remota | 6 | sim | reversa/colisao/terreno.py --criar e morro.py (fora de src/; terreno.py reconstruído e não reexecutado) | provada_em_script | 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/ | — |
| [Criar um efeito visual (partículas) num ponto](#criar_efeito) | EstSet | 0x001FAF80 | chamada remota | 10 | sim | reversa/colisao/efeito.py (fora de src/) | provada_em_script | 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/ | — |
| [Perguntar ao jogo se o jogador pode saltar o muro à frente](#testar_salto) | jumpCheck | 0x00246538 | chamada remota | 1 | não | reversa/colisao/salto_check.py (fora de src/) | provada_em_script | 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/ | — |
| [Devolver ao jogo um bloco do mem_alloc](#liberar_memoria) | Mem_free | 0x002296D8 | chamada remota | 1 | não | reversa/colisao/terreno.py (fora de src/) | provada_em_script | 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/ | — |
| [Criar uma área de roteiro em tempo de execução](#criar_area_de_roteiro) | SceAtCreateExecAt | 0x0026C458 | chamada remota | 14 | sim | nenhuma | candidata | — | — |
| [Criar um item de roteiro num ponto](#criar_item_no_chao) | SceAtCreateItemAt | 0x0026C898 | chamada remota | 7 | sim | nenhuma | candidata | — | — |
| [Habilitar ou desabilitar uma área de roteiro pelo número](#ligar_area) | SceAtSetEnable | 0x0026A9C8 | chamada remota | 2 | não | nenhuma | candidata | — | — |
| [Trocar a função e o argumento de uma área de roteiro](#armar_area) | SceAtDataSet_exec | 0x0026A8A8 | chamada remota | 6 | sim | nenhuma | candidata | — | — |
| [Criar a entrada i da lista da sala](#criar_da_lista) | EmSetFromList2 | 0x001BD538 | chamada remota | 2 | não | nenhuma | candidata | — | — |
| [Tirar vida de um personagem pela função de dano](#dar_dano) | LifeDownSet2 | 0x001C2618 | chamada remota | 4 | não | nenhuma | candidata | — | — |
| [Saber se um personagem ou entrada está vivo](#consultar_vivo) | SceCheckEmAlive / EmListSetAlive | 0x00270F00, 0x001BDAD8 | chamada remota | 2 | não | nenhuma | candidata | — | — |
| [Tocar um evento (cutscene)](#tocar_cutscene) | EventMgr::EvtReadExec | 0x00206280 | chamada remota | 4 | não | nenhuma | trava | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | — |
| [Trocar de sala por porta](#trocar_sala) | SceAtExecRoomJump | 0x0026B0C8 | chamada remota | 5 | sim | nenhuma | trava | — | — |
| [Carregar módulo pelo carregador do jogo](#carregar_modulo_pelo_jogo) | carregador do disco | 0x00262708 | chamada remota | 1 | não | nenhuma | trava | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | — |
| [Reler a lista de inimigos da sala do disco](#recarregar_lista) | readEmList | 0x00276D60 | chamada remota | 1 | não | nenhuma | trava | — | — |
| [Iniciar uma tarefa do escalonador](#iniciar_tarefa) | TaskExec | 0x00255F90 | chamada remota | 3 | não | nenhuma | trava | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | — |
| [Criar personagem de tipo sem módulo residente](#criar_sem_modulo) | EmSetEvent | 0x001BD800 | chamada remota | 1 | não | nenhuma | trava | 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md) | 11/11/2026 |

## Provada (registro datado e ferramenta em src/)

<a id="criar_personagem"></a>
### Criar um personagem à frente do jogador

- **Função:** EmSetEvent (0x001BD800); símbolo: `EmSetEvent__FP7EM_LIST`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** ponteiro para uma EM_LIST de 32 bytes na área do mestre (tipo em +1, +4 = 1, vida em +8, posição em cm em +0xC, sala em +0x18, +0x1A = 1)
- **Ferramenta:** python -m iaemps2.bancada.personagens criar <tipo> [--vida N] [--distancia M] [--variante V]
- **Pré-condições:**
  - módulo do tipo residente (bancada/modulos.py listar; carregar se não estiver)
  - tipo que obedece à posição: 0x12, 0x15, 0x23, 0x28, 0x2A, 0x0E, 0x0F; 0x03 e 0x04 nascem em ponto fixo próprio
  - jogador parado (chamada imediata, não ancorada)
  - salva o estado no slot 95 antes
  - conferir o retorno de carregar_modulo antes de criar: criar sem módulo congela o jogo (reproduzido em 11/11)
- **Efeito visível:** o personagem nasce a 2 m à frente, na direção da câmera, e anda; devolve a vaga no vetor
- **Como desfazer:** não provado por personagem: SceDestroyEm apaga o tipo inteiro; recarregar o estado salvo é a volta provada
- **Risco / causa da trava:** tipo sem módulo residente congela o jogo (o carregador dorme); tipo 2 (cSubLeon) deixa a thread perdida; cSubAda (pl12) nasce e o jogo congela segundos depois na colisão; 0x25 desenha errado; os módulos de personagem disputam vagas de textura (cabelo do Leon trocado com pl10)
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); aldeões 0x12 (quatro), corvos, 0x2A, 0x21, lanchas 0x0E/0x0F criados e andando; 8 a 17 ms
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); aldeão 0x12 criado a 3 m em 14 ms (vaga 13), andou; estado 95 regravado pela ferramenta e restaurado da cópia depois

<a id="destruir_tipo"></a>
### Destruir todos os personagens de uma faixa de tipos

- **Função:** SceDestroyEm (0x002710C8); símbolo: `SceDestroyEm__Fii`
- **Via:** chamada remota; 2 argumentos; trampolim desnecessário
- **Argumentos:** tipo inicial, tipo final (inteiros)
- **Ferramenta:** python -m iaemps2.bancada.modulos liberar <tipo> (chama antes de InitModule)
- **Pré-condições:**
  - nenhum personagem da faixa em uso pelo jogador (a lancha com o cliente em cima congelou o jogo)
- **Efeito visível:** todos os personagens da faixa somem
- **Como desfazer:** recriar com criar_personagem; ou recarregar o estado salvo
- **Risco / causa da trava:** apaga o tipo inteiro, não um personagem; destruir o que o jogador usa congela
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); usada ao liberar módulos (em25, pl0f) antes de InitModule
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); SceDestroyEm(0x21, 0x21) dentro de liberar 0x21: sem personagem do tipo vivo, jogo seguiu

<a id="carregar_modulo"></a>
### Carregar da ISO o módulo de um tipo de personagem (sem tela de loading)

- **Função:** mem_alloc + registrar módulo + SearchEmModule (0x00229338, 0x00262BB0, 0x00262D68); símbolo: `mem_alloc__FUiPCcibUiUi; FUN_00262bb0; SearchEmModule__FUc`
- **Via:** chamada remota; 6 argumentos; trampolim necessário
- **Argumentos:** mem_alloc(tamanho, nome, 0, 1, 0xD, alinhamento) por trampolim de 7 instruções (a0 = tamanho, os outros fixos); registrar(entrada da tabela 0x455E50); SearchEmModule(tipo)
- **Ferramenta:** python -m iaemps2.bancada.modulos carregar <tipo> [--dat N --rel N]
- **Pré-condições:**
  - vaga livre na tabela de módulos (4; liberar uma antes)
  - memória do jogo para .dat e .rel (mem_alloc não confere limite)
  - ISO acessível (lê os dois arquivos do BIO4DAT.AFS)
  - memória livre no heap do jogo: mem_alloc devolve 0 quando não cabe (em15.dat de 3,6 MB não coube na sala 0x0100 em 11/11)
- **Efeito visível:** o tipo passa a ter módulo residente; criar_personagem funciona para ele
- **Como desfazer:** liberar_modulo (InitModule) depois de destruir os personagens do tipo
- **Risco / causa da trava:** mem_alloc devolveu endereço sobre dados vivos em 30/10 (queda do jogo): conferir a faixa devolvida; tipo 2 (cSubLeon) não termina a ligação; módulos de personagem trocam texturas entre si
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); pl11, pl14, pl0e, pl0f, em25 e pl12 carregados e confirmados por SearchEmModule
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); carregar 0x15 na sala 0x0100: mem_alloc(0x376000) devolveu 0 (sem memória para o em15.dat de 3,6 MB com a sala de 5,2 MB carregada); a ferramenta parou com erro sem tocar no jogo. Carga de módulo grande nesta sala não cabe

<a id="liberar_modulo"></a>
### Liberar a entrada de um módulo residente

- **Função:** InitModule (0x00262570); símbolo: `InitModule__FP10MODULE_DAT`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** ponteiro para a entrada de 0x98 bytes na tabela 0x455E50
- **Ferramenta:** python -m iaemps2.bancada.modulos liberar <tipo>
- **Pré-condições:**
  - destruir antes os personagens do tipo (SceDestroyEm)
  - nunca o tipo com que o jogador interage
- **Efeito visível:** a vaga da tabela fica livre; .dat e .rel liberados pelo jogo
- **Como desfazer:** carregar_modulo de novo
- **Risco / causa da trava:** liberar com personagem vivo do tipo: comportamento não lido
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); liberações antes de carregar os tipos de teste
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); entrada 2 (tipo 0x21) liberada; tabela com 3 módulos depois

<a id="consultar_modulo"></a>
### Saber se o módulo de um tipo está residente

- **Função:** SearchEmModule (0x00262D68); símbolo: `SearchEmModule__FUc`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** tipo (u8); devolve a entrada da tabela ou 0
- **Ferramenta:** python -m iaemps2.bancada.modulos listar (lê a tabela; a chamada é usada por carregar)
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** só consulta
- **Como desfazer:** nada a desfazer
- **Risco / causa da trava:** nenhum conhecido
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); confirmação de cada módulo carregado
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); modulos listar: em12, em2a, em21, pl0e residentes

<a id="lista_viva"></a>
### Saber se a entrada i da lista da sala está viva

- **Função:** EmListIsAlive (0x001BDB38); símbolo: `EmListIsAlive__FUi`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** índice na EM_LIST (0..255); devolve 0 ou 1
- **Ferramenta:** python -m iaemps2.bancada.capacidades lista-viva <i>
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** só consulta
- **Como desfazer:** nada a desfazer
- **Risco / causa da trava:** nenhum conhecido
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); primeira prova da chamada remota: EmListIsAlive(15) = 1 em 17 ms
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); EmListIsAlive(3) = 0 e (20) = 1: bate com o bit 0 da be_flag das entradas lidas no S9-02

<a id="contar_item"></a>
### Quantidade de um item no inventário

- **Função:** cItemMgr::num (0x0011F0E0); símbolo: `num__8cItemMgrUs`
- **Via:** chamada remota; 2 argumentos; trampolim desnecessário
- **Argumentos:** this = 0x003CE148, id do item (u16); devolve a contagem
- **Ferramenta:** python -m iaemps2.bancada.capacidades contar-item <id>
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** só consulta
- **Como desfazer:** nada a desfazer
- **Risco / causa da trava:** nenhum conhecido
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); cItemMgr::num(pistola) = 1
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); cItemMgr::num(0x23) = 1, (0x04) = 15: bate com o inventário lido

<a id="vida"></a>
### Mudar a vida do jogador

- **Função:** escrita em pG+0x7ED6 (0x0042DA76); símbolo: `pl_life (s16)`
- **Via:** escrita de memória; 0 argumentos; trampolim desnecessário
- **Argumentos:** valor 0..vida máxima (pG+0x7ED8)
- **Ferramenta:** python -m iaemps2.bancada.capacidades vida <valor>
- **Pré-condições:**
  - respeitar a vida máxima
  - fora de evento (SceEventStart guarda o estado de dano do jogador)
- **Efeito visível:** a barra de vida muda na hora
- **Como desfazer:** escrever o valor anterior
- **Risco / causa da trava:** zero deve matar o jogador (não medido); a ferramenta limita a 0..máxima
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); vida cheia escrita em 0x0042DA76
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); 1200 → 1100 → 1200, relida igual

<a id="teleporte"></a>
### Teleportar o jogador

- **Função:** escrita em cEm (vaga 0) (0x004203B0); símbolo: `EmMgr lido ao vivo (vetor e passo); na vaga 0: pos +0xC0, pos_old +0x130 e, em cada parte da cadeia +0x110, +0x80/+0x90/+0xA0`
- **Via:** escrita de memória; 0 argumentos; trampolim desnecessário
- **Argumentos:** posição em mm (x, y, z)
- **Ferramenta:** python -m iaemps2.bancada.capacidades teleporte <x> <y> <z> [--relativo]
- **Pré-condições:**
  - ponto do chão original ou até 3 m acima (árvores têm caixa de colisão enorme e empurram dezenas de metros)
  - escrever também as partes, senão a varredura de parede arrasta o jogador até a primeira parede no caminho
- **Efeito visível:** o jogador aparece no ponto
- **Como desfazer:** escrever a posição anterior
- **Risco / causa da trava:** ponto dentro de objeto é rejeitado (empurrado para longe); +0x80 é deslocamento local e foi escrito com posição de mundo: funcionou sem explicação medida
- **Prova:** 29/10/2026 (receita +0x40/+0xC0/+0x130, com o cliente no controle) e 30/10/2026 (andarilho, 10 459 passos); duas receitas; a do andarilho é a completa
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); +1 m em x e volta: o jogo encaixou y no chão (125 mm do pedido)

<a id="dar_item_por_escrita"></a>
### Dar um item escrevendo a vaga do inventário

- **Função:** escrita no vetor de itens (0x003CE148); símbolo: `cItemMgr +0x14 vetor, +0x18 última vaga`
- **Via:** escrita de memória; 0 argumentos; trampolim desnecessário
- **Argumentos:** id, quantidade; a ferramenta escolhe a vaga e o canto na maleta
- **Ferramenta:** python -m iaemps2.bancada.inventario dar <id> [--qtd N]
- **Pré-condições:**
  - lugar livre na maleta sem girar
  - id com dados de peça na tabela 0x00326DE8
- **Efeito visível:** o item aparece na maleta ao abrir
- **Como desfazer:** não provado; recarregar o estado salvo
- **Risco / causa da trava:** item removido pelo jogo após aparecer numa prova (carga 0 na primeira gravação); tipos 9 e 10 não tratados
- **Prova:** 28/10/2026 (docs/medicoes/S8-01-vigia.md); munição exata e itens dados; validado contra o decompilado
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); não ensaiado em 11/11 (prova de 28/10)

<a id="esconder_cenario"></a>
### Esconder ou mostrar pedaços do cenário pela camada de cena

- **Função:** regra de cena (código 0x85) (sem endereço); símbolo: `camada de cena do fork`
- **Via:** camada de cena; 0 argumentos; trampolim desnecessário
- **Argumentos:** hash da textura ou da forma, duração
- **Ferramenta:** python -m iaemps2.bancada.capacidades esconder <hash> [--segundos S] (materiais lista os hashes; mostrar remove)
- **Pré-condições:**
  - assinaturas da cena conhecidas (S7-01)
- **Efeito visível:** o pedaço some da tela pelo tempo pedido
- **Como desfazer:** cena_limpar
- **Risco / causa da trava:** nenhum visto
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); cenário escondido por 20 s (45 materiais)
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); regra no material 092c951410a6beda (área 2 111 688) por 5 s e removida; estatística da regra conferida (ver ferramenta)

## Provada, sem ferramenta em src/

<a id="dar_item_pela_funcao"></a>
### Dar um item pela função do próprio jogo (encaixa na maleta)

- **Função:** dar_item_se_couber (0x00261898); símbolo: `FUN_00261898 (sem símbolo)`
- **Via:** chamada remota; 3 argumentos; trampolim desnecessário
- **Argumentos:** id do item, quantidade, 0
- **Ferramenta:** nenhuma: bancada/inventario.py dar escreve a vaga direto (ver dar_item_por_escrita)
- **Pré-condições:**
  - lugar livre na maleta (a função recusa se não couber)
  - tipos de item 9 e 10 (+0x6/+0x8) não tratados
- **Efeito visível:** o item aparece na maleta
- **Como desfazer:** não provado (remover item não foi chamado); recarregar o estado salvo
- **Risco / causa da trava:** nenhum visto nas três provas
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); erva, 10 balas e a arma 0x2C
- **Ensaio:** —; não ensaiado

<a id="somar_dinheiro"></a>
### Somar pesetas

- **Função:** somar_dinheiro (0x0011E610); símbolo: `FUN_0011e610 (sem símbolo)`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** quantidade (inteiro)
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** o dinheiro sobe na tela
- **Como desfazer:** não provado (valor negativo não foi chamado); o campo em pG não foi localizado
- **Risco / causa da trava:** nenhum visto
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); 5000 pesetas
- **Ensaio:** —; não ensaiado

## Provada só em script de reversa (uma execução)

<a id="criar_peca_de_colisao"></a>
### Registrar uma peça de colisão (chão ou laje) no SatMgr

- **Função:** cSatMgr::create (0x001A32D0, 0x001A33A8); símbolo: `create__7cSatMgrUiUiPC6tagVecT3Uc; create__7cSatMgrPC6tagVecN21fUiUi`
- **Via:** chamada remota; 6 argumentos; trampolim necessário
- **Argumentos:** dados: (this, arquivo cSatFile, flag, pos, rot, type); laje: (this, pos, ang, 4 cantos de 16 bytes, altura float, attr, 0x200); ambas por trampolim
- **Ferramenta:** reversa/colisao/terreno.py --criar e morro.py (fora de src/; terreno.py reconstruído e não reexecutado)
- **Pré-condições:**
  - 20 vagas por gerente; liberar as próprias (be_flag e flag = 0) antes de recriar
  - arquivo em faixa de memória zerada medida (0x1F00000..0x1FF0000, 0xAB0000..0xDF0000), não pelo mem_alloc
  - jogador parado durante a chamada
- **Efeito visível:** o jogador anda sobre o chão novo
- **Como desfazer:** zerar be_flag e flag da peça e Mem_free do arquivo
- **Risco / causa da trava:** chamada durante a partida coincidiu com duas quedas; peça errada prende ou derruba o jogador
- **Prova:** 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/; chão de 7148 triângulos e laje; o cliente subiu o morro
- **Ensaio:** —; não ensaiado

<a id="criar_efeito"></a>
### Criar um efeito visual (partículas) num ponto

- **Função:** EstSet (0x001FAF80); símbolo: `EstSet__FP6cModelUiP6tagVecT2UiUcUsUcPvP14ESPSEQ_CONTROL`
- **Via:** chamada remota; 10 argumentos; trampolim necessário
- **Argumentos:** (modelo ou 0, -1, pos, rot, conjunto est, kind, flags, 0, 0, 0) por trampolim
- **Ferramenta:** reversa/colisao/efeito.py (fora de src/)
- **Pré-condições:**
  - conjunto e kind existentes na tabela Est do gerente (*0x4203A4 + 0x7400)
- **Efeito visível:** o efeito aparece no ponto
- **Como desfazer:** não lido (o efeito acaba sozinho)
- **Risco / causa da trava:** kind inexistente: comportamento não lido
- **Prova:** 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/; efeitos criados na frente do jogador
- **Ensaio:** —; não ensaiado

<a id="testar_salto"></a>
### Perguntar ao jogo se o jogador pode saltar o muro à frente

- **Função:** jumpCheck (0x00246538); símbolo: `FUN_00246538 (sem símbolo; recebe cPlayer*)`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** ponteiro do jogador (vaga 0)
- **Ferramenta:** reversa/colisao/salto_check.py (fora de src/)
- **Pré-condições:**
  - jogador parado
  - muro contínuo ≥ 60 cm marcado 0x80000 e chão 3,8 m atrás
- **Efeito visível:** só consulta (0 ou 1)
- **Como desfazer:** nada a desfazer
- **Risco / causa da trava:** nenhum visto
- **Prova:** 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/; 10 de 30 muros aceitos
- **Ensaio:** —; não ensaiado

<a id="liberar_memoria"></a>
### Devolver ao jogo um bloco do mem_alloc

- **Função:** Mem_free (0x002296D8); símbolo: `Mem_free__FPv`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** ponteiro
- **Ferramenta:** reversa/colisao/terreno.py (fora de src/)
- **Pré-condições:**
  - bloco vindo do mem_alloc e sem uso
- **Efeito visível:** memória liberada
- **Como desfazer:** nada a desfazer
- **Risco / causa da trava:** liberar bloco em uso deve derrubar o jogo (não medido)
- **Prova:** 30/10/2026, uma execução, scripts em reversa/colisao (docs/medicoes/S9-02-colisao-e-terreno.md); sem ferramenta em src/; arquivos de peça liberados
- **Ensaio:** —; não ensaiado

## Candidata (lida no C, nunca acionada)

<a id="criar_area_de_roteiro"></a>
### Criar uma área de roteiro em tempo de execução

- **Função:** SceAtCreateExecAt (0x0026C458); símbolo: `SceAtCreateExecAt__FP6cModelP6tagVecfUcUcUcUcffUc9SCE_LEVELPvT11_Uc`
- **Via:** chamada remota; 14 argumentos; trampolim necessário
- **Argumentos:** 14 argumentos com floats: exige trampolim próprio
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - ler a função inteira antes (aloca 0xA0 pelo mem_calloc e encadeia na lista de prioridade)
- **Efeito visível:** não observado
- **Como desfazer:** não lido
- **Risco / causa da trava:** não lido
- **Prova:** nenhuma; só o índice de símbolos; nunca chamada
- **Ensaio:** —; não ensaiado

<a id="criar_item_no_chao"></a>
### Criar um item de roteiro num ponto

- **Função:** SceAtCreateItemAt (0x0026C898); símbolo: `SceAtCreateItemAt__FRC6tagVecUsUiSciP6cModels`
- **Via:** chamada remota; 7 argumentos; trampolim necessário
- **Argumentos:** (pos, id do item, u32, s8, int, modelo, s16): exige trampolim
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - ler a função inteira antes
- **Efeito visível:** não observado
- **Como desfazer:** não lido
- **Risco / causa da trava:** não lido
- **Prova:** nenhuma; só o índice de símbolos; nunca chamada
- **Ensaio:** —; não ensaiado

<a id="ligar_area"></a>
### Habilitar ou desabilitar uma área de roteiro pelo número

- **Função:** SceAtSetEnable (0x0026A9C8); símbolo: `SceAtSetEnable__FUib`
- **Via:** chamada remota; 2 argumentos; trampolim desnecessário
- **Argumentos:** número da área (+0x36), 1 ou 0
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - área existente na lista (*0x4563F0+0x8C)
- **Efeito visível:** não observado (lido: liga o bit 0 de +0x34; tipos 3 e 11 têm rotina própria)
- **Como desfazer:** chamar com o valor oposto
- **Risco / causa da trava:** não lido
- **Prova:** nenhuma; lida no C em 11/11
- **Ensaio:** —; não ensaiado

<a id="armar_area"></a>
### Trocar a função e o argumento de uma área de roteiro

- **Função:** SceAtDataSet_exec (0x0026A8A8); símbolo: `SceAtDataSet_exec__FUi9SCE_LEVELUiPvT3Uc`
- **Via:** chamada remota; 6 argumentos; trampolim necessário
- **Argumentos:** (número, nível, trg_type, função, argumento, kind): exige trampolim
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - área existente
- **Efeito visível:** não observado
- **Como desfazer:** não lido
- **Risco / causa da trava:** função errada executada pelo escalonador de roteiro deve derrubar o jogo (não medido)
- **Prova:** nenhuma; lida no C em 10/11
- **Ensaio:** —; não ensaiado

<a id="criar_da_lista"></a>
### Criar a entrada i da lista da sala

- **Função:** EmSetFromList2 (0x001BD538); símbolo: `EmSetFromList2__FUiUi`
- **Via:** chamada remota; 2 argumentos; trampolim desnecessário
- **Argumentos:** índice, checar_usada
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - sala e estágio da entrada iguais aos de pG+0x7EB8
  - entrada não criada (bit 1 da be_flag)
  - módulo do tipo residente (senão o mesmo caminho de EmSetEvent sem módulo)
- **Efeito visível:** não observado
- **Como desfazer:** não lido
- **Risco / causa da trava:** sem módulo residente: congela (mesma causa de criar_sem_modulo)
- **Prova:** nenhuma; lida no C em 29/10
- **Ensaio:** —; não ensaiado

<a id="dar_dano"></a>
### Tirar vida de um personagem pela função de dano

- **Função:** LifeDownSet2 (0x001C2618); símbolo: `LifeDownSet2__FP3cEmiiUi`
- **Via:** chamada remota; 4 argumentos; trampolim desnecessário
- **Argumentos:** (cEm*, dano, tipo de ataque, sinalizadores; bit 0 não deixa a vida cair abaixo de 1)
- **Ferramenta:** nenhuma
- **Pré-condições:**
  - personagem vivo
- **Efeito visível:** não observado (lido: desconta vida com escala pela dificuldade e dá pontos)
- **Como desfazer:** escrever a vida de volta (cEm+0x4B0)
- **Risco / causa da trava:** deve matar o personagem com dano ≥ vida (lido no C, não medido); no jogador desconta pG+0x7ED6
- **Prova:** nenhuma; lida no C em 28/10 e 11/11 (tabela de tipos 0x3B8F40)
- **Ensaio:** —; não ensaiado

<a id="consultar_vivo"></a>
### Saber se um personagem ou entrada está vivo

- **Função:** SceCheckEmAlive / EmListSetAlive (0x00270F00, 0x001BDAD8); símbolo: `SceCheckEmAlive__FP3cEm; EmListSetAlive__FUib`
- **Via:** chamada remota; 2 argumentos; trampolim desnecessário
- **Argumentos:** cEm*; (índice, vivo)
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** consulta; EmListSetAlive escreve o bit
- **Como desfazer:** EmListSetAlive com o valor oposto
- **Risco / causa da trava:** não lido
- **Prova:** nenhuma; só o índice de símbolos
- **Ensaio:** —; não ensaiado

## Trava (nunca acionar)

<a id="tocar_cutscene"></a>
### Tocar um evento (cutscene)

- **Função:** EventMgr::EvtReadExec (0x00206280); símbolo: `EvtReadExec__8EventMgrPCcUcUi`
- **Via:** chamada remota; 4 argumentos; trampolim desnecessário
- **Argumentos:** (mgr 0x4243D0, nome do .evd, espera, bits)
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** dorme pelo escalonador (SceSleep, cDvd); travou três vezes em 29/10, inclusive ancorada na thread de jogo pela matriz da câmera
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); três travamentos registrados
- **Ensaio:** —; não ensaiado

<a id="trocar_sala"></a>
### Trocar de sala por porta

- **Função:** SceAtExecRoomJump (0x0026B0C8); símbolo: `SceAtExecRoomJump__FUsRC6tagVecT1Uc13DOOR_EFF_TYPE`
- **Via:** chamada remota; 5 argumentos; trampolim necessário
- **Argumentos:** (sala, pos, rot, u8, efeito da porta)
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** trava por leitura, nunca acionada: carrega a sala do disco pelo carregador que dorme (TaskSleep), a mesma causa dos travamentos observados em 29/10
- **Prova:** nenhuma; lida no C; nunca chamada
- **Ensaio:** —; não ensaiado

<a id="carregar_modulo_pelo_jogo"></a>
### Carregar módulo pelo carregador do jogo

- **Função:** carregador do disco (0x00262708); símbolo: `FUN_00262708 (sem símbolo)`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** —
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** dorme por TaskSleep: a thread sequestrada nunca volta (três provas em 29/10)
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); jogo congelado
- **Ensaio:** —; não ensaiado

<a id="recarregar_lista"></a>
### Reler a lista de inimigos da sala do disco

- **Função:** readEmList (0x00276D60); símbolo: `readEmList__FUi`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** número da lista
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** trava por leitura, nunca acionada: lê pelo cDvd e dorme (mesma causa dos travamentos observados em 29/10)
- **Prova:** nenhuma; lida no C em 10/11; nunca chamada
- **Ensaio:** —; não ensaiado

<a id="iniciar_tarefa"></a>
### Iniciar uma tarefa do escalonador

- **Função:** TaskExec (0x00255F90); símbolo: `TaskExec (no, função, argumento)`
- **Via:** chamada remota; 3 argumentos; trampolim desnecessário
- **Argumentos:** (vaga, função, argumento)
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** a tarefa fica pendente: só o escalonador do jogo inicia tarefas (vagas 7 e 1 em 29/10)
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); tarefa pendente, sem efeito
- **Ensaio:** —; não ensaiado

<a id="criar_sem_modulo"></a>
### Criar personagem de tipo sem módulo residente

- **Função:** EmSetEvent (0x001BD800); símbolo: `EmSetEvent__FP7EM_LIST`
- **Via:** chamada remota; 1 argumentos; trampolim desnecessário
- **Argumentos:** EM_LIST de um tipo ausente da tabela 0x455E50
- **Ferramenta:** nenhuma
- **Pré-condições:** nenhuma registrada
- **Efeito visível:** —
- **Como desfazer:** —
- **Risco / causa da trava:** o jogo chama o carregador do disco, que dorme: jogo congelado (29/10)
- **Prova:** 29/10/2026, com o cliente no controle (docs/medicoes/S8-02-chamada-remota.md); jogo congelado
- **Ensaio:** 11/11/2026, estado 96, sala 0x0100, pelo autor (ensaio antes do aceite); reproduzido sem querer: EmSetEvent de 0x15 depois da carga falhar; chamada perdida em 5 s, os quadros do jogo pararam (68835 fixo); recuperado por LOAD_STATE 96

