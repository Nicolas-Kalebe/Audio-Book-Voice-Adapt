# Rodar a próxima medição

Este arquivo é o ponto de entrada de quem vai continuar. Quem mexe no motor
atualiza **este arquivo e o README no mesmo commit** — quem chega depois não tem
como adivinhar o que mudou.

## O que mudou, do mais novo para o mais velho

### 8 de setembro de 2026 — auditoria do gabarito e mais duas âncoras

- **O gabarito bate com o livro.** 49 atribuições explícitas conferidas contra o
  texto, 0 divergências; 0 ids órfãos; 0 contradições internas; e os quinze turnos
  em disputa, lidos à mão, dão razão ao gabarito em todos.
  Ver [docs/AUDITORIA-DO-GABARITO.md](docs/AUDITORIA-DO-GABARITO.md).
- `PRONOUN_GAP`: `respondeu por ela Geralt` voltou a ancorar. A lista de palavras
  funcionais, que existe para barrar `disse para Ana`, barrava também este caso.
- `TITLE_ONLY`: `sorriu o feiticeiro` resolve quando o próprio livro escreveu
  `o feiticeiro Radcliffe` em outro lugar. Dois com a mesma profissão não
  resolvem nada — a doutrina de não unir por ocupação continua.
- **Âncoras corretas: 46 → 49. Falsas: 0.** Estimado sobre a rodada fria:
  precisão **95,17%**, cobertura **97,18%**.

### 8 de setembro de 2026 — âncora atravessa o cargo até o nome

- A regex de atribuição só aceitava `verbo + artigo + Nome`. O livro escreve
  `observou o chanceler Vilibert`, com **cargo no meio**, e isso deixava o
  falante sem âncora nenhuma. `TITLE_GAP`, em `dialogue.py`, atravessa até duas
  palavras que não sejam funcionais.
- Cinco verbos de fala entraram: `esbravejou`, `bradou`, `indagou`, `piaram`,
  `apoiaram`, `vociferou`, `apoiou`, `indagaram`.
- **Âncoras corretas: 35 → 46. Falsas: 1 → 0.**
- Reaplicado sobre a rodada fria: precisão **93,17% → 95,15%** (estimado),
  cobertura 96,71%. **Precisa de rodada fria para confirmar**, porque âncora nova
  muda o payload do modelo.
- Efeito colateral: o `compact` puro passou a descobrir o nome atrás do título, que
  era o que o experimento `source_subjects` tentava — sem a parte dele que
  fragmentava identidades. `tests/test_speaker_subjects.py` foi atualizado.

### 8 de setembro de 2026 — as duas rodadas frias voltaram

| | Precisão | Cobertura | Corretos | Errados |
|---|---:|---:|---:|---:|
| `--no-turn-consistency` | 87,02% | 97,65% | 181 | 27 |
| com as regras | **93,17%** | 96,24% | 191 | 14 |

As duas reproduzem exatamente a simulação offline, e o resultado caiu dentro da
faixa pré-registrada de 92–94%.

### 8 de setembro de 2026 — regras de coerência de turno

- `turn_consistency.py`: duas regras aplicadas **depois** que o modelo responde.
  Vocativo (quem é chamado dentro da fala não é quem fala) e sanduíche (três
  turnos seguidos da mesma pessoa não é diálogo). Não chamam o modelo, não mudam
  prompt nem schema. Desligar com `--no-turn-consistency` ou
  `book_first.turn_consistency: false`.
- `merge_partial_names`: nome curto que é prefixo de **um único** nome completo é
  a mesma pessoa. `Radcliffe` e `Radcliffe de Oxenfurt` eram duas entidades.
- Medido sobre a rodada fria: precisão de 85,10% → 87,02% → **93,17%**, cobertura
  96,24%. Detalhe em [docs/RESULTADO-PART01.md](docs/RESULTADO-PART01.md).
- `scripts/simulate_rules.py`: testa regra nova sobre um `analysis.json` que já
  existe, sem GPU, e reporta **ganhos e perdas separados**.

### 8 de setembro de 2026 — duas decisões de produto

- Abstenção virou a saída segura, não erro. O placar separa o desfecho em três.
- Figurante de uma cena só não ganha voz. Denominador caiu de 255 para 213.
- Meta passou a ser **95% de precisão e 95% de cobertura** sobre os dubláveis.

### 8 de setembro de 2026 — o teto do gabarito

- Papel anônimo saía rotulado com sufixo de cena e nunca casava: um motor
  perfeito marcava 81,57%, e a meta de 90% era impossível. Teto corrigido para
  98,04%. `scripts/gold_ceiling.py` mede isso em 30s, sem GPU.
- **O `178/255` dos documentos antigos não é linha de base.**

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

A próxima rodada mede o **conserto da âncora**. Escrito antes de ver o resultado:

| Precisão sobre dubláveis | Leitura |
|---|---|
| **94–96%** | Esperado: confirma a estimativa de 95,17%. |
| **≥95%** | Meta batida. |
| **93%** | As âncoras novas não renderam com o modelo no laço; nada regrediu. |
| **< 93%** | Regressão: âncora nova confundiu o modelo em outros turnos. |

Cobertura esperada **96–98%**. Se cair abaixo de 95%, alguma âncora nova está
entrando em conflito e virando abstenção.

Rode as duas, em pastas novas:

```powershell
... --protocol compact --output output\ancora-com-regras-<data>
... --protocol compact --no-turn-consistency --output output\ancora-sem-regras-<data>
```

## Conferir o teto antes de qualquer campanha

Trinta segundos, sem GPU. Se sair código 1, nenhuma melhoria de modelo alcança a
meta e o problema é o gabarito, não o motor:

```powershell
& .venv\Scripts\python.exe scripts\gold_ceiling.py
```
