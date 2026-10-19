# Rodar a próxima medição

Este arquivo é o ponto de entrada de quem vai continuar. Quem mexe no motor
atualiza **este arquivo e o README no mesmo commit** — quem chega depois não tem
como adivinhar o que mudou.

## O que mudou, do mais novo para o mais velho

### 19 de outubro de 2026 — alinhamento forçado define onde cada fala começa e termina

A primeira conversão completa (Parte 01, Fable + Seed-VC) soou ruim: falas
voltando para a voz original no meio da frase. Não era atribuição. A busca
aproximada da fala na transcrição (`map_phrase_to_words`) ancora no maior trecho
idêntico — numa fala longa, qualquer palavra transcrita diferente põe o início
no meio da frase — e dá nota baixa às falas longas, que então ficavam sem
conversão enquanto o trecho anterior do mesmo turno era convertido.

- **`alignment.forced: true`** (`forced_alignment.py`): o texto do livro é
  alinhado ao áudio por CTC (MMS_FA do torchaudio, GPU, modelo de 1,2 GB baixado
  na primeira vez), em janelas entre âncoras confiáveis do alinhamento antigo,
  com um token curinga em cada ponta. Só as janelas com falas de personagens em
  `convert` são alinhadas. Na cena da Yennefer, o método antigo começava falas
  curtas até 4 s antes (convertendo narração) e longas até 14 s depois; o
  proprietário comparou os cortes de ouvido e aprovou o forçado.
- **Fala inteira ou nada:** se um trecho de um turno não pode ser convertido,
  nenhum é; trecho curto demais não veta.
- Parte 01: 73 de 76 falas a converter receberam tempo forçado (3 mantiveram o
  antigo); **69 convertidas, contra 55** antes (Yennefer 63, Ciri 6); 1 trecho
  vetado pela regra do turno.

### 18 de outubro de 2026 — cargo só resolve na própria cena; ponte com o Claude Code

- **`TITLE_ONLY` escopado à cena.** `sorriu o feiticeiro` continua resolvendo
  para Radcliffe porque o livro escreveu `o feiticeiro Radcliffe` na mesma cena;
  `comentou o bruxo` deixa de virar Lambert por causa de um `o bruxo Lambert`
  noutro capítulo. Âncoras explícitas contra os gabaritos: Parte 01 49 corretas,
  Parte 02 38, Parte 03 43, **zero falsas — iguais a antes**; no livro inteiro,
  379 → 377 âncoras (as duas que saíram eram cargo fora de cena). Teste em
  `tests/test_ancora_com_titulo.py`.
- **`llm.provider: exchange`** (`ExchangeProvider`): o app grava cada pedido em
  `llm.exchange_dir` como `request-<hash>.md` e para **antes de converter**; um
  agente externo — o Claude Code com o login do usuário, sem chave de API —
  escreve `response-<hash>.json`; a execução seguinte consome a resposta pelo
  mesmo caminho de validação do `frontier`. Lote sem resposta nunca vira áudio
  convertido pela metade.

### 18 de outubro de 2026 — holdout dos Capítulos 6 e 7: precisão aprovada, cobertura reprovada

Rodada única, configuração congelada no commit anterior (Fable 5.1, prompt e
schema `frontier-speakers-v1`, limite 0,70). Auditoria das ferramentas: os dois
subagentes só leram o próprio pedido e escreveram a resposta.

| | Certas | Erradas | Abstenções | Precisão | Cobertura |
|---|---:|---:|---:|---:|---:|
| Cap. 6 (44 apagadas) | 23 | 1 | 20 | 95,83% | 54,55% |
| Cap. 7 (32 apagadas) | 30 | 0 | 2 | 100% | 93,75% |
| **Holdout** (76) | **53** | **1** | **22** | **98,15%** | **71,05%** |

**Leitura pelo pré-registro:** nenhuma faixa casa. A precisão passa do corte de
95%, a cobertura fica abaixo dos 85% exigidos. Não é aprovação, e não se
rebatiza a rodada.

O que os números escondem, registrado para a próxima decisão, sem mudar o placar:

- O único erro é **Artaud** respondido como **Terranova** — prenome e sobrenome da
  mesma pessoa, que o livro também escreve junto. `merge_partial_names` só une
  prefixo, não sobrenome; por identidade seria 54 de 54.
- **14 das 22 abstenções** são respostas `null` numa única cena de conselho com
  cinco reis, em que o apagamento de 60% tirou quase todas as indicações. É a
  saída segura funcionando onde o teste cego tirou a informação — mas é também a
  cena em que a cobertura do produto real dependeria de as indicações estarem lá.
- O Capítulo 6 é o lugar óbvio para medir cobertura real com o texto inteiro;
  o Capítulo 7 confirma que, em diálogo comum, o protocolo transfere sem perda.

