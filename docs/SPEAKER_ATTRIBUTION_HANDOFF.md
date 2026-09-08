# Handoff: investigação de identificação de falantes

Este documento dá contexto suficiente para outra IA revisar o motor sem depender
dos relatórios locais ignorados pelo Git. Ele descreve a Parte 01 usada como
regressão de desenvolvimento, as hipóteses medidas e o que os resultados permitem
ou não concluir.

## Objetivo e critério

O produto recebe um audiobook e, quando há texto do livro, deve identificar quem
fala cada turno antes de trocar vozes. A prioridade é a identidade correta do
falante, não a velocidade de conversão. A meta definida pelo proprietário é pelo
menos 90% de acerto em **todas** as falas; omissões, abstenções e falas perdidas
contam como erro.

O motor não deve usar timbre como fonte principal de identidade ficcional. O texto
serve para descobrir os turnos e os falantes; áudio/ASR/alinhamento servem para
localizar os trechos que serão preservados ou convertidos.

## Material de desenvolvimento

A Parte 01 de um audiobook em português foi anotada pelo projeto e contém 255
turnos falados no gabarito. A avaliação usa o mesmo EPUB, transcrição e alinhamento
congelados, sem aliases configurados, sem overrides manuais, sem refazer ASR e sem
executar conversão de voz. O modelo é `qwen3:8b` local no Ollama.

O gabarito da Parte 01 foi consultado durante desenvolvimento. Portanto é uma
regressão de desenvolvimento, não um teste independente e não prova generalização
para outros livros. Os pesos do Qwen não foram treinados; “melhorias” significam
alterações de parser, prompt, schema ou regras.

As duas falas que a detecção textual/ASR ainda não localiza são contabilizadas como
erro em todas as métricas ponta a ponta. O denominador permanece 255.

## Métricas comparáveis

As cinco linhas abaixo usaram o mesmo material e gabarito. `Atribuídas` é a
quantidade de turnos com um falante emitido. `Acerto emitido` pode parecer alto
quando o motor deixa muitos turnos vazios; a métrica decisiva é `Corretas / 255`.

| Variante | Corretas / 255 | Atribuídas | Acerto emitido | Chamadas LLM | Cache hits | Tempo de atribuição | Resultado |
|---|---:|---:|---:|---:|---:|---:|---|
| Evidence, exigindo evidência gerada | 35 (13,73%) | 36 | 97,22% | 15 | 0 | 1.048,391 s | Rejeitada: esquema grande levou a JSON truncado/timeout e cobertura baixa. |
| Contexto por cena + cadastro de elenco | 141 (55,29%) | 204 | 69,12% | 27 | 0 | 687,968 s | Rejeitada: chamada de elenco truncou e o cadastro recusou identidades válidas. |
| Compacto corrigido | **178 (69,80%)** | **237** | **75,11%** | **14** | **0** | **247,735 s** | Melhor resultado atual; permanece abaixo da meta. |
| Lightweight | 128 (50,20%) | 172 | 74,42% | 14 | 0 | 301,688 s | Rejeitada: schema/prompt limitaram respostas e fragmentaram identidades. |
| Compacto + `source_subjects` | 139 (54,51%) | 218 | 63,76% | 14 | 0 | 322,421 s | Rejeitada: acrescentar muitas descrições como candidatos levou o modelo a tratá-las como pessoas novas. |

As execuções brutas não entram no Git porque incluem texto do livro. Os nomes locais
das pastas de saída estão registrados nos documentos de experimento e foram:
`book-first-evidence-qwen-20260907`, `scene-qwen-controlled-20260907`,
`compact-context-fixed-20260908`, `lightweight-context-fixed-20260908` e
`compact-subjects-qwen-20260908`.

## O que foi aprendido

### Detecção e localização não são o gargalo principal

Na melhor rodada, 253 dos 255 turnos do gabarito foram encontrados e 252 foram
encontrados completos. A cobertura textual/ASR está perto de 99%, enquanto a
identificação de falante ponta a ponta está em 69,80%. A maior perda está em decidir
o falante correto, não em extrair as falas.

### O método compacto é a referência atual

O compacto envia uma janela limitada de texto, entidades candidatas e turnos com
IDs curtos. A resposta contém `speaker`, `kind` e `confidence`, sem exigir offsets
ou explicações geradas. A validação local verifica estrutura, menções e limites.
Ele oferece a melhor combinação observada de cobertura, acerto e tempo.

Mesmo assim, o compacto falha muito em cenas com grande elenco e papéis anônimos.
Na melhor rodada, a cena com muitos interlocutores concentrou 49 dos 77 erros.
Erros recorrentes: trocar Yennefer/Jaskier, trocar personagem nomeado por descrições
ou pessoas citadas, e não representar anonimamente o interlocutor correto.

