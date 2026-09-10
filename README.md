# Audio-Book-Voice-Adapt

Ferramenta local para detectar falas em audiobooks e aplicar **voice conversion somente a personagens explicitamente habilitados**, preservando a narração e qualquer trecho incerto.

> Estado: pipeline funcional e conservador. A qualidade final depende dos modelos Seed-VC, das referências de voz, da fidelidade do texto do livro e do áudio de entrada. Leia [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) para escolhas e limitações.

Para um roteiro direto, incluindo onde colocar cada arquivo, consulte [GUIA_DE_USO.md](GUIA_DE_USO.md).

## Estado atual — 10 de setembro de 2026

**Próxima implementação pronta, ainda sem campanha Qwen:** ablações controladas
de prompt e schema e modo `speaker-only`, que separa identidade da classificação
recebida do inventário. Em `--protocol hybrid`, use `--attribution-contract`;
o roteiro completo e as faixas estão no topo do [RODAR.md](RODAR.md).
O diagnóstico revisado mostrou que, dos 40 acertos perdidos pelo hybrid-catalog,
18 viraram `unknown` e dez decisões inválidas; só sete das 25 menções rejeitadas
têm recuperação única ignorando caixa. Normalizar strings sozinho é insuficiente.
O resultado medido permanece **79,42% × 97,20%** para hybrid v1.1 na P4 e
**80,20% × 78,80%** para o candidato reprovado. Nada novo foi promovido.
[Parecer e handoff para Claude](docs/REVISAO-CONTRATO-DE-ATRIBUICAO.md).

**A Parte 04 foi o holdout novo do mesmo livro e reprovou.** O primeiro passe
frio do `hybrid` v1.1 foi recuperado por cache congelado (15/15 respostas exatas),
pois o gravador do relatório falhou ao serializar um metadado de data. O placar é
**79,42% de precisão e 97,20% de cobertura** nos 250 turnos dubláveis: 193
corretos, 50 vozes trocadas, 5 abstenções e 2 falas não localizadas. Há cinco
ocorrências de `Vilfrid Wenck`→`Wenck` a auditar como nomenclatura, mas mesmo
aceitando-as a precisão seria apenas 81,48%. A falha é real: novos interlocutores
de cenas densas foram confundidos com o elenco já conhecido e o híbrido não fez
reparos porque o primeiro passe não deixou lacunas. A P4 agora é desenvolvimento;
o produto ainda não está validado para uso geral.

O candidato `hybrid-catalog` v1 atacou a falha estrutural observada nessa rodada. O
contrato que antes existia apenas em português no prompt
agora também existe no schema do decodificador: entidades conhecidas usam somente
IDs `E`, pessoas realmente ausentes precisam ser propostas com IDs `N`, e cada
janela aceita apenas os IDs de turno e de catálogo que recebeu. Isso impede a
resposta malformada vista na P4, na qual o Qwen devolveu entradas `E` como se fossem
novas, todas rejeitadas silenciosamente pelo validador. O modo também diz
explicitamente para abster em vez de encaixar um recém-chegado no elenco conhecido
e trata autorreferência pelo nome como evidência negativa, com exceções. Não há
regra, nome ou vocabulário de fantasia do livro no motor. A campanha fria P4
**reprovou**: 80,20% de precisão e 78,80% de cobertura (158 corretos, 39 errados,
51 abstenções e 2 não localizadas). Ela salvou 5 decisões do baseline, mas estragou
40. Foram 63 propostas anônimas, das quais 38 aceitas (23 identidades criadas)
e 25 recusadas. A rodada mudou schema e prompt juntos; ainda não isolou a causa
do colapso de tipos. Portanto o
contrato estrito não entra no motor padrão. A análise e a próxima hipótese ficam em
[RODAR.md](RODAR.md).

Auditoria textual dos 28 casos divergentes de P3: **25 erros do motor confirmados
pelo parecer, 3 em dúvida, nenhuma correção de gabarito demonstrada**. Revisão por
assistente com consulta ao EPUB; não independente. Pontuação da v1.1 permanece
**91,44% × 93,43%**. [Parecer detalhado (contém spoilers)](docs/AUDITORIA-P03-28-CASOS.md).

