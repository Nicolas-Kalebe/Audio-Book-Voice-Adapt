# Audio-Book-Voice-Adapt

Ferramenta local para detectar falas em audiobooks e aplicar **voice conversion somente a personagens explicitamente habilitados**, preservando a narraÃ§Ã£o e qualquer trecho incerto.

> Estado: pipeline funcional e conservador. A qualidade final depende dos modelos Seed-VC, das referÃªncias de voz, da fidelidade do texto do livro e do Ã¡udio de entrada. Leia [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) para escolhas e limitaÃ§Ãµes.

Para um roteiro direto, incluindo onde colocar cada arquivo, consulte [GUIA_DE_USO.md](GUIA_DE_USO.md).

## Estado atual — 10 de setembro de 2026`r`n`r`nCampanha fria de contratos na Parte 04: `speaker-only` foi o melhor, com 81,15% de precisão e 97,60% de cobertura (198 corretas, 46 erradas, 4 abstenções; 240 s). Melhorou +5 acertos contra o baseline, mas ainda não atinge a meta de 95% e não deve ser promovido. `catalog-schema` (80,86% × 83,60%), `catalog-prompt` (80,45% × 88,00%) e `both` (80,20% × 78,80%) foram rejeitados. Detalhes em output/contracts-p04-20260910-201844-* (ignorado).

**PrÃ³xima implementaÃ§Ã£o pronta, ainda sem campanha Qwen:** ablaÃ§Ãµes controladas
de prompt e schema e modo `speaker-only`, que separa identidade da classificaÃ§Ã£o
recebida do inventÃ¡rio. Em `--protocol hybrid`, use `--attribution-contract`;
o roteiro completo e as faixas estÃ£o no topo do [RODAR.md](RODAR.md).
O diagnÃ³stico revisado mostrou que, dos 40 acertos perdidos pelo hybrid-catalog,
18 viraram `unknown` e dez decisÃµes invÃ¡lidas; sÃ³ sete das 25 menÃ§Ãµes rejeitadas
tÃªm recuperaÃ§Ã£o Ãºnica ignorando caixa. Normalizar strings sozinho Ã© insuficiente.
O resultado medido permanece **79,42% Ã— 97,20%** para hybrid v1.1 na P4 e
**80,20% Ã— 78,80%** para o candidato reprovado. Nada novo foi promovido.
[Parecer e handoff para Claude](docs/REVISAO-CONTRATO-DE-ATRIBUICAO.md).

**A Parte 04 foi o holdout novo do mesmo livro e reprovou.** O primeiro passe
frio do `hybrid` v1.1 foi recuperado por cache congelado (15/15 respostas exatas),
pois o gravador do relatÃ³rio falhou ao serializar um metadado de data. O placar Ã©
**79,42% de precisÃ£o e 97,20% de cobertura** nos 250 turnos dublÃ¡veis: 193
corretos, 50 vozes trocadas, 5 abstenÃ§Ãµes e 2 falas nÃ£o localizadas. HÃ¡ cinco
ocorrÃªncias de `Vilfrid Wenck`â†’`Wenck` a auditar como nomenclatura, mas mesmo
aceitando-as a precisÃ£o seria apenas 81,48%. A falha Ã© real: novos interlocutores
de cenas densas foram confundidos com o elenco jÃ¡ conhecido e o hÃ­brido nÃ£o fez
reparos porque o primeiro passe nÃ£o deixou lacunas. A P4 agora Ã© desenvolvimento;
o produto ainda nÃ£o estÃ¡ validado para uso geral.

