# Engenharia reversa do código do jogo

Ferramentas para destrinchar o código de um jogo a partir do executável da ISO e de uma foto da memória do
emulador. O produto não depende delas: o que elas descobrem entra no perfil de memória do jogo
(`perfis/memoria/<serial>.json`) e nos documentos de medição.

## Peças

- `src/iaemps2/bancada/reversa.py`: extrai o executável da ISO, acha a tabela de símbolos que o jogo carrega,
  lista as faixas de memória que parecem código, acha função e chamadores de um endereço, desmonta uma faixa.
  Precisa do grupo opcional `reversa` (`pip install -e ".[dev,reversa]"`).
- `reversa/ghidra/MontarMemoriaEDecompilar.java`: pós-script do Ghidra sem interface. Completa o executável
  importado com a foto da memória (dados vivos e módulos carregados em tempo de execução), marca faixas como
  código, aplica os símbolos, nomeia âncoras, exporta a lista de funções e decompila as pedidas para `.c`.
- `perfis/memoria/<serial>.simbolos.csv`: a tabela de símbolos extraída (endereço, nome legível, nome decorado,
  info), regenerável a partir de qualquer foto da memória com o jogo carregado.

## Ferramentas externas

- Ghidra 12.1.4 (a extensão abaixo ainda não acompanha o 12.2) e JDK 21, instalados fora do repositório.
- Extensão `ghidra-emotionengine-reloaded` (linguagem `r5900:LE:32:default`), copiada para
  `<ghidra>/Ghidra/Extensions/`.

## Roteiro

1. Foto da memória com o jogo na cena de interesse: `python -m iaemps2.bancada.prova_memoria foto <rotulo>`.
2. Executável: `python -m iaemps2.bancada.reversa elf "<jogo>.iso" <pasta>`.
3. Símbolos: `python -m iaemps2.bancada.reversa simbolos <foto.bin> --saida perfis/memoria/<serial>.simbolos.csv`.
4. Faixas de código fora do executável: `python -m iaemps2.bancada.reversa codigo <foto.bin>`.
5. Projeto do Ghidra (primeira vez importa e analisa; depois `-process <exe> -noanalysis`):

```
analyzeHeadless <pasta_projeto> <nome> -import <exe> -processor "r5900:LE:32:default" \
  -scriptPath reversa/ghidra -postScript MontarMemoriaEDecompilar.java <foto.bin> <pasta_saida> \
  simbolos:<csv> codigo:<inicio>-<fim> ... nome:<endereco> ... -- <endereco> +<endereco> ...
```

   `codigo:` marca uma faixa como executável, `nome:endereco` rotula uma função, `simbolos:` aplica o CSV; depois
   do `--` vêm as funções a decompilar, e `+endereco` decompila também quem a chama. O `cmd.exe` parte argumentos
   em `=` e trata `^` como escape, por isso os separadores são `:` e `+`.

## Decisões

- O produto lê e aciona o jogo por fora, pelo emulador; não altera o disco nem o executável.
- Sem contribuição ao Ghidra nem à extensão: uso como estão.