**Defeito no instrumento, achado e consertado nesta rodada:** `--blocks-only`
recalculava os pseudônimos e, por iterar um `set` cuja ordem muda a cada
execução do Python, gerou para o Capítulo 7 um mapeamento diferente da chave. As
respostas do modelo são sobre o texto que ele recebeu e não foram tocadas; o
placar acima traduz os pseudônimos do texto recebido para os da chave por
alinhamento palavra a palavra (26 nomes, bijeção, nenhum ambíguo; Capítulos 4–6
sem nenhuma diferença). O script agora itera em ordem fixa e, com
`--blocks-only`, usa os pseudônimos da chave congelada e aborta se as falas
apagadas não baterem.

### 18 de outubro de 2026 — protocolo `frontier` com modelo de ponta, Qwen aposentado

**Por quê.** Dado só o texto, Opus 5.5 e Fable 5.1 acertaram a Parte 03 sem uma
voz errada, onde o Qwen 3 8B tinha errado 29. Para descartar cola, um teste cego
nos Capítulos 4 e 5 (nunca tocados por motor nenhum) apagou 60% das atribuições
explícitas, trocou todos os nomes por pseudônimos e corrigiu só as apagadas; a
auditoria das ferramentas dos subagentes mostrou que eles só leram o próprio
pacote. O gargalo era o modelo local, não a tarefa.

**O que entrou.**

- `llm.AnthropicProvider`: SDK oficial, saída estruturada por JSON Schema,
  system prompt em cache, fallback do servidor em caso de recusa. Configuração:
  `llm.provider: anthropic`, `llm.model: claude-fable-5-1` (ou `claude-opus-5-5`),
  `llm.effort`, e credencial por `ANTHROPIC_API_KEY` ou login `ant auth login`.
  Dependência opcional: `pip install -e .[frontier]`.
- `frontier_speakers.py` (`book_first.protocol: frontier`): cenas inteiras até
  150 mil caracteres por chamada; catálogo de personagens com IDs; as âncoras do
  parser vão como **pistas contestáveis**. Por turno o modelo devolve falante,
  tipo de trecho (fala, pensamento, citação), tipo de evidência, um trecho
  literal, confiança, segunda opção e se a pista é suspeita.
- **O código decide, não o modelo:** a voz só troca se é fala, o falante está
  no catálogo (ou foi declarado com menção literal no texto), o trecho citado
  existe no lote e a confiança passa de `book_first.frontier_confidence`
  (**0,70**, escolhido nos dados de desenvolvimento abaixo). Discordar de uma
  âncora explícita vira abstenção, nunca troca.
- `scripts/frontier_offline.py` exporta o pedido exato e aplica respostas
  obtidas por fora; `scripts/frontier_ceiling.py` põe essas respostas no placar
  do avaliador; `scripts/blind_attribution_test.py` monta e corrige o teste cego.

**Desenvolvimento, limite 0,70** (respostas do Fable 5.1 por subagente, não pela API):

| | Corretas | Vozes erradas | Abstenções | Não localizadas | Precisão | Cobertura |
|---|---:|---:|---:|---:|---:|---:|
| Parte 01 (213 dubláveis) | 211 | 0 | 0 | 2 | 100% | 99,06% |
| Parte 02 (183) | 179 | 0 | 3 | 1 | 100% | 97,81% |
| Parte 03 (350) | 332 | 0 | 5 | 13 | 100% | 94,86% |
| Cego Cap. 4 (38 apagadas) | 33 | 0 | 5 | — | 100% | 86,84% |
| Cego Cap. 5 (35 apagadas) | 31 | 1 | 3 | — | 96,88% | 91,43% |

Na Parte 03 a cobertura só fica abaixo de 95% pelas 13 falas que o áudio não
localizou; dos turnos detectados, 98,52% recebem voz. O teste cego é mais duro
que o uso real (as falas corrigidas perderam a indicação do autor), e várias
abstenções ali são de falas que, sem a indicação, não têm informação nenhuma.

**Defeito achado no parser, não consertado:** `TITLE_ONLY` resolveu `comentou o
bruxo` como Lambert porque o livro escreve "o bruxo Lambert" uma única vez; na
cena era Geralt. É âncora falsa que entrava no Qwen. No `frontier` ela vira
pista, e o modelo pode contestá-la.

**Pré-registro do holdout — Capítulos 6 e 7, teste cego, rodada única.** Chaves
congeladas em 18/10 antes de qualquer ajuste (sha256 `75e6f715…` e `00a71309…`,
fora do Git), 76 falas apagadas. Configuração congelada neste commit: prompt e
schema `frontier-speakers-v1`, limite 0,70, Fable 5.1.

