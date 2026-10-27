# S7-00 — prova medida da camada de cena (portão da fase 4)

Medição feita na máquina do cliente em 27/10/2026, com a versão própria do emulador (etiqueta v2.9.146 mais
a extensão do canal e a camada de cena) e o jogo de abertura, Resident Evil 4 (SLUS-21134, versão 1.01).
A cena é a da floresta, carregada de um estado salvo do mestre (slot 95), sem ninguém no controle: Leon
parado com a arma em punho, a casa ao fundo. Imagens e dados brutos ficam fora do repositório, em
`~/IAEmPS2/medicoes/s7-00/` (capturas do jogo não entram no repositório, RN-09).

## O que a camada faz

Uma função de entrada no renderizador, chamada antes de cada lote de triângulos ir para a placa de vídeo.
Para cada lote ela registra uma assinatura (hash da textura, quantidade de vértices, caixa na tela,
faixa de profundidade, se é desenho de mundo) e aplica as regras recebidas pelo canal: esconder um hash,
ou injetar um retângulo chapado numa profundidade escolhida, com o teste de profundidade do próprio jogo.
Regras têm prazo e morrem sozinhas no emulador. Quatro códigos novos no canal (0x84 lista, 0x85 regra,
0x86 limpar, 0x88 estatísticas), ainda fora da máscara de capacidades.

## Resultado

| medida | valor |
|---|---|
| desenhos por quadro na cena | 550 |
| desenhos de mundo por quadro (alvo + profundidade + teste e escrita) | 168 |
| parcela dos desenhos com hash real de textura | 34% (todos os de mundo com hash: 168 de 168) |
| custo de CPU da camada, sem regras | 26 µs por quadro |
| custo com uma regra de esconder | 27 µs por quadro |
| custo com dez regras que não casam | 40 a 47 µs por quadro |
| esconder o objeto escolhido por 10 s | aplicado em 299 de 299 quadros (100%), parado |
| esconder todos os 73 hashes de mundo de um quadro | Leon, árvores, chão e casa somem; fica névoa, céu e dois objetos sem hash |
| retângulo injetado na profundidade máxima | visível em 87% da caixa (o resto é a interface do jogo), nas duas regiões |
| retângulo na profundidade mediana ou mínima dos desenhos | 0% visível: tapado pelo que está na frente |

O quadro do jogo é 512x448; a janela do emulador tem barras pretas e o viewport é detectado na captura.

### Identidade entre quadros (LC-15)

Com a câmera parada, a assinatura escolhida (hash + 64 vértices + caixa) apareceu em 100% de 90 quadros, uma
cópia por quadro, e a regra de esconder a alcançou em 100% dos 299 quadros do intervalo. Vinte e um hashes
de mundo cumprem o critério de alvo (presença acima de 90%, área entre 1% e 30% do quadro, até duas cópias).

Dois limites apareceram. Primeiro: o jogo quebra o mundo em pedaços de 64 vértices que compartilham
textura, e desenha o mesmo objeto em mais de uma passada (cor e sombreamento com texturas diferentes), então
um hash é um "material" ou uma "passada", não um objeto: esconder um hash tira todas as folhas, ou toda a
casca de árvore, ou só o sombreamento de Leon, não "aquela árvore". Foi o que aconteceu com o alvo escolhido:
a imagem da diferença mostra o contorno de Leon e da casa mudando de leve (4 níveis de cinza em média),
porque o hash escondido era uma passada de sombreamento sobre eles; esconder o conjunto dos hashes de mundo
apaga a cena inteira. Segundo: a medição com a câmera girando precisa de alguém no controle (não há controle
virtual) e fica pendente para a sessão com o cliente.

### Profundidade (LC-16)

Nos desenhos de mundo da cena, a profundidade vai de 6.308 a 791.471, mediana 21.312. O sentido é: valor
maior, mais perto da câmera (o teste é "maior ou igual"). A varredura do retângulo em dez profundidades
mostra a ocultação coerente com a cena:

| profundidade | centro (Leon e chão próximo) | alto (casa e névoa, longe) | baixo à esquerda (chão) |
|---|---|---|---|
| até 31.579 | 0% | 0% | 0% |
| 54.022 | 3% | 54% | 0% |
| 92.416 | 13% | 67% | 0% |
| 158.095 | 22% | 73% | 0% |
| 270.453 | 22% | 74% | 81% |
| 462.661 | 37% | 87% | 81% |
| 791.471 | 87% | 87% | 93% |

O retângulo aparece primeiro na região longe (casa) e por último sobre Leon, como um objeto real faria.
A escala não é linear: a faixa útil para "longe" fica entre 30 mil e 100 mil, e "perto" acima de 400 mil,
neste jogo e nesta cena. Cada jogo terá a sua tabela no perfil de cena.

### Custo

A camada custa 26 µs por quadro sem regras (550 desenhos), dentro de um quadro de 16,7 ms: 0,16%. Com dez
regras, até 47 µs. É tempo de CPU da própria camada; o custo de GPU do retângulo injetado não foi medido e é
desprezível (dois triângulos).

## O que a prova responde ao critério do card

- Objeto escondido em pelo menos 95% dos quadros parado: **sim, 100%**. Com a câmera girando: **pendente**,
  exige o cliente no controle.
- Retângulo injetado ocluído corretamente em três profundidades: **sim**, e a varredura em dez profundidades
  dá a curva inteira em três regiões.
- Custo por quadro nos três cenários: **26, 27 e 40–47 µs**.

## O que isso muda no desenho da fase 4

- A unidade de identidade do nível 1 é o material (hash), não o objeto. Esconder, recolorir e deformar valem
  por material: "todas as folhas", "toda a casca", "todo o chão". Para agir num objeto só, é preciso juntar
  hash com posição, que vem do perfil de memória (fase 2), ou agrupar pedaços por vizinhança de caixa (a
  medir no S7-01).
- Dois objetos pequenos da cena não têm hash (texturas grandes demais para o cache de hash do emulador);
  para eles vale a identidade por endereço, menos estável entre carregamentos.
- A tabela de profundidade por jogo (LC-16) é medível com este mesmo roteiro e entra no perfil de cena.

## Como repetir

```
# emulador próprio aberto com o jogo, uma instância só
python -m iaemps2.bancada.prova_cena --slot 95 --saida ~/IAEmPS2/medicoes/s7-00/resultado.json
```