O candidato `hybrid-catalog` v1 atacou a falha estrutural observada nessa rodada. O
contrato que antes existia apenas em portuguÃªs no prompt
agora tambÃ©m existe no schema do decodificador: entidades conhecidas usam somente
IDs `E`, pessoas realmente ausentes precisam ser propostas com IDs `N`, e cada
janela aceita apenas os IDs de turno e de catÃ¡logo que recebeu. Isso impede a
resposta malformada vista na P4, na qual o Qwen devolveu entradas `E` como se fossem
novas, todas rejeitadas silenciosamente pelo validador. O modo tambÃ©m diz
explicitamente para abster em vez de encaixar um recÃ©m-chegado no elenco conhecido
e trata autorreferÃªncia pelo nome como evidÃªncia negativa, com exceÃ§Ãµes. NÃ£o hÃ¡
regra, nome ou vocabulÃ¡rio de fantasia do livro no motor. A campanha fria P4
**reprovou**: 80,20% de precisÃ£o e 78,80% de cobertura (158 corretos, 39 errados,
51 abstenÃ§Ãµes e 2 nÃ£o localizadas). Ela salvou 5 decisÃµes do baseline, mas estragou
40. Foram 63 propostas anÃ´nimas, das quais 38 aceitas (23 identidades criadas)
e 25 recusadas. A rodada mudou schema e prompt juntos; ainda nÃ£o isolou a causa
do colapso de tipos. Portanto o
contrato estrito nÃ£o entra no motor padrÃ£o. A anÃ¡lise e a prÃ³xima hipÃ³tese ficam em
[RODAR.md](RODAR.md).

Auditoria textual dos 28 casos divergentes de P3: **25 erros do motor confirmados
pelo parecer, 3 em dÃºvida, nenhuma correÃ§Ã£o de gabarito demonstrada**. RevisÃ£o por
assistente com consulta ao EPUB; nÃ£o independente. PontuaÃ§Ã£o da v1.1 permanece
**91,44% Ã— 93,43%**. [Parecer detalhado (contÃ©m spoilers)](docs/AUDITORIA-P03-28-CASOS.md).

O benchmark aceita `--frozen-base-cache <rodada>/cache`: reutiliza respostas exatas
do primeiro passe e executa somente os reparos novos. Registra hashes das respostas,
interrompe se uma requisiÃ§Ã£o nÃ£o existir e identifica o resultado como replay, nunca
como rodada fria. Ferramenta preparada; nenhuma melhoria de precisÃ£o foi medida com ela.

**Se vocÃª chegou agora, leia [RODAR.md](RODAR.md).** Ele tem o que rodar, em um
comando, e o que mandar de volta. O que mudou e por quÃª fica em
[docs/RESULTADO-PART01.md](docs/RESULTADO-PART01.md).

| Indicador | Faixa nas campanhas hÃ­bridas v1.1/v1.2 em P1â€“P3 | Meta |
|---|---:|---:|
| PrecisÃ£o sobre falas dublÃ¡veis | **89,97%â€“95,53%** | 95% |
| Cobertura sobre falas dublÃ¡veis | **93,43%â€“98,59%** | 95% |

| Desenvolvimento | PrecisÃ£o | Cobertura |
|---|---:|---:|
| Parte 01, baseline `compact` | **94,74%** | **98,12%** |
| Parte 02, baseline `compact` | **95,53%** | **97,81%** |
| Parte 03, baseline `compact` | **90,68%** | **88,86%** |

As trÃªs partes jÃ¡ medidas sÃ£o desenvolvimento: seus erros foram consultados. O melhor
resultado confirmado nÃ£o Ã© um Ãºnico nÃºmero agregado; a Parte 03 mostra que o
motor atual ainda nÃ£o generaliza entre regimes de cena.

O protocolo experimental `hybrid` preserva o `compact` como primeira
leitura, nunca derruba uma Ã¢ncora literal e chama uma segunda leitura curta
somente para lacunas em continuaÃ§Ãµes de cena com 2â€“4 falantes jÃ¡ estabelecidos.
Ele nÃ£o substitui acertos do baseline e nÃ£o consulta o gabarito durante a
execuÃ§Ã£o. A v1 foi medida e **reprovou**: P1 ficou em 93,30% Ã— 98,12% e P3 em
91,03% Ã— 89,14%. Duas respostas de reparaÃ§Ã£o foram descartadas porque o Qwen
ecoou entidades apesar da instruÃ§Ã£o; a v1.1 ignora essas entidades sem permitir
seus IDs, restringe o schema aos falantes estabelecidos e limita a saÃ­da da
reparaÃ§Ã£o. Medida em 10/09, a v1.1 obteve P1 **95,24% Ã— 98,59%**, P2
**95,53% Ã— 97,81%** e P3 **91,44% Ã— 93,43%**. Ela recuperou 16 lacunas da cena
27 da P3, sem elevar vozes erradas, mas a P3 ainda reprova a meta de 95% Ã— 95%; o
protocolo continua experimental e nÃ£o Ã© o padrÃ£o. O comparador
`scripts/compare_speaker_runs.py` registra por turno onde cada motor salva,
estraga, abstÃ©m ou apenas troca um erro por outro â€” e, desde 10/09, **qual regra de
consistÃªncia escreveu cada voz errada que sobrou**, o que separa "faltou mecanismo"
de "regra existente errou". Projeto, resultados e prÃ©-registro:
[docs/MEGAZORD-HIBRIDO.md](docs/MEGAZORD-HIBRIDO.md).

