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

## Ganho pré-registrado

Escrito **antes** de ver o resultado, para o número não ser explicado depois:

| Faixa (coluna por identidade) | Leitura |
|---|---|
| **188–205 / 255** | Esperado. A correção liberou os papéis anônimos que o motor já reconhecia. |
| **> 205 / 255** | Melhor que o previsto. |
| **178–187 / 255** | A correção mal moveu: o motor reconhece o papel anônimo pior do que eu supus. |
| **≤ 177 / 255** | Regressão. A fusão de anônimos por descrição está juntando gente diferente — reverter com `anonymous_scope: mention`. |

A coluna literal também aparece no placar. Ela vai continuar mais baixa que a de
identidade; a diferença entre as duas é a lista `literal_only_misses`, e cada
turno dela deve ser auditado antes de virar acerto oficial.

## Conferir o teto antes de qualquer campanha

Trinta segundos, sem GPU. Se sair código 1, nenhuma melhoria de modelo alcança a
meta e o problema é o gabarito, não o motor:

```powershell
& .venv\Scripts\python.exe scripts\gold_ceiling.py
```
