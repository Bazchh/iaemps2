# IAEmPS2

Mestre invisível por inteligência artificial para jogos de PlayStation 2 em emulador. Ele vê a tela,
lê o estado da partida pelo canal oficial do emulador e intervém, primeiro no ritmo e depois no mundo
do jogo, dentro de um catálogo fechado, com tudo registrado.

Os documentos que mandam no projeto estão em `docs/`: o Mapa do Projeto, os Casos de Uso e o
Blueprint Técnico. O código segue o roteiro em cards do capítulo 8 do Blueprint.

## Rodar

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
mestre --versao
```

Para jogar com o mestre: abra o emulador (PCSX2 2.8 ou mais novo) com o canal oficial ligado em
Configurações, Avançado, PINE, porta 28011; carregue o jogo; depois rode `mestre`. Sem o emulador
aberto, o programa informa que o canal não foi encontrado e encerra.

Nenhum teste sai da máquina nem precisa do emulador: o simulador do canal cobre tudo, e a integração
contínua no GitHub roda lint, formato, tipos e testes a cada push, sem nenhuma chave. O log é uma linha
JSON por evento, com sessão e ciclo.
Nenhuma chave entra no repositório; veja `.env.example`. A configuração fica em `config.toml`;
veja `config.example.toml`.

## O que nunca entra no repositório

Imagem de jogo, BIOS, estados salvos, capturas de tela e arquivos de sessão. São do jogador e ficam
na máquina dele (regra RN-09 do Mapa do Projeto).