A lista de protocolos da configuraÃ§Ã£o e do benchmark vem da mesma constante,
evitando que um modo aceito pelo motor seja rejeitado apenas pela interface de
linha de comando.

O protocolo `hybrid-revisao` (v1.2) foi medido, **reprovou e foi removido do
cÃ³digo** â€” estÃ¡ no histÃ³rico (`8fe3851`), nÃ£o na lista de protocolos.

`scripts/auditar_erros.py` fecha a outra ponta: lista **quais** turnos erraram, com
os vizinhos e o falante atribuÃ­do a cada um, para uma pessoa responder turno a turno
se o motor errou ou se o rÃ³tulo do gabarito estÃ¡ errado. Os gabaritos declaram que
nÃ£o passaram por revisor humano independente, e essa conferÃªncia nunca foi feita. Ele acrescentava Ã 
v1.1 uma revisÃ£o de turno contextual cujo falante nÃ£o aparece no elenco estabelecido
da cena; Ã¢ncoras literais continuavam intocÃ¡veis e `null` mantinha a atribuiÃ§Ã£o. A
primeira campanha fria piorou P1/P2/P3. O replay posterior congelou cada resposta
do primeiro passe e isolou a revisÃ£o: P1 ficou exatamente igual Ã  v1.1; P2 caiu de
**95,53% Ã— 97,81%** para **93,75% Ã— 96,17%** (saldo âˆ’6); P3 caiu de
**91,44% Ã— 93,43%** para **89,97% Ã— 94,00%** (saldo âˆ’3). Portanto esse alvo nÃ£o
entra no motor padrÃ£o. Dos danos isolados, 7/8 em P2 e 10/11 em P3 foram turnos
marcados pela prÃ³pria revisÃ£o; a hipÃ³tese de instabilidade do primeiro passe foi
eliminada para esses dois resultados.

A primeira rodada realmente externa, na Parte 02, ficou em **91,53% de precisÃ£o
e 96,72% de cobertura**: cobertura aprovada, precisÃ£o reprovada. Depois de ler
esses erros, `turn-consistency-v2` passou a tratar vocativos recÃ­procos, inversÃ£o
local de fase, referÃªncia ao prÃ³prio personagem em terceira pessoa e monÃ³logos
compostos. Reaplicada offline sobre as respostas frias jÃ¡ existentes, a versÃ£o
candidata marca **95,53% Ã— 97,81% na Parte 02** e **93,20% Ã— 96,71% na Parte 01**.
Isso era uma estimativa de desenvolvimento. A rodada fria posterior confirmou a
Parte 02 exatamente: **95,53% Ã— 97,81%**. Na Parte 01, o pipeline completo foi
melhor que a reaplicaÃ§Ã£o offline e chegou a **94,74% Ã— 98,12%** (198 corretos,
11 erros e 2 abstenÃ§Ãµes sobre 213 dublÃ¡veis): falta uma atribuiÃ§Ã£o correta â€” ou
uma atribuiÃ§Ã£o errada que possa ser abstida sem baixar a cobertura de 95% â€” para
atingir a meta. A Parte 02 permanece desenvolvimento, pois seus erros foram
consultados para criar a v2; estes resultados nÃ£o demonstram generalizaÃ§Ã£o.

> **Pendente de confirmaÃ§Ã£o:** trÃªs consertos no parser de Ã¢ncoras â€” cargo entre
> o artigo e o nome, preposiÃ§Ã£o com pronome (`respondeu por ela Geralt`) e cargo
> sem nome resolvido pelo prÃ³prio livro (`o feiticeiro Radcliffe` ensina quem Ã©
> `o feiticeiro`) â€” levaram as Ã¢ncoras corretas de 35 para **49**, sem nenhuma
> falsa. Reaplicado sobre a rodada fria, dÃ¡ **95,17% de precisÃ£o e 97,18% de
> cobertura** â€” a meta. Ã‰ estimativa: Ã¢ncora nova muda o que o modelo recebe,
> entÃ£o os outros turnos podem se mexer. **A prÃ³xima rodada fria decide.**