O benchmark aceita `--frozen-base-cache <rodada>/cache`: reutiliza respostas exatas
do primeiro passe e executa somente os reparos novos. Registra hashes das respostas,
interrompe se uma requisição não existir e identifica o resultado como replay, nunca
como rodada fria. Ferramenta preparada; nenhuma melhoria de precisão foi medida com ela.

**Se você chegou agora, leia [RODAR.md](RODAR.md).** Ele tem o que rodar, em um
comando, e o que mandar de volta. O que mudou e por quê fica em
[docs/RESULTADO-PART01.md](docs/RESULTADO-PART01.md).

| Indicador | Faixa nas campanhas híbridas v1.1/v1.2 em P1–P3 | Meta |
|---|---:|---:|
| Precisão sobre falas dubláveis | **89,97%–95,53%** | 95% |
| Cobertura sobre falas dubláveis | **93,43%–98,59%** | 95% |

| Desenvolvimento | Precisão | Cobertura |
|---|---:|---:|
| Parte 01, baseline `compact` | **94,74%** | **98,12%** |
| Parte 02, baseline `compact` | **95,53%** | **97,81%** |
| Parte 03, baseline `compact` | **90,68%** | **88,86%** |

As três partes já medidas são desenvolvimento: seus erros foram consultados. O melhor
resultado confirmado não é um único número agregado; a Parte 03 mostra que o
motor atual ainda não generaliza entre regimes de cena.

O protocolo experimental `hybrid` preserva o `compact` como primeira
leitura, nunca derruba uma âncora literal e chama uma segunda leitura curta
somente para lacunas em continuações de cena com 2–4 falantes já estabelecidos.
Ele não substitui acertos do baseline e não consulta o gabarito durante a
execução. A v1 foi medida e **reprovou**: P1 ficou em 93,30% × 98,12% e P3 em
91,03% × 89,14%. Duas respostas de reparação foram descartadas porque o Qwen
ecoou entidades apesar da instrução; a v1.1 ignora essas entidades sem permitir
seus IDs, restringe o schema aos falantes estabelecidos e limita a saída da
reparação. Medida em 10/09, a v1.1 obteve P1 **95,24% × 98,59%**, P2
**95,53% × 97,81%** e P3 **91,44% × 93,43%**. Ela recuperou 16 lacunas da cena
27 da P3, sem elevar vozes erradas, mas a P3 ainda reprova a meta de 95% × 95%; o
protocolo continua experimental e não é o padrão. O comparador
`scripts/compare_speaker_runs.py` registra por turno onde cada motor salva,
estraga, abstém ou apenas troca um erro por outro — e, desde 10/09, **qual regra de
consistência escreveu cada voz errada que sobrou**, o que separa "faltou mecanismo"
de "regra existente errou". Projeto, resultados e pré-registro:
[docs/MEGAZORD-HIBRIDO.md](docs/MEGAZORD-HIBRIDO.md).

A lista de protocolos da configuração e do benchmark vem da mesma constante,
evitando que um modo aceito pelo motor seja rejeitado apenas pela interface de
linha de comando.

O protocolo `hybrid-revisao` (v1.2) foi medido, **reprovou e foi removido do
código** — está no histórico (`8fe3851`), não na lista de protocolos.

`scripts/auditar_erros.py` fecha a outra ponta: lista **quais** turnos erraram, com
os vizinhos e o falante atribuído a cada um, para uma pessoa responder turno a turno
se o motor errou ou se o rótulo do gabarito está errado. Os gabaritos declaram que
não passaram por revisor humano independente, e essa conferência nunca foi feita. Ele acrescentava à
v1.1 uma revisão de turno contextual cujo falante não aparece no elenco estabelecido
da cena; âncoras literais continuavam intocáveis e `null` mantinha a atribuição. A
primeira campanha fria piorou P1/P2/P3. O replay posterior congelou cada resposta
do primeiro passe e isolou a revisão: P1 ficou exatamente igual à v1.1; P2 caiu de
**95,53% × 97,81%** para **93,75% × 96,17%** (saldo −6); P3 caiu de
**91,44% × 93,43%** para **89,97% × 94,00%** (saldo −3). Portanto esse alvo não
entra no motor padrão. Dos danos isolados, 7/8 em P2 e 10/11 em P3 foram turnos
marcados pela própria revisão; a hipótese de instabilidade do primeiro passe foi
eliminada para esses dois resultados.

