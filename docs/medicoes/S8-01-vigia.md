# S8-01 — vigia de escrita e a função de dano do jogo de abertura

Medição de 27 e 28/10/2026 na máquina do cliente, com o cliente no controle. Tabelas do vigia e desmontagens em
`~/IAEmPS2/medicoes/s8-01/` (não entram no repositório).

## O que o vigia é

Um comando novo do canal próprio (capacidade bit 16): dada uma faixa de memória e uma condição (leitura, escrita ou
ambas), o emulador registra, **por instrução do jogo**, cada acesso à faixa, sem pausar: endereço do primeiro e do
último acesso, contagem, largura, último valor escrito e os 32 registradores no primeiro acesso. A tabela tem 4096
entradas por instrução; o que não cabe vira "descartado" e aparece no resumo. O vigia se desarma sozinho no prazo.

Custo: enquanto há um vigia armado, todo acesso à memória do jogo passa pela verificação do depurador, então o
jogo tende a ficar mais lento. **Não medido.** As contagens vistas (86 acessos por instrução em 3 s no slot do
inimigo, 168 em 2 s na matriz da câmera) não servem de medida porque não se sabe quantas vezes por quadro cada
escrita acontece, e o jogo roda nativamente a 30 quadros por segundo. Receita para medir: achar um contador de
quadros do jogo, ler pelo canal o avanço dele em 10 s sem vigia e com o vigia armado, e comparar. O vigia não fica
armado durante uma sessão normal.

## Provas

| o quê | como | resultado |
|---|---|---|
| mecanismo | vigiar a matriz da câmera (escrita todo quadro) por 2 s | 4 instruções `sq` seguidas (0x252830 a 0x25283C), 168 acessos cada, base a2 = 0x4327C0, zero descartes |
| prova de fogo do card | vigiar a vida do jogador (0x42DA76) enquanto o inimigo acerta | vida 1200 → 0, 11 acessos, 3 instruções, as três `sh` com deslocamento 0x7ED6 sobre a base 0x425BA0; a de valor novo é 0x1C27FC |
| vida do inimigo | vigiar o vetor inteiro de personagens durante três tiros do cliente | a instrução 0x1C2AA8 escreveu 248 no slot 11 em +0x4B0 no primeiro tiro e 0 no tiro que matou; o cabeçalho ganhou o bit 16 |

A vida do inimigo, que não aparecia por diferença de fotos (S8-00), apareceu na primeira janela certa do vigia: o
Ganado de aldeia tem 500 de 500 (+0x4B0 e +0x4B2), as aves 10, os atores parados 1000, e o próprio jogador 1200 no
slot 0, espelho da vida global.

Duas janelas anteriores não deram nada e valem como lição: a primeira porque o Ganado que o cliente atingiu não era
o slot vigiado; a segunda porque a janela de tempo fechou antes do tiro. A forma que funcionou foi armar o vigia por
dez minutos, deixar o cliente agir e ler a tabela quando ele avisa.

## A função de dano, lida no código

Com o endereço da instrução em mãos, a função em volta foi desmontada da foto da memória. É uma função só para todo
dano do jogo, `dano(entidade, quantidade, variação, flags)`, que devolve a vida restante:

- **Variação**: se diferente de zero, soma `aleatório % (2·variação) − variação` à quantidade.
- **Tipo da entidade em +0x11C** decide o ramo: 0 é o jogador, 1 a 13 a parceira e aliados, 16 ou mais os inimigos
  (tabela de salto por tipo em 0x3C8F40, 64 entradas, para fatores específicos).
- **Jogador**: vida global 0x42DA76 no bloco 0x425BA0 (apontado por 0x325308), fator de dificuldade 0,1·dif + 0,5
  (dificuldade adaptativa em 0x42DA64, o "3 → 2" visto em S8-00), reduções de 0,7 e 0,8 por condições, flags de
  invencibilidade e de vida cheia em +0x7EE8 (64 bits), sons por intensidade. Desconta no máximo a vida atual; com o
  bit 0 das flags, nunca mata (deixa 1).