O gabarito da Parte 01 foi auditado contra o livro em 08/09 e **nÃ£o tem erro
conhecido**: [docs/AUDITORIA-DO-GABARITO.md](docs/AUDITORIA-DO-GABARITO.md).

**A Parte 02 nÃ£o Ã© mais holdout.** Seus 183 rÃ³tulos continuam congelados, mas os
erros da primeira rodada foram usados para criar a versÃ£o 2. Ela agora Ã© um
segundo conjunto de desenvolvimento. A prÃ³xima validaÃ§Ã£o honesta serÃ¡ uma parte
nova, com gabarito congelado antes de qualquer resultado do motor.

**A Parte 03 foi medida como holdout intocado e reprovou:** 90,68% de precisÃ£o e
88,86% de cobertura sobre 350 falas dublÃ¡veis (282 corretas, 29 erradas e 26
abstenÃ§Ãµes; outras 13 falas nÃ£o foram localizadas no Ã¡udio). O gabarito P684â€“1126
foi congelado antes da execuÃ§Ã£o, mas, apÃ³s a leitura do resultado, agora tambÃ©m Ã©
desenvolvimento. Ele foi escrito por assistente e ainda nÃ£o tem auditoria humana
independente. O motor nÃ£o estÃ¡ validado para uso geral.

### Duas regras de produto que mandam em tudo

1. **Ã‰ melhor nÃ£o trocar uma voz do que trocar errado.** Sem certeza, o turno
   fica sem atribuiÃ§Ã£o e mantÃ©m a voz do narrador. AbstenÃ§Ã£o Ã© a saÃ­da segura,
   nÃ£o erro â€” o Ãºnico defeito que conta Ã© voz trocada errada.
2. **Figurante de uma cena sÃ³ nÃ£o precisa de voz.** Esses 42 turnos saem do
   denominador que decide o produto; sobram 213 dublÃ¡veis. Ficam visÃ­veis na
   linha `figurante` do placar, nunca escondidos.

As duas estÃ£o em [AGENTS.md](AGENTS.md) e substituem a regra antiga, que mandava
contar omissÃ£o como erro e perseguir 90% sobre todas as 255 falas.

### O que faltava, e a causa tinha nome

Doze dos vinte turnos pendentes estavam na cena do carvalho, e **nÃ£o era o
modelo**: o livro atribui as falas do Vilibert todas as vezes â€” `observou o
chanceler Vilibert`, `urrou o chanceler Vilibert` â€” e o parser nÃ£o enxergava,
porque a regex de Ã¢ncora sÃ³ aceitava `verbo + artigo + Nome` e ali hÃ¡ um **cargo
no meio**. Sem Ã¢ncora, o modelo entregava as falas dele a quem tinha.

Consertado, junto com cinco verbos de fala que faltavam (`esbravejou`, `bradou`,
`indagou`, `piaram`, `apoiaram`). O risco do conserto Ã© o oposto â€” aceitar
palavra demais faria `disse que Ana estava certa` ancorar na Ana â€” e por isso hÃ¡
uma lista de palavras funcionais e `tests/test_ancora_com_titulo.py`.

Sobra a coreferÃªncia por descriÃ§Ã£o: `sorriu o feiticeiro`, `refutou a guerreira`,
`retrucou o anÃ£o`. SÃ£o cinco turnos, e exigem ligar a descriÃ§Ã£o ao nome que o
prÃ³prio texto jÃ¡ apresentou (`o feiticeiro Radcliffe` ensina quem Ã© `o
feiticeiro`). Ainda nÃ£o feito.

### Antes de qualquer campanha com GPU

```bat
.venv\Scripts\python scripts\gold_ceiling.py
```

Trinta segundos, sem GPU. Diz se a meta cabe no gabarito. Cinco campanhas foram
comparadas contra um teto de 81,57% sem que ninguÃ©m tivesse conferido â€” a
histÃ³ria estÃ¡ em [docs/TETO-DO-GABARITO.md](docs/TETO-DO-GABARITO.md).

### Documentos, na ordem em que servem