A primeira rodada realmente externa, na Parte 02, ficou em **91,53% de precisão
e 96,72% de cobertura**: cobertura aprovada, precisão reprovada. Depois de ler
esses erros, `turn-consistency-v2` passou a tratar vocativos recíprocos, inversão
local de fase, referência ao próprio personagem em terceira pessoa e monólogos
compostos. Reaplicada offline sobre as respostas frias já existentes, a versão
candidata marca **95,53% × 97,81% na Parte 02** e **93,20% × 96,71% na Parte 01**.
Isso era uma estimativa de desenvolvimento. A rodada fria posterior confirmou a
Parte 02 exatamente: **95,53% × 97,81%**. Na Parte 01, o pipeline completo foi
melhor que a reaplicação offline e chegou a **94,74% × 98,12%** (198 corretos,
11 erros e 2 abstenções sobre 213 dubláveis): falta uma atribuição correta — ou
uma atribuição errada que possa ser abstida sem baixar a cobertura de 95% — para
atingir a meta. A Parte 02 permanece desenvolvimento, pois seus erros foram
consultados para criar a v2; estes resultados não demonstram generalização.

> **Pendente de confirmação:** três consertos no parser de âncoras — cargo entre
> o artigo e o nome, preposição com pronome (`respondeu por ela Geralt`) e cargo
> sem nome resolvido pelo próprio livro (`o feiticeiro Radcliffe` ensina quem é
> `o feiticeiro`) — levaram as âncoras corretas de 35 para **49**, sem nenhuma
> falsa. Reaplicado sobre a rodada fria, dá **95,17% de precisão e 97,18% de
> cobertura** — a meta. É estimativa: âncora nova muda o que o modelo recebe,
> então os outros turnos podem se mexer. **A próxima rodada fria decide.**

O gabarito da Parte 01 foi auditado contra o livro em 08/09 e **não tem erro
conhecido**: [docs/AUDITORIA-DO-GABARITO.md](docs/AUDITORIA-DO-GABARITO.md).

**A Parte 02 não é mais holdout.** Seus 183 rótulos continuam congelados, mas os
erros da primeira rodada foram usados para criar a versão 2. Ela agora é um
segundo conjunto de desenvolvimento. A próxima validação honesta será uma parte
nova, com gabarito congelado antes de qualquer resultado do motor.

**A Parte 03 foi medida como holdout intocado e reprovou:** 90,68% de precisão e
88,86% de cobertura sobre 350 falas dubláveis (282 corretas, 29 erradas e 26
abstenções; outras 13 falas não foram localizadas no áudio). O gabarito P684–1126
foi congelado antes da execução, mas, após a leitura do resultado, agora também é
desenvolvimento. Ele foi escrito por assistente e ainda não tem auditoria humana
independente. O motor não está validado para uso geral.

### Duas regras de produto que mandam em tudo

1. **É melhor não trocar uma voz do que trocar errado.** Sem certeza, o turno
   fica sem atribuição e mantém a voz do narrador. Abstenção é a saída segura,
   não erro — o único defeito que conta é voz trocada errada.
2. **Figurante de uma cena só não precisa de voz.** Esses 42 turnos saem do
   denominador que decide o produto; sobram 213 dubláveis. Ficam visíveis na
   linha `figurante` do placar, nunca escondidos.

As duas estão em [AGENTS.md](AGENTS.md) e substituem a regra antiga, que mandava
contar omissão como erro e perseguir 90% sobre todas as 255 falas.

### O que faltava, e a causa tinha nome