### Mais contexto ou mais candidatos pioraram o Qwen atual

O protocolo `scene` pediu primeiro um cadastro de participantes por cena. Uma saída
atingiu o limite de 4096 tokens antes de fechar o JSON; em outras cenas o modelo
retornou frases onde o validador precisava de uma menção curta. O resultado foi a
remoção de candidatos úteis antes da atribuição.

O `lightweight` tentou limitar IDs e enriquecer as janelas com pistas de narração.
Ele reduziu a cobertura e levou o modelo a criar entidades novas para nomes já
conhecidos. A hipótese de que a mera redução de catálogo explica a queda não foi
isolada: esse protocolo mudou mais de uma variável ao mesmo tempo.

`source_subjects` extraiu descrições imediatamente após verbos de fala, como
“o anão” ou “a guerreira”, e as passou como candidatos. Isso pareceu promissor em
teste sem LLM, mas no Qwen real fragmentou uma mesma pessoa em vários nomes de
descrição. Não ligar essa opção por padrão.

### Erro de contexto já corrigido

Uma fala continuava em outro parágrafo, cujo início era a palavra “Capítulo”. O
inventário reconhecia a continuação, mas a segmentação de cenas interpretava a
palavra como cabeçalho e removia a segunda parte da janela. A correção preserva
todo fragmento do turno nas janelas e evita tratar uma continuação como capítulo.
Depois dela, o compacto passou de 176/255 para 178/255 numa comparação limpa.

## Estado atual do código

O fluxo relevante é:

```text
EPUB → book_inventory.py / book_speakers.py → turnos e entidades
                                              ↓
                                     compact_speakers.py + Qwen
                                              ↓
                    dialogue.py / alinhamento → recortes de áudio
                                              ↓
                                   voice_conversion.py
```

- `src/audiobook_voice_enhancer/book_speakers.py`: inventário, entidades básicas,
  janelas, projeção da decisão textual para os recortes de áudio.
- `src/audiobook_voice_enhancer/compact_speakers.py`: protocolo atual de melhor
  resultado (`compact-speakers-v1`).
- `src/audiobook_voice_enhancer/dialogue.py`: parser de diálogos, cenas e
  recuperação de falas curtas; contém a correção de continuação EPUB.
- `src/audiobook_voice_enhancer/scene_context.py`, `lightweight_speakers.py` e
  `speaker_subjects.py`: experimentos preservados para reprodução; não são padrão.
- `scripts/benchmark_book_speakers.py`: benchmark reproduzível com saída inédita,
  hashes de entrada e checagem de cache vazio.
- `benchmarks/part01_gold.yaml`: gabarito de desenvolvimento. Não modificar para
  elevar uma avaliação depois de ver as respostas.

`config/config.yaml` mantém `book_first.protocol: compact` e não ativa
`source_subjects`. Não há conversão de voz sendo medida nas tabelas acima.

## O que a próxima revisão deve fazer

1. Tratar o compacto de 178/255 como baseline congelada e executar qualquer mudança
   em saída nova, com o mesmo livro/transcrição/alinhamento/gabarito e cache LLM
   vazio. Uma mudança por experimento.
2. Investigar decisões entre candidatos que já existem, em vez de ampliar catálogo,
   cenário ou schema. A próxima hipótese deve explicar como melhora cenas com muitos
   interlocutores sem criar nomes descritivos paralelos.
3. Separar explicitamente identidade canônica, alias local e referência descritiva.
   Uma descrição pode apontar para uma entidade, mas não pode virar outra pessoa só
   por ser exibida ao modelo. Essa ligação precisa ser verificável e não inferida por
   profissão isolada.
4. Medir ganhos e perdas por cena, personagem, anônimos, omissões e identidade
   fragmentada. Não aceitar uma melhora de precisão que reduza cobertura: omissões
   contam como erro.
5. Criar uma avaliação independente por livros antes de alegar qualquer desempenho
   geral. O objetivo de 90% exige pelo menos 230/255 no gabarito atual, seguido por
   validação externa.

## Reproduzir o baseline atual

Na worktree de desenvolvimento, com Ollama local ativo e os arquivos privados
presentes, execute `scripts/benchmark_book_speakers.py` com os argumentos de livro,
transcrição, alinhamento, config e gabarito descritos em
[`SOURCE_SUBJECTS.md`](SOURCE_SUBJECTS.md). Use `--protocol compact` e uma pasta
de saída inédita. O script recusa reutilizar a saída para proteger a condição de
cache vazio.

## Validação técnica

Após o merge atual na `main`, a suíte local passou em 181 testes. Esses testes
verificam parser, schemas, isolamento de cache, continuação de turnos e integração.
Eles não medem acurácia literária do Qwen.
