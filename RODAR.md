# Rodar a próxima medição

Este arquivo é o ponto de entrada de quem vai continuar. Quem mexe no motor
atualiza **este arquivo e o README no mesmo commit** — quem chega depois não tem
como adivinhar o que mudou.

## O que mudou, do mais novo para o mais velho

### 10 de setembro de 2026 — a fila de auditoria dos erros (`scripts/auditar_erros.py`)

Ferramenta de diagnóstico. Não toca no motor, não precisa de campanha nem de GPU:
roda sobre um `analysis.json` que já existe.

**O que faltava.** Os relatórios dizem QUANTOS erros existem. Nenhum dizia QUAIS, com
o que havia escrito em volta — e sem isso a pergunta que decide tudo nunca foi feita
turno a turno: **o motor errou, ou o rótulo do gabarito está errado?** O gabarito da
P3 declara `annotation_review: assistant_authored_not_independently_audited`, e os 28
erros dela nunca foram conferidos por uma pessoa contra o livro.

Isso importa para a conta. São 350 dubláveis, 327 atribuídos, 299 corretos; a meta
pede 12 erros convertidos. Se alguns dos 28 forem rótulo errado, a distância encolhe
**sem tocar no motor** — e nenhum mecanismo novo precisa ser inventado para isso.

**O que ela produz**, em `auditoria-erros.md`, `.json` e `.csv`:

- erros e abstenções **separados** — trocar a voz e ficar sem voz são desfechos
  diferentes, e só um é defeito;
- resumo por cena, por regra que escreveu a voz (`sem_regra` = primeira leitura) e as
  trocas mais frequentes (esperado → saiu);
- um bloco por erro com os **turnos vizinhos**, cada um com o falante que o motor
  atribuiu e o texto. É o que permite julgar sem abrir o EPUB na maioria dos casos;
- uma linha de veredito para preencher: motor errou · gabarito errado · em dúvida.

Figurante fica fora da fila, pela mesma razão que fica fora da métrica (decisão do
proprietário, 08/09/2026): não decide o produto, não ocupa tempo de quem audita.

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
& .venv\Scripts\python.exe scripts\auditar_erros.py `
  --gold benchmarks\part03_gold.yaml `
  --analysis output\hybrid-p03-v11-20260910\analysis.json `
  --output output\auditoria-p03
```

**Ordem sugerida antes da próxima campanha**, e as duas primeiras não precisam de
ninguém escrevendo código:

1. rodar o diferencial da P3 com o cruzamento por `consistency_rule` — decide entre
   apertar regra existente e escrever mecanismo novo;
2. rodar esta auditoria e responder o veredito dos 28;
3. anotar um holdout novo e congelá-lo. P1, P2 e P3 são todas desenvolvimento, e cada
   iteração é decidida contra as mesmas três partes. Sem uma parte nunca vista,
   nenhum resultado sustenta a frase "funciona em qualquer livro".

### 10 de setembro de 2026 — o código da v1.2 sai do repositório

O protocolo `hybrid-revisao` foi **removido**: constante de protocolos, ligação no
`book_speakers`/`compact_speakers`, o modo do roteador e os testes da opção. O
`hybrid` (v1.1) volta a ser exatamente o que era, e o replay congelado — que é
contribuição boa e independente — fica.

Mecanismo reprovado que continua ligável é armadilha. O próximo a passar por aqui
liga "só para ver", ou mexe no limiar que a própria medição disse para não mexer.
O experimento está no histórico (`8fe3851`) e a medição está registrada abaixo;
isso basta para reconstruí-lo, e é mais do que basta para não repeti-lo.

**A lição, que vale mais que o código removido.** A hipótese era: "falante fora do
elenco estabelecido da cena é suspeito". O replay mostrou que ela é falsa, e a causa
é estrutural, não de calibragem — quem some da janela de doze registros e volta a
falar é o caso NORMAL de um personagem que ficou algum tempo calado. A revisão então
marcava um acerto como alvo e, oferecendo só o `active` como catálogo, tornava
impossível manter a resposta certa: a voz original não estava entre as opções. Por
isso trocou a maioria do que olhou (21/26 na P3) em vez de quase nada.