Doze dos vinte turnos pendentes estavam na cena do carvalho, e **não era o
modelo**: o livro atribui as falas do Vilibert todas as vezes — `observou o
chanceler Vilibert`, `urrou o chanceler Vilibert` — e o parser não enxergava,
porque a regex de âncora só aceitava `verbo + artigo + Nome` e ali há um **cargo
no meio**. Sem âncora, o modelo entregava as falas dele a quem tinha.

Consertado, junto com cinco verbos de fala que faltavam (`esbravejou`, `bradou`,
`indagou`, `piaram`, `apoiaram`). O risco do conserto é o oposto — aceitar
palavra demais faria `disse que Ana estava certa` ancorar na Ana — e por isso há
uma lista de palavras funcionais e `tests/test_ancora_com_titulo.py`.

Sobra a coreferência por descrição: `sorriu o feiticeiro`, `refutou a guerreira`,
`retrucou o anão`. São cinco turnos, e exigem ligar a descrição ao nome que o
próprio texto já apresentou (`o feiticeiro Radcliffe` ensina quem é `o
feiticeiro`). Ainda não feito.

### Antes de qualquer campanha com GPU

```bat
.venv\Scripts\python scripts\gold_ceiling.py
```

Trinta segundos, sem GPU. Diz se a meta cabe no gabarito. Cinco campanhas foram
comparadas contra um teto de 81,57% sem que ninguém tivesse conferido — a
história está em [docs/TETO-DO-GABARITO.md](docs/TETO-DO-GABARITO.md).

### Documentos, na ordem em que servem

- [RODAR.md](RODAR.md) — o que rodar agora, o que mandar de volta, o registro do que mudou.
- [docs/RESULTADO-PART01.md](docs/RESULTADO-PART01.md) — a última medição e o que ela desmentiu.
- [docs/TETO-DO-GABARITO.md](docs/TETO-DO-GABARITO.md) — por que o placar mentia, e as duas decisões de produto.
- [docs/AUDITORIA-DO-GABARITO.md](docs/AUDITORIA-DO-GABARITO.md) — o gabarito bate com o livro, e o que a auditoria não prova.
- `benchmarks/part02_gold.yaml` — gabarito congelado da Parte 02, agora marcado como desenvolvimento após o primeiro teste externo.
- [AGENTS.md](AGENTS.md) — as preferências e as regras que não se negociam.
- [docs/SPEAKER_ATTRIBUTION_HANDOFF.md](docs/SPEAKER_ATTRIBUTION_HANDOFF.md) — histórico dos cinco protocolos. **Os números dele são anteriores à correção do avaliador.**
- [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) — escolhas de transcrição, conversão e GPU.
- [GUIA_DE_USO.md](GUIA_DE_USO.md) — onde colocar cada arquivo.

Os experimentos `scene`, `lightweight` e `source_subjects` regrediram e ficam só
para reprodução. O padrão é `compact` com `turn_consistency`.

## Requisitos

- Windows 11, Python 3.11 para a aplicação e Python 3.10 para Seed-VC
- NVIDIA recente e driver atualizado (CPU funciona, mas é muito lento)
- FFmpeg/FFprobe no `PATH`
- Aproximadamente 15–25 GB livres para ambientes e modelos

## Instalação

No Prompt de Comando:

```bat
setup.bat
setup_seedvc.bat
check_gpu.bat
```

`setup.bat` cria `.venv`, instala PyTorch CUDA 13.0, faster-whisper e as bibliotecas CUDA 12/cuDNN 9 exigidas pelo CTranslate2 lado a lado. Se FFmpeg estiver ausente e `winget` existir, tenta instalar `Gyan.FFmpeg`. Reabra o terminal após a instalação do FFmpeg.

`setup_seedvc.bat` clona o projeto oficial em `models/seed-vc` e usa um ambiente Python 3.10 separado. Como os pins PyTorch 2.4/CUDA 12.6 do upstream antecedem Blackwell, o script substitui somente o trio PyTorch pelo wheel oficial 2.11/CUDA 13.0. Os pesos são baixados pelo próprio Seed-VC no primeiro segmento convertido.

Para instalar Python 3.10, se necessário:

```bat
winget install Python.Python.3.10
```

## Preparação

