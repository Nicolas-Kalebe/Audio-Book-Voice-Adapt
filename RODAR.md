# Rodar a próxima medição

Uma rodada só. Nada de lógica de identificação mudou nesta versão — o que está
sendo medido é a correção de rótulo e identidade do commit anterior.

## Antes de rodar

Confira os dois hashes de cache da Parte 01. São os mesmos das rodadas
anteriores, e trocá-los invalida a comparação:

```powershell
dir cache\transcription\37a006528eea8622f6589b8a11310aa51e12ea0865343ffa42b0eba7f2093338.json
dir cache\alignment\ae2e108189c7ea7e77b5600b4a2cf1eed1a8532bd0fd14f37574396d2026881a.json
```

Ollama no ar com `qwen3:8b`, e nenhum outro processo usando a GPU.

## Rodada fria

A pasta de saída tem de ser inédita — é o que garante cache de respostas vazio.
Troque a data se já existir.

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
& .venv\Scripts\python.exe scripts\benchmark_book_speakers.py `
  --book "books\O Sangue dos Elfos.epub" `
  --transcription cache\transcription\37a006528eea8622f6589b8a11310aa51e12ea0865343ffa42b0eba7f2093338.json `
  --alignment cache\alignment\ae2e108189c7ea7e77b5600b4a2cf1eed1a8532bd0fd14f37574396d2026881a.json `
  --config config\config.yaml `
  --gold benchmarks\part01_gold.yaml `
  --protocol compact `
  --output output\identidade-corrigida-20260908
```

## Depois, o CSV

```powershell
& .venv\Scripts\python.exe scripts\dump_errors.py `
  --analysis output\identidade-corrigida-20260908\analysis.json `
  --output output\identidade-corrigida-20260908\erros.csv
```

## O que me mandar

Só dois arquivos, e nada mais precisa vir junto:

1. `output\identidade-corrigida-20260908\erros.csv`
2. a saída impressa dos dois comandos (o placar e as tabelas de família e cena)

O CSV não tem texto do livro além de 200 caracteres por turno; se isso for
problema, apague a coluna `texto` antes de mandar — o resto basta.

## A meta

Definida em 08/09/2026: **95% em tudo**, sobre os **213 turnos dubláveis** (os
outros 42 são figurante de uma cena só e não ganham voz).

| | Exige | Teto | Folga |
|---|---:|---:|---:|
| Cobertura ≥95% | 203 atribuídos | 208 têm áudio | **5 abstenções** |
| Precisão ≥95% | 193 corretos | — | **10 vozes erradas** |

A trava mais apertada é a **cobertura**. O motor hoje abstém cerca de 16 vezes,
o triplo da folga — abster para não errar deixou de ser de graça.

## Ganho pré-registrado da PRÓXIMA rodada

A rodada de 08/09 já voltou: 85,10% de precisão e 97,65% de cobertura sobre os
dubláveis (ver `docs/RESULTADO-PART01.md`). Sobre ela foram aplicadas as regras
de coerência, medidas offline em `scripts/simulate_rules.py`.

A próxima rodada fria tem de confirmar, com o modelo no laço:

| Precisão sobre dubláveis | Leitura |
|---|---|
| **92–94%** | Esperado: reproduz a medição offline. |
| **≥95%** | Meta batida nesse lado. |
| **87–92%** | As regras rendem menos com o modelo no laço do que na simulação. |
| **< 87%** | Regressão. Desligar com `--no-turn-consistency` e comparar. |

| Cobertura sobre dubláveis | Leitura |
|---|---|
| **96–98%** | Esperado. |
| **< 95%** | A regra de vocativo está abstendo demais. |

Rode **as duas**, em pastas diferentes, para isolar o efeito das regras:

```powershell
... --protocol compact --output output\com-regras-<data>
... --protocol compact --no-turn-consistency --output output\sem-regras-<data>
```

## Conferir o teto antes de qualquer campanha

Trinta segundos, sem GPU. Se sair código 1, nenhuma melhoria de modelo alcança a
meta e o problema é o gabarito, não o motor:

```powershell
& .venv\Scripts\python.exe scripts\gold_ceiling.py
```