- [RODAR.md](RODAR.md) â€” o que rodar agora, o que mandar de volta, o registro do que mudou.
- [docs/RESULTADO-PART01.md](docs/RESULTADO-PART01.md) â€” a Ãºltima mediÃ§Ã£o e o que ela desmentiu.
- [docs/TETO-DO-GABARITO.md](docs/TETO-DO-GABARITO.md) â€” por que o placar mentia, e as duas decisÃµes de produto.
- [docs/AUDITORIA-DO-GABARITO.md](docs/AUDITORIA-DO-GABARITO.md) â€” o gabarito bate com o livro, e o que a auditoria nÃ£o prova.
- `benchmarks/part02_gold.yaml` â€” gabarito congelado da Parte 02, agora marcado como desenvolvimento apÃ³s o primeiro teste externo.
- [AGENTS.md](AGENTS.md) â€” as preferÃªncias e as regras que nÃ£o se negociam.
- [docs/SPEAKER_ATTRIBUTION_HANDOFF.md](docs/SPEAKER_ATTRIBUTION_HANDOFF.md) â€” histÃ³rico dos cinco protocolos. **Os nÃºmeros dele sÃ£o anteriores Ã  correÃ§Ã£o do avaliador.**
- [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) â€” escolhas de transcriÃ§Ã£o, conversÃ£o e GPU.
- [GUIA_DE_USO.md](GUIA_DE_USO.md) â€” onde colocar cada arquivo.

Os experimentos `scene`, `lightweight` e `source_subjects` regrediram e ficam sÃ³
para reproduÃ§Ã£o. O padrÃ£o Ã© `compact` com `turn_consistency`.

## Requisitos

- Windows 11, Python 3.11 para a aplicaÃ§Ã£o e Python 3.10 para Seed-VC
- NVIDIA recente e driver atualizado (CPU funciona, mas Ã© muito lento)
- FFmpeg/FFprobe no `PATH`
- Aproximadamente 15â€“25 GB livres para ambientes e modelos

## InstalaÃ§Ã£o

No Prompt de Comando:

```bat
setup.bat
setup_seedvc.bat
check_gpu.bat
```

`setup.bat` cria `.venv`, instala PyTorch CUDA 13.0, faster-whisper e as bibliotecas CUDA 12/cuDNN 9 exigidas pelo CTranslate2 lado a lado. Se FFmpeg estiver ausente e `winget` existir, tenta instalar `Gyan.FFmpeg`. Reabra o terminal apÃ³s a instalaÃ§Ã£o do FFmpeg.

`setup_seedvc.bat` clona o projeto oficial em `models/seed-vc` e usa um ambiente Python 3.10 separado. Como os pins PyTorch 2.4/CUDA 12.6 do upstream antecedem Blackwell, o script substitui somente o trio PyTorch pelo wheel oficial 2.11/CUDA 13.0. Os pesos sÃ£o baixados pelo prÃ³prio Seed-VC no primeiro segmento convertido.

Para instalar Python 3.10, se necessÃ¡rio:

```bat
winget install Python.Python.3.10
```

## PreparaÃ§Ã£o

1. Coloque um arquivo ou capÃ­tulos em `input/`. MP3, M4A, FLAC, WAV, OPUS, OGG e AAC sÃ£o aceitos.
2. Coloque referÃªncias WAV limpas, de preferÃªncia de 10â€“30 segundos, em `voices/`.
3. Edite `config/characters.json`. SÃ³ personagens em `mode: convert` (ou `auto` explicitamente habilitado) e com referÃªncia existente sÃ£o elegÃ­veis.
4. Opcionalmente, forneÃ§a o livro em TXT, EPUB, SRT ou JSON. Isso melhora substancialmente a detecÃ§Ã£o estrutural e a atribuiÃ§Ã£o.

VocÃª Ã© responsÃ¡vel por obter consentimento e direitos para as vozes e obras utilizadas. NÃ£o use o software para personificaÃ§Ã£o enganosa ou fraude.

## Uso

Ative o ambiente ou use `run.bat`:

Interface grÃ¡fica no Windows (dÃª dois cliques):

```bat
ABRIR_INTERFACE.bat
```

Ela permite escolher capÃ­tulos/livro/saÃ­da, importar automaticamente os personagens encontrados, escolher suas vozes, alterar configuraÃ§Ãµes e acompanhar capÃ­tulo, tempo e porcentagem sem digitar comandos.

