# S7-01 — identidade de pedaço e perfil de cena mínimo (parte 1)

Medição feita na máquina do cliente em 27/10/2026, com a versão própria do emulador (camada de cena com
assinatura de forma) e o jogo de abertura, Resident Evil 4 (SLUS-21134). Imagens e dados brutos em
`~/IAEmPS2/medicoes/s7-01/` e os rascunhos de perfil em `~/IAEmPS2/perfis/cena/` (capturas do jogo não
entram no repositório, RN-09).

## O que mudou na camada

Cada desenho ganhou uma **assinatura de forma**: um hash das coordenadas de textura dos vértices (as que o
jogo usa para vestir o pedaço), quantizadas a 1/8 de texel, mais a quantidade de vértices. Coordenadas de
textura não mudam com a câmera nem com a pose do personagem, então o hash nomeia o pedaço de malha, não o
material. A regra de esconder aceita o par (material, forma); com forma zero vale para o material inteiro.
A máscara de capacidades passou a anunciar a cena (bit 8). O simulador do canal ganhou uma cena de mentira
e os quatro códigos, com teste.

## Resultado: identidade entre quadros (LC-15), câmera parada

| medida | valor |
|---|---|
| materiais de mundo por quadro | 73 |
| pedaços de mundo por quadro | 168 |
| pedaços cuja assinatura se mantém em 95% de 91 quadros | 153 (91%) |
| pedaços em comum entre dois quadros seguidos | 92% (mínimo 92%) |
| pedaços que aparecem num quadro só | cerca de 10 por quadro: partes animadas ou lotes que o emulador junta de forma diferente |
| materiais cuja lista de tamanhos de lote varia entre quadros | 37 de 73 |
| pedaços por material (mediana / máximo) | 35 / 612 |

A primeira tentativa, com quantização a 1/4096 de texel, não servia: quase nenhum pedaço repetia o hash
entre quadros, por ruído de ponto flutuante na divisão pela perspectiva. A 1/8 de texel, 91% dos pedaços de
mundo têm identidade estável com a câmera parada. **A medição com a câmera girando continua pendente:
precisa do cliente no controle.**

### Esconder um pedaço só, comparado ao material

Nos cinco maiores pedaços estáveis da cena (área entre 1% e 24% do quadro), esconder só o pedaço mudou a
imagem na caixa dele entre 1,2 e 2,9 níveis de cinza; esconder o material inteiro, entre 1,6 e 4,7. Ou
seja: a regra por pedaço age, e age em menos coisa que a regra por material, como esperado. As mudanças
são pequenas porque esses pedaços são sombreamento e passadas secundárias sobre o chão e sobre Leon (o
jogo desenha o mesmo objeto várias vezes); o efeito visível grande continua sendo esconder o conjunto.

## Ferramenta do mapeador (caso K03) e rascunho de perfil

`python -m iaemps2.bancada.mapear_cena --slot N --saida <pasta>` amostra alguns segundos de assinaturas,
grava a captura com uma caixa por pedaço estável, colorida pela classe sugerida, e um rascunho de perfil
em JSON com, por material: classe sugerida, se é desenho de mundo ou de tela, presença, pedaços por quadro,
deslocamento com a câmera parada e a lista dos pedaços estáveis. Classes sugeridas por regra simples:

- **interface**: desenhos sem profundidade presentes em todos os quadros (vida, munição, mira);
- **cenario**: material de mundo cujos pedaços ficam parados;
- **movel**: material de mundo cujos pedaços se deslocam com a câmera parada (personagem, animação);
- **desconhecido**: o resto.

Rascunhos gerados para duas cenas do jogo de abertura:

| cena | materiais | interface | cenário | móvel | desconhecido |
|---|---|---|---|---|---|
| floresta, Leon parado (slot 95) | 103 | 28 | 55 | 18 | 2 |
| cachorro na armadilha (slot 96) | 105 | 29 | 70 | 1 | 5 |

Os 18 "móveis" da primeira cena são os materiais de Leon respirando. O critério do card pedia classificar
inimigo e interface da primeira área: interface está classificada por regra; **inimigo depende de uma cena
com inimigo na tela e da confirmação do mapeador**, que é o cliente, porque a ferramenta só sugere.
As caixas desenhadas ainda saem deslocadas em parte da tela (a conversão de pixels do jogo para a janela
assume o quadro inteiro visível); vale corrigir com a medição da câmera.

## O que a parte 1 responde e o que falta no S7-01

- Assinaturas pelo canal em menos de 5 ms: **sim** (a lista de 550 assinaturas responde em um pedido).
- Perfil de cena com interface classificada: **sim, por regra**. Inimigo: **pendente do mapeador**.
- Identidade por pedaço com a câmera parada: **91% estável**. Com a câmera girando: **pendente**.
- Agrupar pedaços em objetos: **não feito**; a parte 2 testa dois caminhos, vizinhança de caixa e
  endereço de origem do desenho na memória do jogo.

## Como repetir

```
# emulador próprio aberto com o jogo, uma instância só
python -m iaemps2.bancada.prova_identidade --slot 95 --saida ~/IAEmPS2/medicoes/s7-01/identidade.json
python -m iaemps2.bancada.mapear_cena --slot 96 --saida ~/IAEmPS2/perfis/cena/rascunho-SLUS-21134-slot96
```