Confundir "não está no elenco recente" com "provavelmente errado" foi o erro. O
alvo estava errado, não o limiar — e é por isso que ajustar confiança não o
salvaria.

**O que fica de método:** na campanha fria completa, a P1 aparecia com saldo −5; no
replay congelado, ficou 0/0. Ou seja, aquele dano era **variação do primeiro passe
entre execuções**, não efeito da regra. Comparação entre duas campanhas frias mede a
experiência do protocolo inteiro, e serve para decidir o que entra em produção; para
atribuir causa a um mecanismo, o replay com primeiro passe congelado passa a ser o
instrumento — e vale reler com essa lente qualquer conclusão anterior tirada de duas
rodadas frias.

### 10 de setembro de 2026 — replay congelado confirma a reprovação da v1.2

O diagnóstico foi executado em saídas inéditas. Cada uma reutilizou todas as
respostas do primeiro passe da v1.1: P1 14/14, P2 12/12 e P3 19/19 chaves lidas;
zero faltas. Só as chamadas de reparo/revisão foram ao Qwen. Assim, o comparador
abaixo mede mudanças depois do primeiro passe, não variação dele.

| Desenvolvimento | v1.1 (precisão × cobertura) | replay v1.2 | Salvos / estragados | Saldo |
|---|---:|---:|---:|---:|
| Parte 01 | 95,24% × 98,59% | 95,24% × 98,59% | 0 / 0 | 0 |
| Parte 02 | 95,53% × 97,81% | **93,75% × 96,17%** | 2 / 8 | −6 |
| Parte 03 | 91,44% × 93,43% | **89,97% × 94,00%** | 8 / 11 | −3 |

Conclusão: o primeiro passe frio explica o dano visto na P1, mas não os danos em
P2/P3. Em P2, 7 dos 8 acertos estragados foram marcados
`revised_by_hybrid_outsider`; em P3, 10 dos 11. As mudanças de coerência restantes
são efeitos posteriores dessas trocas. A v1.2 oferece apenas o elenco `active` à
revisão, logo a voz original que caiu fora da janela não pode ser escolhida de novo.
O mecanismo como um todo fica descartado, não é candidato a ajuste de confiança.

Saídas locais ignoradas pelo Git: `output/replay-p0X-v12-20260910/` e
`output/comparacao-replay-p0X-v12/`.

### Replay do primeiro passe — próximo turno de testes

Implementado `--frozen-base-cache`: a chave inclui prompt, schema, identidade do
provider e payload completos. Uma chave ausente aborta a execução; não há fallback
para Qwen. A origem é somente leitura e cada resposta usada recebe hash no relatório.
`cold_response_cache_valid` fica falso neste modo. O tempo mede o replay mais os
reparos, portanto não deve ser comparado ao tempo de uma rodada fria completa.

Constatação de código: o alvo v1.2 está fora de `active`, enquanto seu schema só
permite IDs de `active` ou null. Assim, a identidade original não pode ser reafirmada
pela revisão. A ausência no histórico recente não prova ausência na cena. Isso é
uma hipótese estrutural para os danos medidos, ainda não uma contagem causal.

Pré-registro de diagnóstico: rodar o teto; repetir `hybrid` e `hybrid-revisao` com
os mesmos argumentos de entrada e `--frozen-base-cache` apontando para a mesma
rodada v1.1 da parte. Usar duas saídas inéditas. Os mapas `frozen_base.response_sha256`
dos dois relatórios devem ser idênticos e conter todas as janelas iniciais; qualquer
divergência ou erro invalida a comparação. Medir salvos/estragados, precisão,
cobertura e regras de consistência com o comparador existente. Critério permanece:
nenhum dano líquido em P1/P2, ganho em P3; este diagnóstico não promove a v1.2.