1. Coloque um arquivo ou capítulos em `input/`. MP3, M4A, FLAC, WAV, OPUS, OGG e AAC são aceitos.
2. Coloque referências WAV limpas, de preferência de 10–30 segundos, em `voices/`.
3. Edite `config/characters.json`. Só personagens em `mode: convert` (ou `auto` explicitamente habilitado) e com referência existente são elegíveis.
4. Opcionalmente, forneça o livro em TXT, EPUB, SRT ou JSON. Isso melhora substancialmente a detecção estrutural e a atribuição.

Você é responsável por obter consentimento e direitos para as vozes e obras utilizadas. Não use o software para personificação enganosa ou fraude.

## Uso

Ative o ambiente ou use `run.bat`:

Interface gráfica no Windows (dê dois cliques):

```bat
ABRIR_INTERFACE.bat
```

Ela permite escolher capítulos/livro/saída, importar automaticamente os personagens encontrados, escolher suas vozes, alterar configurações e acompanhar capítulo, tempo e porcentagem sem digitar comandos.

Na edição de personagens, o campo **Referência de voz** é uma lista dos arquivos disponíveis em
`voices/`; use **Atualizar lista** se copiar um arquivo para a pasta com a interface aberta.

Também inclui seleção individual de capítulos, aliases de personagens, estimativa de tempo/espaço, checkpoints retomáveis e prévias original/convertida para comparação A/B.

### Banco de voz

A aba **BANCO DE VOZ** recebe WAV, MP3, M4A, FLAC, Opus, OGG ou AAC e faz diarização local:

1. selecione o áudio e o intervalo a analisar (10 segundos a 1 hora);
2. deixe a quantidade de vozes em `Automático` ou informe quantas pessoas existem;
3. clique em **Reconhecer e separar vozes**;
4. ouça a amostra de cada grupo e informe o nome do personagem;
5. expanda a voz, ouça os trechos individuais e exclua qualquer trecho contaminado;
6. clique em **Cortar e salvar voz**.

O app escolhe os trechos mais limpos, monta até 25 segundos de referência em `voices/`, atualiza
`config/characters.json` e habilita o personagem para conversão. A diarização usa Resemblyzer no
ambiente local do Seed-VC; execute `setup_seedvc.bat` antes do primeiro uso. Falas simultâneas e música
de fundo não podem ser isoladas perfeitamente e devem ser evitadas.

A opção **Limpeza leve de ruído** vem ativada somente na cópia interna usada para reconhecimento. Ela
reduz ruído constante e ajuda a separar falantes, mas previews e referências são recortados de uma
cópia mestre não filtrada em 44,1/48 kHz. Assim, a análise pode ser simplificada sem deixar a voz salva
abafada. Música, eco ou vozes sobrepostas ainda precisam ser evitados ou excluídos na revisão.

O detector faz cortes de no máximo quatro segundos, mede a consistência interna e exclui por padrão
trechos curtos ou suspeitos. Na árvore de resultados, dê dois cliques para ouvir um trecho e use
**Incluir/excluir trecho** para controlar exatamente o que entrará na referência final.

```bat
.venv\Scripts\activate
python main.py analyze input --book-text livro.txt
python main.py process input --book-text livro.txt --dry-run
python main.py process input --book-text livro.txt
```

Idioma explícito e configuração alternativa:

```bat
python main.py analyze input\Chapter 01.mp3 --language pt
python main.py process input --config config\config.yaml --characters config\characters.json
python main.py analyze input\amostra.wav --model tiny --device cuda
```

`analyze` e `--dry-run` não criam áudio alterado; ambos geram `output/analysis.json`, `report.json` e `report.html`. `process` cria arquivos como `Chapter 01 Enhanced.mp3`.

## Regra de decisão

Um trecho só é convertido quando todas estas condições são verdadeiras:

1. o falante foi identificado e existe em `characters.json`;
2. o `mode` resolve para conversão e a referência existe;
3. confiança do falante atinge `speaker_confidence_threshold`;
4. com livro, alinhamento atinge `alignment_confidence_threshold`;
5. a duração mínima é atingida;
6. não é interjeição/som curto inseguro.

