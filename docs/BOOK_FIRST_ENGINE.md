# Motor textual de personagens — implementação para avaliação

Esta etapa implementa o núcleo de entidades e turnos do livro e o conecta ao app.
A qualidade real com Qwen ainda deve ser medida no próximo turno de testes.

## Comportamento

O app constrói o inventário de todo o livro e suas âncoras textuais antes da
transcrição. Identidade tem ID próprio; o nome apresentado na interface é outro
campo. Nomes completos diferentes não são fundidos por compartilhar o primeiro
nome. Aliases configurados pelo usuário constituem vínculos explícitos.

Depois que o alinhamento determina quais páginas correspondem ao MP3 selecionado,
a IA analisa as cenas textuais pertinentes, incluindo falas sem correspondência no
áudio. Esse carregamento por cena evita revisar o restante do romance ao analisar
um único capítulo. A IA recebe os parágrafos originais e todos os fragmentos de
cada turno. O áudio não define a lista de falas a identificar.

Janelas são limitadas a 24 turnos e 14.000 caracteres de texto por padrão. Quando
uma cena excede isso, usa janelas com contexto ao redor; não atravessa divisões de
cena. Um turno grande demais fica pendente com erro explícito de limite, em vez de
ser truncado silenciosamente. Não há ainda uma memória completa de entradas e saídas
persistida entre janelas: a presença é inferida do contexto fornecido pelo Qwen.

A saída da IA usa IDs e cita evidências com parágrafo e offsets. O app verifica a
existência literal dessas citações e sua localização na narração. Se o modelo
errar o offset, aceita uma citação com uma única ocorrência naquele parágrafo.
Uma atribuição precisa também citar o nome/alias da entidade nas evidências.
Isso verifica procedência e algumas contradições; não prova que a interpretação
semântica está correta nem calibra a confiança.

A IA pode propor personagens novos a partir de menções literais na narração,
incluindo ocupações desconhecidas pelo parser anterior. Entidades anônimas são
locais à cena e recebem identidade pela menção de origem. Dois indivíduos podem
ter a mesma descrição. Vínculos automáticos entre descrições diferentes da mesma
pessoa ainda precisam de evolução; não há fusão sem evidência só pela profissão.

As âncoras iniciais usam atribuições de fala e autoapresentações explícitas.
Uma discordância sustentada entre âncora e IA vira conflito para revisão.
Pensamentos e citações classificados como tal não recebem voz de personagem.
Propostas com evidência inválida permanecem pendentes, preservando uma âncora
explícita já existente quando houver. Confirmações manuais continuam prevalecendo.

Ao final, o app associa cada decisão ao candidato textual que originou o recorte.
Essa associação não altera os tempos. Turnos sem áudio permanecem no relatório
textual; falas de transcrição sem vínculo textual ficam pendentes nesse modo.

## Configuração e relatórios

Na aba Configurações, marque **Analisar falas pelo texto (experimental)**. O campo
**Confiança da análise textual** controla esse modo. A segunda leitura e os
limiares do motor anterior só se aplicam quando o modo textual está desmarcado.

No YAML, as opções ficam em `book_first`. O padrão da worktree experimental está
ativado; a main e o programa anteriormente aberto não foram atualizados.

Cada capítulo recebe `book_speaker_analysis` no JSON/HTML: entidades, turnos,
evidências, propostas, conflitos e decisões. `book_dialogue_coverage` continua
mostrando a cobertura do alinhamento. Ainda não há uma tela dedicada de edição
das entidades e das evidências: usa-se o relatório para essa inspeção.

O gabarito continua congelado. Nomes anônimos exibidos pelo novo motor incluem
cena e posição para evitar colisões. A comparação literal antiga pode tratar uma
descrição equivalente como erro; não remapear nomes automaticamente para elevar
a pontuação. Uma avaliação por entidade exige correspondências auditadas e
versionadas separadamente, mantendo também a métrica literal para comparação.

## Próximo turno de testes

Usar `scripts/benchmark_book_speakers.py`, não o comparador legado, para exercitar
o novo fluxo. O comparador legado chama diretamente o detector e a revisão antiga
e, portanto, não testa o modo `book_first` do pipeline.

O script recebe `--book`, `--transcription`, `--alignment`, `--config`, `--gold` e
`--output`. Exige pasta nova para garantir cache de respostas vazio. Usa apenas
Ollama local, sem aliases configurados nem correções manuais, aquece o modelo
separadamente e registra os tempos e erros. `--without-llm` permite verificar
apenas as atribuições explícitas. Não executa Whisper nem conversão de voz.

Para repetir a Parte 01, usar os mesmos arquivos dos testes anteriores:

- Transcrição: `cache/transcription/37a006528eea8622f6589b8a11310aa51e12ea0865343ffa42b0eba7f2093338.json`, na main.
- Alinhamento: `cache/alignment/ae2e108189c7ea7e77b5600b4a2cf1eed1a8532bd0fd14f37574396d2026881a.json`, na main.
- Livro: EPUB da Parte 01 já fornecido, em `books/` na main.
- Gabarito: `benchmarks/part01_gold.yaml` desta worktree.
- Referência: `output/qwen-comparison-fresh-20260907/` nesta worktree.

A referência v25 acertou 160/255 (62,75%) e a v27 antiga 149/255 (58,43%).
Esses números não medem este novo motor. O conjunto é regressão de desenvolvimento;
foi inspecionado durante ajustes e não comprova generalização para outros livros.

Primeiro verificar erros de protocolo, citações rejeitadas, conflitos e tipos de
entidade; depois comparar acertos, omissões, precisão entre atribuídas, resultado
por personagem e tempo. Não modificar prompts, gabarito ou limites durante a rodada.