Na worktree, acrescentar ao comando completo do benchmark, para P1:
`--frozen-base-cache ../hybrid-p01-v11-20260910/cache`.
P2/P3 usam suas respectivas pastas v1.1. Manter os mesmos hashes de livro,
transcrição, alinhamento, configuração e gabarito registrados no baseline. Se
reparos anteriores alterarem o payload de uma janela seguinte, o replay abortará:
isso é evidência de dependência entre etapas, não motivo para ignorar a chave.

Não foi executada campanha Qwen neste turno de implementação. Os resultados
v1.2 abaixo continuam sendo os últimos números medidos.

### 10 de setembro de 2026 — v1.2 reprovada: revisão fora do elenco

Campanha completa em três saídas inéditas, com cache de respostas vazio e Qwen
local `qwen3:8b`. `gold_ceiling.py` confirmou antes que a meta ainda é alcançável.
O candidato `hybrid-revisao` falhou os quatro critérios pré-registrados:

| Desenvolvimento | v1.1 (precisão × cobertura) | v1.2 (precisão × cobertura) | Salvos / estragados | Saldo | Tempo v1.2 |
|---|---:|---:|---:|---:|---:|
| Parte 01 | 95,24% × 98,59% | **93,30% × 98,12%** | 1 / 6 | −5 | 294,3 s |
| Parte 02 | 95,53% × 97,81% | **94,29% × 95,63%** | 3 / 9 | −6 | 218,3 s |
| Parte 03 | 91,44% × 93,43% | **89,97% × 94,00%** | 8 / 11 | −3 | 387,5 s |

P1 e P2 pioraram, P3 teve saldo negativo e seu tempo excedeu os 372,5 s da
v1.1. A v1.2 também trocou 5/34 alvos em P1, 14/18 em P2 e 21/26 em P3 — o oposto
da revisão conservadora pretendida. O alvo “fora do elenco” fica **reprovado**;
não ajustar seu limiar nem promovê-lo para o padrão.

Ressalva importante para a próxima investigação: o diferencial comparou duas
execuções frias completas. Como a primeira leitura do Qwen pode variar entre
execuções, ele mede corretamente a experiência do protocolo inteiro, mas não
atribui causalidade de cada troca somente à revisão v1.2. Antes de desenhar um
novo corretor de atribuições existentes, criar um replay que aplique a segunda
leitura a um primeiro passe congelado; assim o diferencial isolará a regra nova.

Saídas locais ignoradas pelo Git: `output/hybrid-p01-v12-20260910/`,
`output/hybrid-p02-v12-20260910/`, `output/hybrid-p03-v12-20260910/` e
`output/comparacao-p0X-v12/`.

### 10 de setembro de 2026 — integração do benchmark para a v1.2

O primeiro disparo da campanha parou antes do Qwen: o motor e a configuração
aceitavam `hybrid-revisao`, mas `benchmark_book_speakers.py` mantinha uma lista
duplicada sem esse valor. A lista passou a ser única (`BOOK_PROTOCOLS`, em
`config.py`) e compartilhada pelo validador e pelo CLI. O comportamento do motor,
os números e o pré-registro da v1.2 não mudaram. A próxima execução deve usar a
mesma saída planejada; a tentativa anterior não criou resultado nem cache útil.

### 10 de setembro de 2026 — v1.2: a revisão de quem está fora do elenco (PRÉ-REGISTRO, não medida)

**Escrita, testada em unidade, não executada.** Nenhum número deste repositório
mudou. O que segue é o pré-registro que a campanha tem de cumprir para a v1.2 ser
aceita ou descartada — escrito antes de rodar, de propósito.

**O problema.** A v1.1 só repara **lacuna**: turno que o primeiro passe deixou sem
voz. Na P3 ela fez isso bem (25/28 aceitas, 16/16 da cena 27, nenhum erro de
reparação). Mas os **28 erros que restam são turnos já atribuídos**, e o roteador
nunca olha para eles — por decisão explícita, porque sobrescrever atribuição
contextual foi o que a memória completa fez, e ela destruiu acertos em P1 e P2.