Se qualquer condição falhar ou o backend lançar erro, o original permanece. Não há decisão baseada apenas em uma voz “soar feminina”.

## Configuração

As opções documentadas ficam em `config/config.yaml`:

- `device`: `auto`, `cuda` ou `cpu`;
- `transcription.model`: modelo faster-whisper; `large-v3` prioriza precisão;
- `speaker_confidence_threshold` e `alignment_confidence_threshold`: limites de segurança;
- `padding_ms` e `crossfade`: integração de bordas;
- `minimum_segment_duration`: duração mínima global; pode ser sobrescrita por personagem;
- `voice_conversion.backend`: `auto`, `seedvc`, `openvoice` ou `rvc`;
- `output.format`/`bitrate`: MP3, M4A, FLAC, WAV, OPUS ou OGG;
- `llm`: revisor contextual via Ollama local ou endpoint OpenAI-compatible;
- `llm.automatic_confidence`: limite conservador para uma decisão sem consenso;
- `llm.critic_enabled`: faz uma segunda leitura independente da cena;
- `llm.consensus_confidence`: limite usado quando as leituras concordam e o bloco tem dois participantes.

### LLM local com Ollama

```yaml
llm:
  enabled: true
  provider: ollama
  base_url: http://localhost:11434
  model: qwen3:8b
  timeout_seconds: 90
  reasoning: false
  automatic_confidence: 0.98
  critic_enabled: true
  consensus_confidence: 0.90
```

Dê dois cliques em `setup_qwen.bat` para instalar o Ollama e baixar o modelo, ou execute
`ollama pull qwen3:8b` manualmente uma vez. O modo normal
desativa raciocínio prolongado porque ele pode multiplicar o tempo sem garantir mais acertos. A IA
recebe blocos conversacionais locais do livro, nunca o timbre do narrador. A segunda leitura aumenta
o tempo da primeira análise, mas divergências ficam para revisão humana em vez de entrarem no áudio.
Para API compatível, use
`provider: openai-compatible`, uma `base_url` terminada antes de `/chat/completions`, e defina a
variável indicada por `api_key_env`. Respostas são cacheadas pelo hash de todo o contexto.

## Personagens e referências

Exemplo mínimo:

```json
{
  "Ana": {
    "gender": "female",
    "age_group": "adult",
    "voice_reference": "voices/ana.wav",
    "mode": "convert",
    "pitch_shift": 0
  },
  "Carlos": {"gender": "male", "mode": "original"}
}
```

Compartilhar uma referência gera aviso quando `allow_shared_voice_references: true`; se falso, a configuração é rejeitada. `pitch_shift` é apenas complementar, não o mecanismo principal de identidade.

Os modos são `original` (preservar), `convert` (converter), `auto` (conservador; preserva por padrão) e `ignore` (preservar sem trabalho específico). Gênero, idade, espécie e pitch são metadados e nunca autorizam conversão. `__narrator__` é `original` por padrão.

Gerenciamento pela CLI:

```bat
python main.py character add "Vesemir" --mode convert --voice voices/vesemir_ref.wav
python main.py character set "Geralt" --mode original
python main.py character list
```

## Cache e retomada

Cada fase usa hashes do arquivo, configuração e dependências da etapa. Reexecutar reaproveita transcrição, alinhamento, detecção, LLM e conversões concluídas em `cache/`. Mudanças relevantes geram novas chaves automaticamente. Para invalidar tudo, mova a pasta `cache` para outro local; não edite arquivos de cache à mão.

## GPU e solução de problemas

Execute `check_gpu.bat`. Três estados são independentes: o driver pode detectar a GPU, PyTorch pode ou não ter CUDA, e CTranslate2 pode ou não carregar cuBLAS/cuDNN.