Na ediÃ§Ã£o de personagens, o campo **ReferÃªncia de voz** Ã© uma lista dos arquivos disponÃ­veis em
`voices/`; use **Atualizar lista** se copiar um arquivo para a pasta com a interface aberta.

TambÃ©m inclui seleÃ§Ã£o individual de capÃ­tulos, aliases de personagens, estimativa de tempo/espaÃ§o, checkpoints retomÃ¡veis e prÃ©vias original/convertida para comparaÃ§Ã£o A/B.

### Banco de voz

A aba **BANCO DE VOZ** recebe WAV, MP3, M4A, FLAC, Opus, OGG ou AAC e faz diarizaÃ§Ã£o local:

1. selecione o Ã¡udio e o intervalo a analisar (10 segundos a 1 hora);
2. deixe a quantidade de vozes em `AutomÃ¡tico` ou informe quantas pessoas existem;
3. clique em **Reconhecer e separar vozes**;
4. ouÃ§a a amostra de cada grupo e informe o nome do personagem;
5. expanda a voz, ouÃ§a os trechos individuais e exclua qualquer trecho contaminado;
6. clique em **Cortar e salvar voz**.

O app escolhe os trechos mais limpos, monta atÃ© 25 segundos de referÃªncia em `voices/`, atualiza
`config/characters.json` e habilita o personagem para conversÃ£o. A diarizaÃ§Ã£o usa Resemblyzer no
ambiente local do Seed-VC; execute `setup_seedvc.bat` antes do primeiro uso. Falas simultÃ¢neas e mÃºsica
de fundo nÃ£o podem ser isoladas perfeitamente e devem ser evitadas.

A opÃ§Ã£o **Limpeza leve de ruÃ­do** vem ativada somente na cÃ³pia interna usada para reconhecimento. Ela
reduz ruÃ­do constante e ajuda a separar falantes, mas previews e referÃªncias sÃ£o recortados de uma
cÃ³pia mestre nÃ£o filtrada em 44,1/48 kHz. Assim, a anÃ¡lise pode ser simplificada sem deixar a voz salva
abafada. MÃºsica, eco ou vozes sobrepostas ainda precisam ser evitados ou excluÃ­dos na revisÃ£o.

O detector faz cortes de no mÃ¡ximo quatro segundos, mede a consistÃªncia interna e exclui por padrÃ£o
trechos curtos ou suspeitos. Na Ã¡rvore de resultados, dÃª dois cliques para ouvir um trecho e use
**Incluir/excluir trecho** para controlar exatamente o que entrarÃ¡ na referÃªncia final.

```bat
.venv\Scripts\activate
python main.py analyze input --book-text livro.txt
python main.py process input --book-text livro.txt --dry-run
python main.py process input --book-text livro.txt
```

Idioma explÃ­cito e configuraÃ§Ã£o alternativa:

```bat
python main.py analyze input\Chapter 01.mp3 --language pt
python main.py process input --config config\config.yaml --characters config\characters.json
python main.py analyze input\amostra.wav --model tiny --device cuda
```

`analyze` e `--dry-run` nÃ£o criam Ã¡udio alterado; ambos geram `output/analysis.json`, `report.json` e `report.html`. `process` cria arquivos como `Chapter 01 Enhanced.mp3`.

## Regra de decisÃ£o

Um trecho sÃ³ Ã© convertido quando todas estas condiÃ§Ãµes sÃ£o verdadeiras:

1. o falante foi identificado e existe em `characters.json`;
2. o `mode` resolve para conversÃ£o e a referÃªncia existe;
3. confianÃ§a do falante atinge `speaker_confidence_threshold`;
4. com livro, alinhamento atinge `alignment_confidence_threshold`;
5. a duraÃ§Ã£o mÃ­nima Ã© atingida;
6. nÃ£o Ã© interjeiÃ§Ã£o/som curto inseguro.

Se qualquer condiÃ§Ã£o falhar ou o backend lanÃ§ar erro, o original permanece. NÃ£o hÃ¡ decisÃ£o baseada apenas em uma voz â€œsoar femininaâ€.

## ConfiguraÃ§Ã£o

As opÃ§Ãµes documentadas ficam em `config/config.yaml`:

