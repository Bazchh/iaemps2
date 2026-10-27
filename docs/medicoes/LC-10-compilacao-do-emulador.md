# LC-10 — compilação da versão própria do emulador (card S4-01)

Medição feita na máquina do cliente em 26/10/2026. Fecha a lacuna LC-10 do Mapa com número.

## Resultado

A receita do próprio projeto compila na máquina do cliente sem instalar nada além do que já havia.
O binário resultante abre o jogo de abertura e responde ao canal com a mesma identificação do instalado.

| medida | valor |
|---|---|
| tempo de máquina da compilação completa (Release AVX2, MSVC) | 7 min 16 s (21:21:13 a 21:28:29) |
| tempo de máquina da recompilação após mudar só `PINE.cpp` | 3 min 01 s (21:38:00 a 21:41:01) |
| pasta de objetos (`build/`) | 2,4 GB |
| binário e bibliotecas (`bin/`) | 274 MB |
| pacote de dependências pré-compiladas (baixado) | 172 MB comprimido |
| clone do repositório derivado | 342 MB |
| disco livre antes | 92 GB |
| erros e avisos de compilação | 0 e 0 |

## Ferramentas que já estavam na máquina

- Build Tools 2022 com a carga de trabalho C++ (MSVC 14.44, SDK 26100), MSBuild 17.14.
- Python 3.13 com `py7zr` para extrair o pacote de dependências (não há 7-Zip instalado; a receita do projeto o
  exige só para compilar as dependências do zero, o que não foi necessário).
- Git e a CLI do GitHub.

Nada precisou ser instalado.

## Decisão registrada: base na etiqueta nightly, não na 2.8.2

O Blueprint previa o repositório derivado na etiqueta 2.8.2, que é a versão instalada do cliente. O pacote de
dependências pré-compiladas que o projeto publica existe só para a versão corrente (Qt 6.12, SDL 3.4.18,
FFmpeg 9), e a 2.8.2 pede versões anteriores (Qt 6.11.1, SDL 3.4.12, FFmpeg 8.1). Compilar as dependências
da 2.8.2 do zero exigiria 7-Zip e horas de máquina.

A base passou a ser a etiqueta v2.9.146 (25/10/2026), cujo script de dependências é idêntico ao do pacote
publicado. O servidor do canal (`PINE.cpp` e `PINE.h`) é byte a byte igual entre a 2.8.2 e a v2.9.146, então
a extensão desenhada no Blueprint não muda. A solução passou a se chamar `PCSX2_qt.slnx`; o MSBuild 17.14 a
lê sem ajuste.

Consequência: o binário próprio é o que o cliente passa a usar; estados salvos da 2.8.2 podem não carregar
nele, o que não afeta a plataforma (os slots do mestre são por sessão).

## Receita que funcionou

```
gh repo fork PCSX2/pcsx2 --clone=false
git clone --recurse-submodules https://github.com/<conta>/pcsx2.git
git checkout -b iaemps2/s4-01-compilar v2.9.146
gh release download latest-windows-dependencies -R PCSX2/pcsx2-windows-dependencies -p pcsx2-windows-dependencies.7z
python -c "import py7zr; py7zr.SevenZipFile('pcsx2-windows-dependencies.7z').extractall('<repo>')"   # cria <repo>/deps
cp <instalado>/resources/patches.zip <repo>/bin/resources/
MSBuild.exe PCSX2_qt.slnx -m -v:m -p:Configuration="Release AVX2" -p:Platform=x64
```

O executável sai em `bin/pcsx2-qtx64-avx2.exe`. Para rodar como instalação separada, `bin/portable.txt` e um
`bin/inis/PCSX2.ini` com a seção `[Folders]` apontando BIOS e cartões de memória para a instalação do cliente.

Armadilhas encontradas: no Git Bash, `/m` e `/p:` do MSBuild viram caminhos (usar `-m`, `-p:` ou
`MSYS_NO_PATHCONV=1`); `taskkill /F` falha em silêncio pelo mesmo motivo (encerrar pelo PowerShell).