- **Inimigo**: vida em +0x4B0 da entidade; fator 2,0 − 0,2·dif abaixo da dificuldade 6, senão 1,0 − 0,03·(dif − 5);
  mesma regra de desconto e de "não mata"; som de morte quando chega a zero.

Chamadores: no executável, os de dano ao jogador (0x1C2C18 e 0x1C3628, lendo quantidade e flags de um registro de
acerto); no módulo de inimigos, 0x1BADAF0 é o tratador do acerto de um tiro: pede a quantidade a 0x1BF4458 (tipo de
tiro em +0x2E do registro e zona atingida), chama `dano` e abate do dano restante do registro (+0x89A do slot).
O registro de acerto é preenchido por 0x1BB580, chamado de onze lugares (balas, explosões, agarrões).

## Virada: destrinchar o código do jogo

O tiro não escreve no bloco do jogador (0x425BA0, 32 KB) nem no vetor de entidades. O cliente decidiu em 28/10
mudar de estratégia: em vez de uma janela do vigia por pergunta, destrinchar o código do jogo de forma sistemática,
com desmontador e decompilador (Ghidra 12.1.4 com a extensão do Emotion Engine, sem interface, por roteiro),
partindo das âncoras acima. O executável (SLUS_211.34, 3 MB, código de 0x100000 a 0x3C9F28) é completado com a
foto da memória do estado 91, porque boa parte do código é módulo carregado em tempo de execução (0x4A0000,
0x8A0000, 0x10F0000, 0x1180000, 0x1B00000 em diante, achados pela densidade de prólogos de função na foto).

A decompilação confirmou linha a linha a leitura manual da função de dano, e trouxe o que a desmontagem a mão não
daria: **o executável carrega os próprios símbolos**. A seção `.sndata` tem 3448 nomes C++ decorados e uma tabela
de 1275 entradas liga nome a endereço. Com eles o mapa ganhou classes: `cItemMgr` (inventário), `cObjWep` (arma),
`cObjBull` (bala), `cPlayer`, `cEmHit`, `Merchant`, `CameraControl`. Os nomes entram no projeto do Ghidra por
roteiro e as funções saem com nome no C decompilado.

## Munição: fechada pelo inventário

`cItemMgr::bulletNumCurrent` (0x120450) lê o item equipado do gerenciador global em 0x3CE148 e devolve, para armas
comuns, o campo +0x8 do item deslocado 3 bits à direita. O gerenciador guarda em +0x0C o ponteiro para o item
equipado, em +0x14 o vetor de 384 itens de 14 bytes (id em +0x0, quantidade em +0x2, flags em +0x4, balas no pente
vezes 8 em +0x8) e em +0x1C a quantidade de slots. Validação: o campo deslocado bate com o número do HUD informado
pelo cliente em duas fotos de 27/10 (7 e 9 balas: 56 e 72) e na leitura ao vivo de 28/10 (72 = 9); na foto rotulada
"10 após recarregar" o campo vale 72 (9), provavelmente tirada depois do tiro seguinte, e a reserva do item de balas
(id 4) caiu de 20 para 17, o que confirma a recarga de três. As demais fotos (sem número do HUD informado) dão 10
no estado inicial e 8, 6 e 4 na rodada A, dois a menos por passo, o que pede conferência (dois tiros por passo ou
rótulos trocados). O que sustenta a leitura é o decompilado (`>> 3`) mais os três acertos exatos. Por isso a caça
por valor de S8-00 não achou: o número está multiplicado por 8.

## O que ainda não fechou

- **Tabela de tipos de inimigo** (0x3C8F40): nomear os 64 casos.
- **Mapa de funções**: a tabela de símbolos, o extrator e o roteiro do Ghidra estão no repositório
  (`perfis/memoria/SLUS-21134.simbolos.csv`, `bancada/reversa.py`, `reversa/`); ficam fora o projeto do Ghidra e o
  C decompilado, regeneráveis da foto pela receita do `reversa/README.md`.
- **Munição na rodada A**: as fotos sem número do HUD caem de dois em dois por passo; conferir se foram dois tiros
  por passo ou rótulos trocados.
- **Modo "pausar no acerto"** do vigia: adiado; não foi necessário.