- `device`: `auto`, `cuda` ou `cpu`;
- `transcription.model`: modelo faster-whisper; `large-v3` prioriza precisÃ£o;
- `speaker_confidence_threshold` e `alignment_confidence_threshold`: limites de seguranÃ§a;
- `padding_ms` e `crossfade`: integraÃ§Ã£o de bordas;
- `minimum_segment_duration`: duraÃ§Ã£o mÃ­nima global; pode ser sobrescrita por personagem;
- `voice_conversion.backend`: `auto`, `seedvc`, `openvoice` ou `rvc`;
- `output.format`/`bitrate`: MP3, M4A, FLAC, WAV, OPUS ou OGG;
- `llm`: revisor contextual via Ollama local ou endpoint OpenAI-compatible;
- `llm.automatic_confidence`: limite conservador para uma decisÃ£o sem consenso;
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

DÃª dois cliques em `setup_qwen.bat` para instalar o Ollama e baixar o modelo, ou execute
`ollama pull qwen3:8b` manualmente uma vez. O modo normal
desativa raciocÃ­nio prolongado porque ele pode multiplicar o tempo sem garantir mais acertos. A IA
recebe blocos conversacionais locais do livro, nunca o timbre do narrador. A segunda leitura aumenta
o tempo da primeira anÃ¡lise, mas divergÃªncias ficam para revisÃ£o humana em vez de entrarem no Ã¡udio.
Para API compatÃ­vel, use
`provider: openai-compatible`, uma `base_url` terminada antes de `/chat/completions`, e defina a
variÃ¡vel indicada por `api_key_env`. Respostas sÃ£o cacheadas pelo hash de todo o contexto.

## Personagens e referÃªncias

Exemplo mÃ­nimo:

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

Compartilhar uma referÃªncia gera aviso quando `allow_shared_voice_references: true`; se falso, a configuraÃ§Ã£o Ã© rejeitada. `pitch_shift` Ã© apenas complementar, nÃ£o o mecanismo principal de identidade.

Os modos sÃ£o `original` (preservar), `convert` (converter), `auto` (conservador; preserva por padrÃ£o) e `ignore` (preservar sem trabalho especÃ­fico). GÃªnero, idade, espÃ©cie e pitch sÃ£o metadados e nunca autorizam conversÃ£o. `__narrator__` Ã© `original` por padrÃ£o.

Gerenciamento pela CLI:

```bat
python main.py character add "Vesemir" --mode convert --voice voices/vesemir_ref.wav
python main.py character set "Geralt" --mode original
python main.py character list
```

## Cache e retomada

Cada fase usa hashes do arquivo, configuraÃ§Ã£o e dependÃªncias da etapa. Reexecutar reaproveita transcriÃ§Ã£o, alinhamento, detecÃ§Ã£o, LLM e conversÃµes concluÃ­das em `cache/`. MudanÃ§as relevantes geram novas chaves automaticamente. Para invalidar tudo, mova a pasta `cache` para outro local; nÃ£o edite arquivos de cache Ã  mÃ£o.

## GPU e soluÃ§Ã£o de problemas

Execute `check_gpu.bat`. TrÃªs estados sÃ£o independentes: o driver pode detectar a GPU, PyTorch pode ou nÃ£o ter CUDA, e CTranslate2 pode ou nÃ£o carregar cuBLAS/cuDNN.

- `PyTorch CUDA: DISABLED`: recrie `.venv` pelo setup e confirme driver NVIDIA atual.
- erro `cublas64_12.dll`/`cudnn_ops64_9.dll`: confirme o wheel CUDA do PyTorch; o programa expÃµe automaticamente sua pasta `torch/lib` ao CTranslate2.
- memÃ³ria insuficiente: troque `large-v3` por `medium` ou `distil-large-v3` e reduza processos concorrentes.
- `FFmpeg missing`: execute `winget install Gyan.FFmpeg`, reabra o terminal e repita o diagnÃ³stico.
- RTX 50: use wheels CUDA 13.0 atuais; wheels antigos sem `sm_120` podem falhar.

## Backends de voice conversion

`auto` escolhe o primeiro backend instalado, priorizando Seed-VC. Ele Ã© zero-shot e recebe diretamente Ã¡udio-fonte e referÃªncia. OpenVoice fica exposto como adaptador, mas nÃ£o Ã© executado automaticamente neste release devido ao fluxo/checkpoints especÃ­ficos. RVC funciona apenas se `voice_model` apontar para um `.pth` treinado; uma referÃªncia curta nÃ£o basta.

