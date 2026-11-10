# S9-02 — colisão de cenário: estrutura, terreno gerado e verificação automática

Medição de 30/10/2026 na máquina do cliente, fechada em 10/11/2026. Logs, saídas e cópias dos scripts em
`~/IAEmPS2/medicoes/s9-02/` (não entram no repositório); os scripts em `reversa/colisao/`.

## Por que isto está aqui

O pedido do cliente em 30/10 foi "o Leon anda em qualquer encosta de folhas, não sobe rocha reta, e escala
qualquer muro entre a cintura e a cabeça". Isso é a meta LC-17 do Mapa (mudar geometria de verdade, com colisão),
agendada para depois do S9. O dia foi gasto nela, sob demanda, do jeito que a DC-23 mandou evitar. Em 10/11 o
cliente concordou em fechar o desvio: o que foi medido fica registrado como estrutura do mapa (S9-02) e o
acabamento (paredes, salto) volta quando a LC-17 entrar como fase, com o mapa pronto.

## A estrutura lida (RE4 PS2, SLUS-21134)

- Dois gerentes de colisão, confirmados capturando o `this` da chamada do jogador: `SatMgr` 0x41AF10 (personagens)
  e `EatMgr` 0x41AF30 (balas, objetos, câmera). `cManager`: +0 vetor, +4 vagas (20), +8 tamanho da peça (0xF0),
  +0x10 vivas, +0x1C tipo (0 / 1), copiado para `SEck` (0x41B578) em `hitCheck2`; os filtros de atributo
  (PL_NOHIT 0x00400000 etc.) só valem com tipo 0. A peça da sala é a primeira do vetor.
- `cSat` (PS2): +0xC vértices, +0x10 normais, +0x14 arestas, +0x18 polígonos (0x14 bytes: 3 vértices, normal,
  3 arestas, reserva, status u32), +0x1C nº vértices, +0x1E nº polígonos, +0x20/+0x22/+0x24 chão/rampa/parede,
  +0x2A flag (4 ativa, 2 arquivo alocado), +0x30 bloco raiz, +0x60 arquivo, +0x70 matriz, +0xB0 inversa. Arquivo:
  cabeçalho 0x14, vetor de 12 bytes, blocos irmãos por deslocamento relativo em +0x20, `polyBit` 0x400 → no máximo
  8192 polígonos por peça.
- Funções: `cSatMgr::create(dados)` 0x1A32D0, `create(laje)` 0x1A33AB (o `Vec` do PS2 tem 16 bytes), `hitCheck2`
  0x1A3988, `getFloor` 0x1A26D0, `polySphereCk` 0x1A3490, `check` 0x1A18E8, `Mem_free` 0x2296D8, `jumpCheck`
  0x246538 (recebe `cPlayer*`), atributo `SAT_ATTR_JUMPOVER` 0x80000.
- Jogador: `cAtariInfo` em cEm+0x320 (+0x10 raio 400, +0x1E flags 0x1301); posição +0xC0, anterior +0x130, ângulo
  +0xD4, partes +0x110 (cada parte: mundo +0x80, anterior +0x90, +0xA0); esfera de colisão a y+873; encaixe no chão
  se |chão − y| < 1000, sondado 600 acima.
- Modelo visual (.bin do PS2, formato da ferramenta pública RE4-PS2-BIN-TOOL): cabeçalho 0x50, materiais de 16 bytes
  com ponteiro do nó, segmentos de tiras de triângulos em int16 × fator; mundo = vértice × fator × matriz do objeto
  (cObj+0x10). Tabela de objetos da sala 0x4568AC. Validado: altura sob o jogador bate em 3 cm.
- Efeitos: `EstSet` 0x1FAF80; tabela em gerente(*0x4203A4)+0x7400; conjunto 0x58+id do objeto (caixa 0x59, barril
  0x6A, tocha com tipos 1 a 3); 0x10 = conjunto da sala.
- Memória: `mem_alloc(…, 0xd, …)` não confere limite (alocou sobre dados vivos; queda do R5900). Faixas zeradas
  medidas para arquivos do mestre: 0x1F00000..0x1FF0000 e 0xAB0000..0xDF0000.

Peça de colisão da sala da floresta, lida ao vivo: 1971 polígonos (377 chão, 497 rampa, 1097 parede) na primeira
leitura; nas rodadas finais, 1117 paredes (936 ativas para o jogador, 181 sem geometria visual a 1,5 m
desligadas).

## O que foi feito e medido (uma execução cada; nada aqui é média)

