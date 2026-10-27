# S8-00 — câmera e lista de entidades do jogo de abertura

Medição iniciada em 27/10/2026 na máquina do cliente, com o cliente no controle por cerca de um minuto.
Fotos da memória pausada em `~/IAEmPS2/medicoes/s8-00/` (não entram no repositório). Roteiro cumprido:
três fotos com inimigo andando (primeira rodada contaminada, repetida parado), parado, andou, parado, virou,
parado.

## O que já está provado

| o quê | onde | como se provou |
|---|---|---|
| foto da memória pausada | pausa pelo canal, 32 MB em 1,4 s, retoma | oito fotos, jogo sem engasgo perceptível |
| vida do jogador e da parceira | endereços de fonte pública conferidos ao vivo | 1200 de 1200 e 600 de 600 |
| posição do jogador no mundo | três números em milímetros, mais um 1.0, com cópias em outros pontos da memória | andar 3 s moveu 6 m; virar no lugar quase não moveu; as cópias mudam juntas |
| matriz do jogador | 4x4 com três linhas unitárias e a posição na quarta | muda ao andar e ao virar como a posição |
| bloco da câmera | uma 4x4 que muda ao andar e ao virar, seguida de uma identidade e da transformação para a tela (escala e deslocamento de 2048, profundidade de 24 bits) | só esse bloco tem a forma de projeção; a convenção ainda não fechou |
| esqueleto do inimigo | pool de matrizes de ossos separado do pool do jogador; a raiz anda enquanto o jogador está parado | três fotos limpas, a raiz se desloca em linha |
| lista de entidades | vetor de estruturas de 0xED0 bytes a partir de 0x01789F40; slot 0 é o jogador; posição em +0x40 | cadeia de ponteiros a partir do esqueleto; posição projetada cai na caixa desenhada |

## Câmera fechada, com projeção provada

A leitura correta do bloco: o que parecia "posição do jogador" é o **olho da câmera** (anda com o jogador e
orbita quando ele vira no lugar); o ponto seguinte é o **alvo da câmera**, que projeta exatamente no centro
da tela e fica no tronco do jogador; a 4x4 é uma visão-projeção em convenção vetor-linha, com a distância ao
olho em w. A escala para a tela vem do bloco seguinte: x = 256 - (x/w)·1104,64 e y = 224 + (y/w)·1706,67,
no quadro de 512x448, com o sinal de x vindo da escala negativa do bloco.

Prova: a raiz, os pés e a cabeça do esqueleto do inimigo, lidos da memória, projetados com essa câmera,
caem dentro da caixa que a camada de cena desenha para o inimigo (materiais que se movem) nas três fotos:

| foto | caixa desenhada do inimigo (px) | raiz projetada | pés | cabeça | distância ao olho |
|---|---|---|---|---|---|
| inimigo1 | 217–347 × 114–515 | (271, 276) | (271, 492) | (260, 196) | 2,9 m |
| inimigo2 | 261–372 × 88–434 | (308, 230) | (305, 414) | (306, 158) | 3,4 m |
| inimigo3 | 264–385 × 91–458 | (317, 231) | (314, 418) | (310, 162) | 3,4 m |

Três de três quadros amostrados: acima do critério de 90%, com a ressalva de que a amostra é pequena e o
inimigo andava devagar. A câmera, o alvo, a matriz e a escala entraram no primeiro perfil de memória do jogo
(`perfis/memoria/SLUS-21134.json`), junto com a vida do jogador e da parceira.

## Lista de entidades encontrada

A lista não apareceu por valor: apareceu pela cadeia de ponteiros. O nó raiz do esqueleto do inimigo guarda um
ponteiro de volta para quem o possui, e esse dono é uma estrutura de 0xED0 bytes num vetor contíguo a partir de
0x01789F40. O slot 0 é o jogador (anda junto com o alvo da câmera); o slot 11 é o inimigo do estado 91; os
demais são aves (altura de 9 a 13 m), atores parados e slots vazios (cabeçalho zero). Um segundo vetor, com o
mesmo formato, a partir de 0x017BCDF0, guarda os objetos presos aos personagens (a arma do inimigo some dele
quando o inimigo morre). Campos provados: cabeçalho em +0x000 (bit 16 liga na morte, visto duas vezes), posição
dos pés em +0x040 (cópias em +0x0C0, +0x130 e +0x290), ponteiro para o esqueleto em +0x110, animação corrente em
+0x2FC, ponteiro para a arma em +0x710. A lista de tarefas do quadro, em 0x0048A000, enumera os objetos ativos.