## Testes

```bat
.venv\Scripts\python -m pytest
```

Os testes cobrem configuraÃ§Ã£o, referÃªncias compartilhadas, cache, alinhamento, segmentaÃ§Ã£o em nÃ­vel de palavra, elegibilidade, ordenaÃ§Ã£o de capÃ­tulos e preservaÃ§Ã£o byte a byte quando nÃ£o hÃ¡ substituiÃ§Ãµes. Um teste FFmpeg Ã© executado quando as ferramentas estÃ£o instaladas.

### Benchmark auditado da Parte 01

O gabarito manual fica em `benchmarks/part01_gold.yaml`. Ele separa treino, desenvolvimento e teste
por cenas, registra falas ausentes, pensamentos confundidos com fala, identidades que o livro deixa
ambÃ­guas e turnos cortados antes da continuaÃ§Ã£o. Para comparar uma nova `output/analysis.json`:

```bat
.venv\Scripts\python scripts\evaluate_part01_gold.py
```

O placar lidera com o par **precisÃ£o Ã— cobertura** sobre as falas dublÃ¡veis, e separa
o desfecho em trÃªs â€” correto, voz trocada errada, sem atribuiÃ§Ã£o â€” porque abster e
errar nÃ£o sÃ£o a mesma coisa para quem escuta. As duas mÃ©tricas antigas, que contam
omissÃ£o como erro, continuam no relatÃ³rio para comparar com as rodadas anteriores;
os relatÃ³rios `benchmarks/PART01_*.md` sÃ£o anteriores Ã  correÃ§Ã£o do avaliador.

Para ver turno a turno o que errou, sem GPU:

```bat
.venv\Scripts\python scripts\dump_errors.py --analysis output\<pasta>\analysis.json --output output\<pasta>\erros.csv
```

E para testar uma regra nova sobre uma rodada que jÃ¡ existe, com ganhos e perdas
separados â€” delta lÃ­quido esconde troca de dez por oito:

```bat
.venv\Scripts\python scripts\simulate_rules.py --analysis output\<pasta>\analysis.json
```

## SaÃ­das e auditoria

`report.json` inclui duraÃ§Ã£o, segmentos, falantes, conversÃµes, pulos, erros, GPU, backends, hits de cache e taxa de alinhamento. `report.html` contÃ©m os mesmos dados legÃ­veis. Cada fala registra timestamps, scores, motivo, elegibilidade e aÃ§Ã£o.

### Motor de identificaÃ§Ã£o de falantes

Com um EPUB correspondente ao Ã¡udio, o motor usa atribuiÃ§Ãµes explÃ­citas, uma lista ampla de verbos de fala em portuguÃªs, autoapresentaÃ§Ãµes, nomes usados como vocativo, aÃ§Ãµes narrativas e turnos de conversas entre duas pessoas. Divisores e capÃ­tulos do livro encerram a cena para impedir que um personagem seja carregado para a conversa seguinte. CitaÃ§Ãµes e pensamentos dentro de uma fala nÃ£o viram falas separadas. InferÃªncias sÃ³ sÃ£o convertidas quando ultrapassam `speaker_confidence_threshold`; descriÃ§Ãµes sem nome, como â€œum camponÃªsâ€, permanecem desconhecidas.

O motor mantÃ©m memÃ³ria de papÃ©is por cena (`a guerreira`, `o feiticeiro`), respostas a personagens
chamados pelo nome, aÃ§Ãµes do parÃ¡grafo anterior e aliases como `Lobo â†’ Geralt`. Ambiguidades restantes
sÃ£o revisadas em blocos pelo Qwen; resultados abaixo do limite aparecem em **REVISÃƒO DE FALAS**.
O reconhecimento acÃºstico nÃ£o decide mais personagens. O Ã¡udio serve para transcriÃ§Ã£o e alinhamento,
e os cortes finais continuam vindo do arquivo original. As decisÃµes manuais locais ficam em
`config/speaker_overrides.json`.

## LicenÃ§as de terceiros

Este projeto Ã© MIT. Seed-VC Ã© GPL-3.0 e permanece uma instalaÃ§Ã£o externa; faster-whisper, PyTorch, FFmpeg e modelos possuem suas prÃ³prias licenÃ§as. Confira-as antes de distribuir resultados ou empacotar dependÃªncias.