- `PyTorch CUDA: DISABLED`: recrie `.venv` pelo setup e confirme driver NVIDIA atual.
- erro `cublas64_12.dll`/`cudnn_ops64_9.dll`: confirme o wheel CUDA do PyTorch; o programa expõe automaticamente sua pasta `torch/lib` ao CTranslate2.
- memória insuficiente: troque `large-v3` por `medium` ou `distil-large-v3` e reduza processos concorrentes.
- `FFmpeg missing`: execute `winget install Gyan.FFmpeg`, reabra o terminal e repita o diagnóstico.
- RTX 50: use wheels CUDA 13.0 atuais; wheels antigos sem `sm_120` podem falhar.

## Backends de voice conversion

`auto` escolhe o primeiro backend instalado, priorizando Seed-VC. Ele é zero-shot e recebe diretamente áudio-fonte e referência. OpenVoice fica exposto como adaptador, mas não é executado automaticamente neste release devido ao fluxo/checkpoints específicos. RVC funciona apenas se `voice_model` apontar para um `.pth` treinado; uma referência curta não basta.

## Testes

```bat
.venv\Scripts\python -m pytest
```

Os testes cobrem configuração, referências compartilhadas, cache, alinhamento, segmentação em nível de palavra, elegibilidade, ordenação de capítulos e preservação byte a byte quando não há substituições. Um teste FFmpeg é executado quando as ferramentas estão instaladas.

### Benchmark auditado da Parte 01

O gabarito manual fica em `benchmarks/part01_gold.yaml`. Ele separa treino, desenvolvimento e teste
por cenas, registra falas ausentes, pensamentos confundidos com fala, identidades que o livro deixa
ambíguas e turnos cortados antes da continuação. Para comparar uma nova `output/analysis.json`:

```bat
.venv\Scripts\python scripts\evaluate_part01_gold.py
```

O placar lidera com o par **precisão × cobertura** sobre as falas dubláveis, e separa
o desfecho em três — correto, voz trocada errada, sem atribuição — porque abster e
errar não são a mesma coisa para quem escuta. As duas métricas antigas, que contam
omissão como erro, continuam no relatório para comparar com as rodadas anteriores;
os relatórios `benchmarks/PART01_*.md` são anteriores à correção do avaliador.

Para ver turno a turno o que errou, sem GPU:

```bat
.venv\Scripts\python scripts\dump_errors.py --analysis output\<pasta>\analysis.json --output output\<pasta>\erros.csv
```

E para testar uma regra nova sobre uma rodada que já existe, com ganhos e perdas
separados — delta líquido esconde troca de dez por oito:

```bat
.venv\Scripts\python scripts\simulate_rules.py --analysis output\<pasta>\analysis.json
```

## Saídas e auditoria

`report.json` inclui duração, segmentos, falantes, conversões, pulos, erros, GPU, backends, hits de cache e taxa de alinhamento. `report.html` contém os mesmos dados legíveis. Cada fala registra timestamps, scores, motivo, elegibilidade e ação.

### Motor de identificação de falantes

Com um EPUB correspondente ao áudio, o motor usa atribuições explícitas, uma lista ampla de verbos de fala em português, autoapresentações, nomes usados como vocativo, ações narrativas e turnos de conversas entre duas pessoas. Divisores e capítulos do livro encerram a cena para impedir que um personagem seja carregado para a conversa seguinte. Citações e pensamentos dentro de uma fala não viram falas separadas. Inferências só são convertidas quando ultrapassam `speaker_confidence_threshold`; descrições sem nome, como “um camponês”, permanecem desconhecidas.

O motor mantém memória de papéis por cena (`a guerreira`, `o feiticeiro`), respostas a personagens
chamados pelo nome, ações do parágrafo anterior e aliases como `Lobo → Geralt`. Ambiguidades restantes
são revisadas em blocos pelo Qwen; resultados abaixo do limite aparecem em **REVISÃO DE FALAS**.
O reconhecimento acústico não decide mais personagens. O áudio serve para transcrição e alinhamento,
e os cortes finais continuam vindo do arquivo original. As decisões manuais locais ficam em
`config/speaker_overrides.json`.

## Licenças de terceiros

Este projeto é MIT. Seed-VC é GPL-3.0 e permanece uma instalação externa; faster-whisper, PyTorch, FFmpeg e modelos possuem suas próprias licenças. Confira-as antes de distribuir resultados ou empacotar dependências.
