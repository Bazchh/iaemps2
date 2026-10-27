# S8-00 — câmera e lista de entidades do jogo de abertura (em andamento)

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

## Rodada dos tiros (vida do inimigo)

Três fotos com o cliente imóvel: antes do primeiro tiro, depois do primeiro, depois do segundo. O inimigo
revidou entre as fotos: a vida do jogador caiu de 1200 para 1048 e 915, e essa queda apareceu também como
ponto flutuante em outro endereço (0x0041B5C4), que deve pertencer ao objeto do personagem, não ao bloco de
estado do jogo. Candidatos a vida do inimigo, em ponto flutuante, caindo por valor parecido a cada tiro:
2040 → 1530 → 989 (duas cópias), 2337 → 2067 → 1823, 1635 → 1140 → 743. Nenhum deles tem uma posição
ao lado: a região em que moram (perto de 0x0184 0000 a 0x0186 0000) guarda valores que alternam entre poucos
pontos fixos, mais parecidos com dados de animação do que com uma lista de entidades. Munição: seis
candidatos que caem de um em um por tiro, a confirmar contra a tela.

## O que ainda não fechou

- **Projeção.** A posição do jogador pela 4x4 da câmera cai com divisor perto de zero: a matriz não é um
  mundo-para-tela simples, ou está relativa a outro ponto. Falta testar a composição com a transformação
  para a tela e a ordem das multiplicações, usando a caixa do inimigo na cena como gabarito.
- **Posição do inimigo na estrutura da entidade.** A raiz do esqueleto anda, mas nenhuma cópia dela apareceu
  fora do pool de ossos. A entidade pode guardar a posição em outra forma; procurar pela lista de entidades
  pelo passo entre estruturas, não pelo valor.
- **Critério do card (projeção na caixa em 90% dos quadros):** pendente dos dois itens acima.

## Lições

- O cliente andou durante a primeira rodada de fotos do inimigo e tudo que "andava sozinho" era coisa presa
  ao jogador. O roteiro tem de ser: inimigo andando com o jogador imóvel, e cada foto rotulada.
- Um pool de matrizes de ossos aparece como dezenas de "posições" que se movem juntas; o que identifica a
  entidade é a posição única fora do pool, e essa ainda falta.