**O alvo novo.** Turno `contextual` cujo `speaker_entity_id` **não aparece no elenco
estabelecido da própria cena** (o mesmo `active` que o gate já calcula: âncoras
literais recentes mais hipóteses que se repetiram ao menos duas vezes). Não é
"revisar o que parece errado" — é "revisar quem escolheu alguém que ninguém viu
falando aqui, e sem âncora literal que o sustente".

Três exclusões que não se negociam, e cada uma tem teste:

- `explicit` fica de fora — âncora literal é fato do narrador, e é aí que começa a
  assimetria que protege P1/P2;
- o que o próprio roteador reparou fica de fora, senão ele revisa a si mesmo a cada
  janela seguinte;
- quem **está** no elenco fica de fora, mesmo que a atribuição esteja errada. Esse
  caso continua sendo assunto do modo sombra, não desta versão.

**O que acontece com a resposta.** Só troca com um R do catálogo e confiança ≥ 0,95.
Responder `null` **mantém** a atribuição do primeiro passe — e isso é contado em
`revisao_mantida`, não em `rejected_repairs`: manter é o desfecho esperado de uma
revisão saudável, e somar os dois faria a v1.2 parecer quebrada justamente quando
está sendo conservadora. A troca **não** soma em `assigned`: trocar voz não é
preencher silêncio, e contá-la faria a cobertura mentir.

**A conta que a v1.2 precisa fechar na P3** (350 dubláveis, hoje 327 atribuídos, 299
corretos, 28 errados):

- cobertura ≥ 95% exige **333 atribuídos** — a v1.2 sozinha não mexe nisso, porque só
  troca voz; quem move a cobertura continua sendo a reparação de lacuna da v1.1;
- precisão ≥ 95% com 327 atribuídos exige **311 corretos**, ou seja **12 dos 28 erros
  convertidos**.

**Critério de aprovação, definido antes de rodar:**

1. **P1 e P2 não podem piorar.** É o filtro mais barato e o que reprovou a memória
   completa (+24 na P3, −7 e −5 em P1/P2). Qualquer dano líquido em P1 ou P2 reprova
   a v1.2, mesmo que a P3 melhore.
2. **Saldo diferencial positivo na P3**, medido por `candidate_saves` menos
   `candidate_harms` contra a v1.1 — não contra o baseline frio.
3. **`revisao_trocada` tem de ser pequeno perto de `revisao_targets`.** Uma revisão
   que troca quase tudo que olha não está sendo conservadora: está repetindo a
   memória completa por outro caminho.
4. Custo: as chamadas extras não podem estourar o tempo da v1.1 (372,5 s na P3).

**Como medir (as duas rodadas, mesmo cache zerado):**

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
# baseline da comparação = a v1.1 já medida; candidato = v1.2
& .venv\Scripts\python.exe scripts\compare_speaker_runs.py `
  --gold benchmarks\part03_gold.yaml `
  --baseline output\hybrid-p03-v11-20260910\analysis.json `
  --candidate revisao=output\hybrid-p03-v12-<data>\analysis.json `
  --output output\comparacao-p03-v12
