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