| Precisão nas apagadas | Leitura |
|---|---|
| **≥95%** e cobertura ≥85% | O protocolo generaliza dentro deste livro; falta um segundo livro. |
| 90–95% | Ganho real, mas não fecha a meta; analisar sem rebatizar a rodada. |
| <90% | O desenvolvimento superestimou; não anunciar. |

A cobertura de corte é 85% e não 95% porque, no teste cego, parte das falas
apagadas fica sem informação nenhuma — no Capítulo 4 isso já custou 13 pontos.

### 8 de setembro de 2026 — Parte 03 congelada antes da primeira medição

**Resultado do pré-registro:** reprovado. A primeira execução fria, feita após o
commit do gabarito, produziu **90,68% de precisão e 88,86% de cobertura** sobre
350 falas dubláveis: 282 corretas, 29 vozes erradas, 26 abstenções e 13 falas não
localizadas. A Parte 03 agora está marcada como holdout consumido; repetir nela
serve para desenvolvimento, não para demonstrar generalização.

As maiores famílias foram Triss→Ciri (14), Coen sem atribuição (10), Ciri não
detectada (10), Geralt→Triss (6) e Geralt→Ciri (3). A cena 27, treino Coen/Ciri,
teve apenas 51,22% ponta a ponta, enquanto a cena 28, Geralt/Ciri, teve 97,67%.
Isso sugere falha de estabelecimento/manutenção do par de interlocutores, além
da perda pelo localizador de falas curtas. A próxima implementação deve ser
decidida no turno de modelo mais capaz; não ajustar regras neste turno de teste.

Saída local: `output/p03-holdout-fria-20260908/analysis.json`, `report.md` e
`erros.csv` (ignorados pelo Git).

`benchmarks/part03_gold.yaml` foi criado lendo apenas o EPUB, sem executar nem
consultar o Qwen nesta parte: P684–1126, 358 falas, 11 pensamentos/citações e
369 candidatos textuais no total. A voz metálica que usa a boca de Ciri é um
papel anônimo distinto; pensamentos e contato psíquico entre aspas não são fala
audível. O gabarito é de assistente e ainda não recebeu segunda auditoria humana.

Pré-registro da primeira rodada realmente fria:

| Precisão sobre dubláveis | Leitura |
|---|---|
| **≥95%**, cobertura ≥95% | Meta transferiu para uma parte intocada. |
| **90–95%**, cobertura ≥95% | Ganho parcial; analisar erros sem rebatizar a rodada. |
| **<90%** | O motor atual não generaliza o suficiente. |

Caches já existentes e identificados antes da rodada: transcrição `781f5bb...`
e alinhamento `f6235b2...`. A saída obrigatoriamente deve ser inédita.

### 8 de setembro de 2026 — rodada fria completa da coerência de turno v2

Executada pelo pipeline completo, com cache de respostas novo e Qwen 3 8B local:

| Desenvolvimento | Precisão | Cobertura | Corretos | Errados | Abstenções |
|---|---:|---:|---:|---:|---:|
| Parte 01 | 94,74% | 98,12% | 198 | 11 | 2 |
| Parte 02 | **95,53%** | **97,81%** | 171 | 8 | 3 |

A Parte 02 reproduziu exatamente a simulação offline. A Parte 01 teve seis
acertos a mais que a reaplicação offline (198 contra 192), mas ainda fica **uma
atribuição correta** abaixo da precisão de 95% sobre as 209 atribuições emitidas.
Como sua cobertura tem folga, uma próxima alteração deve preferir transformar em
abstenção apenas um erro demonstravelmente inseguro, ou acertá-lo por evidência
textual; não reduzir cobertura indiscriminadamente.

Arquivos de auditoria: `output/p01-regressao-v2b-20260908/analysis.json`,
`output/p01-regressao-v2b-20260908/erros.csv`,
`output/p02-regressao-v2-20260908/analysis.json` e
`output/p02-regressao-v2-20260908/erros.csv` (ignorados pelo Git).

### 8 de setembro de 2026 — coerência de turno v2 após o primeiro holdout

A Parte 02 voltou com **91,53% de precisão e 96,72% de cobertura**. Portanto, a
versão anterior transferiu apenas em parte e não atingiu 95×95. Como os erros
foram lidos para desenvolver esta versão, a Parte 02 deixou de ser holdout; seus
rótulos continuam congelados e ela passa a ser desenvolvimento.

`turn-consistency-v2` amplia a correção local com quatro evidências
estruturais, sem nomes ou respostas específicos do livro:

- vocativos recíprocos identificam os dois lados de uma resposta;
- uma inversão de dois turnos só é corrigida quando seis turnos sustentam a fase;
- personagem referido como terceira pessoa não pode ser o falante contextual;
- turnos compostos longos são preservados como monólogo, evitando os falsos
  positivos da regra de sanduíche.

