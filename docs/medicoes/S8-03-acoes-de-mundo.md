# S8-03 — ações de mundo no catálogo

Medição de 11/11/2026 na máquina do cliente, pelo autor, no estado 96 (vila, sala 0x0100), uma execução de
cada. O aceite do card (situação de combate, com o cliente no controle) ainda não foi feito.

## O que entrou

- **Perfil** (`perfis/memoria/SLUS-21134.json`, bloco `acoes_de_mundo`): três ações declaradas como o caso de uso
  H05 pede, cada uma apontando para uma capacidade `provada` do catálogo do S9-03:
  `vida_do_jogador` (fixa uma fração da vida máxima, piso 300), `municao_do_pente` (fração das balas no pente da
  arma equipada, pelo ponteiro do item equipado) e `vida_do_inimigo_mais_proximo` (fração da vida do inimigo vivo
  mais próximo, tipos 0x10..0x4F, só em combate). Faixa de fração e de duração por intensidade; volta única:
  devolver o que tirou, limitado à máxima.
- **Regras de mesa ao carregar** (`catalogo/mundo.py`): ação sem capacidade provada, sem máxima, com fração fora
  de (0, 1], ou vida com piso abaixo de 300 é recusada e fica registrada no log da abertura. Perfil de outro
  serial ou outra soma não entra; sem perfil o catálogo é o de hoje.
- **Catálogo**: as ações entram como alavancas iguais às universais (parâmetros `fracao` e `duracao_s`), vão no
  pedido de decisão, sobrevivem à versão nova do catálogo e só ficam disponíveis no modo completo.
- **Validação 1** (`mestre/decisao.py`): fora de jogo (menu, vídeo, carregamento, morte, sistema) e fora das fases
  declaradas é descarte por regra de mesa, antes de tocar no emulador.
- **Executor** (H07): lê o valor atual e a máxima na hora, confere piso e "nunca sobe", escreve, relê e só então
  confirma; releitura diferente devolve na hora e conta como falha. O fim é uma intervenção própria, de origem
  `encerramento`, ligada à mesma decisão, com o que foi devolvido. Reversão do jogador devolve antes do prazo.
  Com ação em vigor o salvamento periódico não acontece; a recarga descarta a ação sem escrever.
- **Capacidades novas provadas** (catálogo do S9-03): munição no pente (10 → 3 → 10) e vida de um personagem
  (1000 → 500 → 1000), relidas e estáveis por 3 s, com comandos `municao` e `vida-inimigo` em
  `bancada/capacidades.py`.

## Ensaio ao vivo do caminho inteiro

Executor real, cliente do canal real, registro numa sessão temporária, slots 90 a 94 (os slots 95 e 96 são do
cliente e nunca entram em ensaio). Decisão `vida_do_jogador` com fração 0,5 e 10 s, situação de combate:

| momento | vida lida | registro |
|---|---|---|
| antes | 9000 (máxima 9000, pedida pelo cliente) | |
| escrita e releitura | 4500 | intervenção 1 confirmada; volta: antes 9000, escrito 4500, tirado 4500 |
| 2 s, 4 s, 7 s, 9 s | 4500 | nada vencido |
| 11 s | 9000 | intervenção 2, origem encerramento, devolvido 4500; `fim_ms` da 1 preenchido |

## Testes (simulador)

`tests/test_s8_03_acoes.py`, 12 testes: o critério de aceite (cai, relido igual, volta sozinho no prazo, registro
com antes, depois, motivo e volta), piso e "nunca sobe", dano no meio do prazo (devolve o tirado), morte no meio
(sem escrita), reversão do jogador, salvamento bloqueado e recarga que descarta, releitura diferente (falha com
volta), fora de jogo na hora, perfil de outro jogo, ação recusada ao carregar, munição por ponteiro e escolha
do inimigo mais próximo (um objeto de tipo 0x51 não conta).

## O que não está

- Três reversões seguidas da mesma ação a tiram da sessão (H05, exceção): não entrou neste card.
- A escolha de entidade "na mira" e "fora da tela": só "mais próximo".
- As ações só rodam no modo completo (escrevem pelo canal); o emulador original não as tem.
- Uma sessão real usa os slots 90 a 99 por padrão: com os estados 95 e 96 do cliente nessa faixa, a sessão pode
  sobrescrevê-los. Configurar `[slots_reservados] inicio = 90, fim = 94` antes de uma sessão no jogo dele.