Prova de posição: a posição do slot 11, projetada com a câmera já provada, contra a caixa desenhada do inimigo:

| foto | caixa desenhada (px) | pés | tronco (+0,9 m) | cabeça (+1,6 m) | distância |
|---|---|---|---|---|---|
| inimigo1 | 217–347 × 114–515 | (271, 492) | (271, 312) | (272, 161) | 2,9 m |
| inimigo2 | 261–372 × 88–434 | (305, 414) | (308, 261) | (310, 131) | 3,3 m |
| inimigo3 | 264–385 × 91–458 | (314, 418) | (317, 263) | (319, 132) | 3,3 m |
| antes do tiro | 158–390 × 112–502 | fora pela borda inferior | (270, 329) | (271, 111) | 2,2 m |
| após o 1º tiro | 255–347 × 83–319 | 8 px à esquerda | 8 px à esquerda | 8 px à esquerda | 8,3 m |

Quatro de cinco quadros válidos com tronco e cabeça dentro da caixa; o quinto, durante a animação de reação ao
tiro, fica 8 px fora, provavelmente porque a animação desloca o corpo em relação à origem da entidade. Uma sexta
foto foi descartada: o inimigo estava atrás da câmera e o que a cena desenhava com materiais "de inimigo" era
outra coisa. O critério do card (projeção na caixa em pelo menos 90% dos quadros) fica em 4 de 5 nos quadros
em que o inimigo anda e 7 de 8 contando a raiz do esqueleto; a amostra continua pequena.

## Rodada dos tiros (vida do inimigo): não fechou

Duas rodadas, as duas a partir do estado 91. Na primeira (antes, após o 1º tiro, após o 2º) o inimigo do slot
11 já estava morto na segunda foto: cabeçalho com o bit 16 ligado, posição congelada, animação 103, e três
inimigos novos entraram no vetor. O primeiro tiro matou, e o resto da rodada foi contra os reforços; o que esta
rodada media de "vida caindo" era outra coisa. Na segunda rodada (após o 1º, após o 2º, após o 3º, que matou) o
slot 11 está vivo nas duas primeiras fotos e morto na terceira, com a mesma assinatura.

Com as seis fotos, nenhum campo de 8, 16 ou 32 bits, nem ponto flutuante, cai nas duas fotos vivas e marca
morto nas três fotos de morte: nem dentro do slot (0xED0 bytes), nem nas estruturas que apontam para ele ou que
ele aponta, nem na memória inteira. As hipóteses inversas (dano acumulado subindo, vida como fração de 0 a 1)
também não deram nada. Os candidatos anteriores (2040 → 1530 → 989, 1635 → 1140 → 743 e parentes) são um pool de
dezenas de endereços com o mesmo trio de valores: altura de ossos (em pé 1,6 m, cambaleando 1,15 m, caído 0),
dados de animação. A vida do inimigo não aparece por diferença de fotos; o caminho é o nível 2: um vigia de
escrita no fork, parado no instante em que o jogo desconta o dano, lendo o endereço escrito.

Munição: também não aparece por valor. Três fotos com o número do HUD informado pelo cliente (7 balas no
carregador, 10 após recarregar, 9 após um tiro): nenhum endereço de 8, 16 ou 32 bits nem ponto flutuante faz
7, 10, 9, nem a sequência invertida (balas que faltam), nem em outra base (diferença +3 depois −1); a reserva
tampouco cai 3 fora das regiões de animação. O único padrão que acompanhou foi um contador cíclico de 0 a 10 em
seis blocos de interface, que não é munição. Vida do inimigo e munição ficam para o vigia de escrita.

## O que ainda não fechou

- **Vida do inimigo e munição.** Não aparecem por diferença de fotos (acima). Próximo passo: vigia de escrita no fork.
- **Critério do card.** Posição da entidade provada em 4 de 5 quadros; falta uma amostra maior e com o inimigo
  em movimento mais variado, com o roteiro novo (foto base antes do primeiro tiro, as duas rodadas a partir do
  mesmo carregamento).

## Lições

- O cliente andou durante a primeira rodada de fotos do inimigo e tudo que "andava sozinho" era coisa presa
  ao jogador. O roteiro tem de ser: inimigo andando com o jogador imóvel, e cada foto rotulada.
- Um pool de matrizes de ossos aparece como dezenas de "posições" que se movem juntas; o que identifica a
  entidade é a posição única fora do pool, e essa ainda falta.