Também foram adicionados `scripts/simulate_consistency_engine.py` e
`scripts/inspect_speaker_sequences.py`. A reaplicação offline, sem Qwen, produz:

| Desenvolvimento | Precisão | Cobertura | Corretos | Errados |
|---|---:|---:|---:|---:|
| Parte 01 | 93,20% | 96,71% | 192 | 14 |
| Parte 02 | **95,53%** | **97,81%** | 171 | 8 |

Esses números servem para detectar regressão da implementação. A rodada fria
ainda precisa confirmar o caminho completo, e a Parte 3 deve ser o próximo
holdout intocado.

### 8 de setembro de 2026 — gabarito da Parte 02, o primeiro holdout

`benchmarks/part02_gold.yaml`: **183 turnos**, P371–682, anotado lendo o EPUB
**antes de qualquer rodada do motor nesta parte**. Nenhuma regra foi ajustada
contra ele. É a primeira validação externa que o projeto tem.

| | Parte 01 | Parte 02 |
|---|---:|---:|
| Turnos | 255 | 183 |
| Dubláveis | 213 | **183** |
| Figurantes | 42 | **0** |
| Falantes | 27 rótulos | 7 nomes |

**Leia isto antes de comemorar o resultado:** a Parte 02 é um regime **diferente e
mais fácil**. Não tem cena de multidão, não tem papel anônimo, e 72% das falas
são Triss ou Ciri num diálogo de duas pessoas — exatamente onde a regra do
sanduíche funciona. Um número alto aqui **não** cancela a dificuldade da cena do
carvalho; confirma que o que foi consertado se transfere, e só isso.

Dois turnos (P672, P674) ficaram em `ambiguous_spoken`: o texto não diz qual dos
bruxos fala, e qualquer um dos cinco presentes conta como certo. Não chutei.

Os defeitos de limite conhecidos estão declarados: P410 e P586, onde a fala não
fecha com travessão e o parser engole a narração seguinte.

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

## Pré-registro histórico já medido

Duas coisas a medir, e nesta ordem.

### 1. Parte 01, para confirmar o conserto da âncora

| Precisão sobre dubláveis | Leitura |
|---|---|
| **94–96%** | Esperado: confirma a estimativa de 95,17%. |
| **93%** | As âncoras novas não renderam com o modelo no laço; nada regrediu. |
| **< 93%** | Regressão: âncora nova confundiu o modelo em outros turnos. |

### 2. Parte 02, então ainda holdout

Escrito **antes** de rodar, e é este número que diz se os ganhos foram reais:

| Precisão sobre dubláveis | Leitura |
|---|---|
| **≥95%** | Os ganhos da Parte 01 transferiram. Meta batida num trecho novo. |
| **88–95%** | Transferiram em parte. Comparar as famílias de erro com o CSV. |
| **80–88%** | A Parte 01 estava sobreajustada; o ganho real é bem menor. |
| **< 80%** | O motor não generaliza, e o 93% da Parte 01 era ilusão de ajuste. |

Cobertura esperada **≥95%** nos dois. Como a Parte 02 é um regime mais fácil
(sem multidão, sem anônimo, 72% de diálogo de duas pessoas), **eu esperaria a
precisão dela ACIMA da Parte 01**. Se vier abaixo, algo está errado de verdade.

Esse pré-registro foi encerrado em 8 de setembro: o resultado real da Parte 02
foi **91,53% de precisão e 96,72% de cobertura**. Depois de consultar seus erros
para criar a coerência v2, ela passou a ser conjunto de desenvolvimento. Não se
deve voltar a apresentar uma execução nela como validação independente.

## Rodada fria concluída

As Partes 01 e 02 foram executadas em diretórios vazios com
`turn-consistency-v2`. A Parte 02 confirmou a simulação; a Parte 01 ficou acima
dela, em 94,74% × 98,12%. Esta é uma **regressão fria**, não um teste de
generalização.

O próximo teste válido de generalização será uma Parte 03 (ou outro livro)
intocada: primeiro criar e congelar o gabarito, só depois executar o motor. A meta
continua sendo precisão ≥95% e cobertura ≥95%.

Para repetir ou investigar, rode as duas partes em pastas novas:

```powershell
# Parte 01
... --gold benchmarks\part01_gold.yaml --output output\p01-ancora-<data>
# Parte 02 (agora conjunto de desenvolvimento)
... --gold benchmarks\part02_gold.yaml --output output\p02-regressao-v2-<data>
... --gold benchmarks\part02_gold.yaml --no-turn-consistency --output output\p02-sem-regras-<data>
```

## Conferir o teto antes de qualquer campanha

Trinta segundos, sem GPU. Se sair código 1, nenhuma melhoria de modelo alcança a
meta e o problema é o gabarito, não o motor:

```powershell
& .venv\Scripts\python.exe scripts\gold_ceiling.py
```