```

O protocolo é `hybrid-revisao` em `book_first.protocol`. O `hybrid` continua sendo a
v1.1, sem alteração nenhuma de comportamento — há teste garantindo que sem a opção
nenhum turno atribuído vira alvo.

**Se reprovar:** o alvo "fora do elenco" morre, e o que sobra é o modo sombra sobre
as atribuições de alta confiança, como o MEGAZORD já previa. Não insistir por
ajuste de limiar — o limiar não é o problema quando a premissa do alvo é a errada.

### 10 de setembro de 2026 — o diferencial passa a dizer QUAL regra escreveu a voz errada

Mudança de ferramenta de diagnóstico; **o motor não muda e nenhuma métrica se
desloca**. Não requer campanha nova: basta rodar `compare_speaker_runs.py` sobre
os `analysis.json` que já existem.

`turn_consistency` carimba cada turno que reescreve (`sanduiche_de_tres_turnos`,
`vocativos_reciprocos`, `referencia_em_terceira_pessoa`, `resposta_ao_vocativo`) e
cada um em que abstém por falta de alternativa. O comparador trazia
`review_issue` e `hybrid_repair`, mas **não trazia esse carimbo** — então não havia
como separar, entre os erros que sobram, os que vieram da primeira leitura dos que
uma regra existente escreveu.

A distinção decide o próximo passo, e as duas conclusões levam a trabalhos opostos:
erro sem carimbo é lacuna de mecanismo; erro carimbado é regra que teve a chance de
decidir e decidiu errado — aí o caminho é apertar a condição dela, não escrever
mecanismo novo.

O que passou a sair:

- coluna `<candidato>_consistency_rule` no CSV, para filtro manual por regra;
- `wrong_by_consistency_rule` no JSON;
- seção **"Erros que restaram, por regra que escreveu a voz"** no relatório em
  Markdown, com `sem_regra` para o que veio da primeira leitura.

Dois testes novos em `tests/test_speaker_differential.py`: um garante a separação
entre erro carimbado e erro sem carimbo; o outro garante que regra que ACERTOU não
aparece como causadora de dano.

### 10 de setembro de 2026 — campanha v1.1: reparação validada, meta final ainda reprovada

Saídas inéditas, cache Qwen zerado e `scripts/gold_ceiling.py` executado antes da
campanha. A v1.1 eliminou os erros de reparação e passou todos os critérios
operacionais do pré-registro anterior:

| Desenvolvimento | Precisão | Cobertura | Corretos | Errados | Abstenções | Tempo | Chamadas |
|---|---:|---:|---:|---:|---:|---:|---:|
| Parte 01 | **95,24%** | **98,59%** | 200 | 10 | 1 | 281,8 s | 15 |
| Parte 02 | **95,53%** | **97,81%** | 171 | 8 | 3 | 196,4 s | 12 |
| Parte 03 | 91,44% | 93,43% | 299 | 28 | 10 | 372,5 s | 22 |

Na P3, a v1.1 recuperou **16/16** lacunas da cena 27 e teve saldo de **+17**
acertos contra o baseline (19 salvos, 2 estragados). A cobertura avançou 4,57
pontos; a precisão, 0,76. Não houve erro de reparação, e o tempo caiu de 642,7 s
na v1 para 372,5 s, abaixo dos 385,6 s do baseline registrado. Ainda assim, P3
está abaixo dos 95% exigidos nos dois lados: o motor continua sem validação para
uso geral.

P1 também ultrapassou 95×95 e P2 repetiu exatamente o baseline porque nenhum
turno dela foi elegível à reparação. Isto confirma que o gate não força memória
onde ela não tem motivo estrutural para atuar; não prova generalização.

Arquivos locais: `output/hybrid-p01-v11-20260910/`,
`output/hybrid-p02-v11-20260910/`, `output/hybrid-p03-v11-20260910/` e os
respectivos diferenciais em `output/hybrid-speaker-worktree/output/`.

**Próxima decisão de implementação:** atacar as 28 vozes erradas ainda presentes
na P3 sem mexer na reparação de lacunas já aprovada. Qualquer proposta deve usar
o CSV diferencial por turno e preservar P1/P2; não iniciar outra campanha antes
de um novo pré-registro.

### 10 de setembro de 2026 — primeira medição híbrida e correção v1.1

A v1 foi medida com cache Qwen novo e reprovou o pré-registro:

| Desenvolvimento | Precisão | Cobertura | Corretos | Errados | Abstenções | Tempo | Chamadas |
|---|---:|---:|---:|---:|---:|---:|---:|
| Parte 01 | 93,30% | 98,12% | 195 | 14 | 2 | 456,7 s | 16 |
| Parte 03 | 91,03% | 89,14% | 284 | 28 | 25 | 642,7 s | 22 |

Na P3, a cobertura subiu só 0,28 ponto e a precisão 0,35 ponto sobre o baseline;
o ganho ficou muito abaixo dos 3 pontos pré-registrados. P2 não foi executada,
pois o defeito estrutural já estava reproduzido em P1 e P3.

A causa direta apareceu no próprio audit: o Qwen criou/ecoou `entities` em uma
reparação da P1 e em outra da P3. A v1 rejeitava a resposta inteira, inclusive
assignments que apontavam apenas para IDs R permitidos. Isso bloqueou justamente
a reparação da cena longa que motivou o híbrido.

`hybrid-speaker-router-v1.1` muda somente o contrato da segunda leitura:

- schema dinâmico contém apenas `assignments`, com enum exato de IDs de turno e
  falantes R já estabelecidos;
- entidade extra é contada e ignorada; nunca entra no catálogo e nunca pode ser
  usada como falante;
- `num_predict` da reparação passa a 72 tokens por alvo, entre 256 e 2048, em vez
  de 4096; o contexto de entrada não foi reduzido;
- testes cobrem entidade intrusa, ID intruso, schema fechado e orçamento.

**Pré-registro consumido pela v1.1:** repetir primeiro a P3. A correção só avança se não houver
erro de reparação, recuperar pelo menos 10 das 16 lacunas da cena 27, não aumentar
vozes erradas e reduzir o tempo da P3 frente aos 642,7 s da v1. Depois disso P1
mede regressão; P2 continua dispensável até esses critérios passarem.

### 9 de setembro de 2026 — Megazord conservador e auditoria por turno

Três rodadas com memória local à cena foram comparadas ao baseline, turno por
turno. A memória completa não pode virar padrão: salvou 32 e estragou 8 acertos
na Parte 03, mas teve saldo **-7** na Parte 01 e **-5** na Parte 02. Isso confirma
que escolher um motor inteiro por média mistura ganhos e regressões.

Entrou `--protocol hybrid` (`hybrid-speaker-router-v1`):

- primeira leitura idêntica ao `compact-speakers-v1`;
- âncora literal nunca é anulada por discordância do modelo;
- segunda leitura só para turnos que continuaram sem falante;
- gate observável: não é a primeira janela da cena, há 2–4 identidades
  estabelecidas e uma identidade baseada apenas no modelo precisa aparecer ao
  menos duas vezes no histórico recente;
- a reparação não cria personagem, não troca uma atribuição já aceita e exige
  confiança declarada ≥0,95;
- histórico limitado a 12 decisões da mesma cena; nenhum nome ou regra do livro
  de desenvolvimento foi codificado.

Também entrou `scripts/compare_speaker_runs.py`. Ele produz CSV, JSON e Markdown
com `candidate_saves`, `candidate_harms`, preenchimento errado, abstenção segura
e saldo por cena. Os relatórios locais das três comparações ficam em
`output/hybrid-speaker-worktree/output/differential-p0X/` e são ignorados pelo
Git. Detalhes em `docs/MEGAZORD-HIBRIDO.md`.

**Pré-registro consumido pela campanha de 10/09 (todas as partes são desenvolvimento):**

| Condição | Aceitação da v1 híbrida |
|---|---|
| Segurança | Vozes erradas não aumentam em nenhuma das três partes. |
| Ganho alvo | Parte 03 recupera ao menos 10 das 16 lacunas da cena 27. |
| Cobertura | Parte 03 sobe pelo menos 3 pontos percentuais. |
| Regressão | P1 e P2 mantêm precisão a no máximo 0,5 ponto do baseline. |
| Custo | Registrar chamadas extras e tempo; reparação não pode rodar em toda janela. |

Antes da campanha, execute `scripts/gold_ceiling.py`. Use saída inédita e
`--protocol hybrid`; depois compare com o baseline por meio do novo script. A
meta final continua sendo **95% de precisão e 95% de cobertura**, simultaneamente.

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