| o quê | resultado medido | hora |
|---|---|---|
| chão gerado do modelo visual (faces até 50°, só a superfície mais alta) e registrado como peça | 7148 triângulos, 1244 blocos, 673 KB em 0x1F00000; o cliente subiu o morro da floresta | 17:06 |
| paredes do modelo visual (faces > 50°, aresta ≤ 6 m, nos dois sentidos) | 2 peças de 8000 polígonos em 0xAB0000 e 0xB56000; 23 329 faces íngremes no modelo, 8835 a 9969 ao alcance do jogador | 17:51 |
| andarilho (teleporte + 10 cm por passo, 60 pontos, 8 direções, 30 passos) | livre 10 459 · barrado 34 · atravessou face 148 · flutuando 18 · afundado 0 · sem chão no modelo 268 · teleporte rejeitado 15 | 18:06 |
| travessias por causa | 148: 57 com parede registrada perto, 91 só com face visual (fora das 16 000 registradas) | 18:09 |
| salto nativo em muros marcados (jumpCheck do jogo, jogador parado) | de 2 em 24 (faces da malha) até 10 em 30 (338 muros retangulares de 1,6 m, 1352 triângulos) | 18:08 → 18:26 |
| gravidade por fora (chão em Python, 5 Hz, 30 min) | 0 correções necessárias | 16:28 |

O que ficou provado: chão andável a partir do modelo visual, registrado como colisão e aceito pelo jogo;
teleporte confiável (posição, posição anterior e todas as partes); verificação automática sem o cliente.

## O que travou e por quê

| tentativa | resultado | causa lida |
|---|---|---|
| remendar código vivo (`j`/`nop` na entrada de função) | emulador em laço "Impossible block clearing failure" | o recompilador não aceita blocos trocados em execução; nunca mais |
| alocar o arquivo pelo `mem_alloc` do jogo | queda do R5900 ("jump to unmapped") | o alocador não confere limite e devolveu endereço sobre dados vivos; usar faixas zeradas medidas |
| gravidade por chamada remota a 4 Hz durante a partida | TLB miss na física do casaco; asserção "FQC = 0 on VIF FIFO READ" | chamadas de função só com o jogador parado; em partida só leitura e escrita de memória |
| teleporte só da posição | jogador arrastado até a primeira parede | a varredura de parede vai da posição anterior das partes até a nova |
| salto em faces finas da malha | jumpCheck nega | exige parede contínua de ≥ 60 cm nos dois ombros (±300 a 400 de altura) e chão 3,8 m atrás dentro de ±1,5 m |
| andarilho relançado às 18:28 com detecção refinada | processo morto por memória baixa do PC (2,6 GB livres) | não relançar sem ordem |

## O que não foi feito

- A validação dos muros de salto pelo chão do próprio jogo está no `terreno.py` final, mas **nunca rodou**; o
  andarilho com detecção refinada **nunca terminou**. Os números acima são da versão anterior.
- O scratchpad de 30/10 foi apagado pela limpeza de temporários. `andarilho.py`, `salto_check.py` e
  `gravidade2.py` são o texto exato lido em 30/10; `terreno.py` foi reconstruído a partir da cópia das 15:07 e dos
  remendos registrados na transcrição (todos reaplicados, compila). O mesmo método, aplicado aos três scripts
  anteriores, reproduziu byte a byte o texto lido, o que valida a reconstrução; ainda assim `terreno.py` **não
  foi executado de novo**.
- Mapeamento dos botões do controle (0x431948) para um botão de salto: não iniciado.

## Lacunas registradas (voltam na LC-17)

- Travessias de parede em 1,4 % dos passos (148 em 10 459), 91 delas em faces fora do limite de 16 000 polígonos.
- Salto nativo disponível em um terço dos muros gerados (10 em 30); falhas por chão atrás ausente ou a mais de
  1,5 m e por um ombro sem acerto.
- Faces gigantes de fundo e caixas de corpo das árvores empurram o jogador por metros; o andarilho só parte do
  chão original (ou até 3 m acima dele).

## Scripts (`reversa/colisao/`)

- `terreno.py [raio_m] [incl_max] [--sala] [--criar] [--substituir] [--sem-paredes] [--paredes=N]`: lê os modelos
  visuais, gera chão e paredes, muros de salto, registra as peças, grava `triangulos_chao.json`.
- `andarilho.py [pontos] [passos] [direcoes]`: verificação automática; grava `andarilho_resultado.json`.
- `salto_check.py [amostras]`: testa o salto nativo nos muros marcados.
- `gravidade2.py [min] [hz]`: gravidade por fora, só leitura e escrita; vigia as faixas do mestre.
- `morro.py` (laje de 4 cantos), `efeito.py <est> <kind>[-fim] …` (efeitos por `EstSet`).

Todos usam a porta 28011 do fork, salvam e recarregam o estado 95 do emulador, e exigem um único cliente PINE
por vez (parar a gravidade antes de rodar outro).
