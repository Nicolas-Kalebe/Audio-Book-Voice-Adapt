# Identificação de falantes por cena

Prioridade atual: acertar o falante em pelo menos 90% das falas, contando omissões
e recusas como erros. O produto ainda não atingiu esse patamar em uma avaliação
validada. A conversão não é o objetivo desta etapa.

## Evidência que orientou a mudança

O compacto anterior acertou 176/255 no gabarito de desenvolvimento. Entre seus
erros há pessoas apenas mencionadas escolhidas como falantes, descrições de
personagens sem uma identidade consistente, confusão com vocativos e divergência
até diante de sujeitos narrativos explícitos. Esses problemas justificam testar
cadastro/contexto da cena e uma revisão dirigida. Não demonstram antecipadamente
que a nova versão atingirá 90%.

O teste compacto anterior teve cinco cache hits, após lançamentos sobrepostos.
Sua duração final não representa uma execução fria independente. Os resultados
anteriores devem ser preservados; a nova comparação precisa de pasta exclusiva.

## Implementação experimental

`book_first.protocol: scene` usa o formato compacto de atribuição e adiciona:

1. Um cadastro textual por cena, incluindo pessoas sem nome e grupos. Distingue
   participantes de pessoas apenas mencionadas. Nomes do restante do livro não
   entram automaticamente no conjunto de falantes.
2. Menções e descrições literais ligadas à identidade local. O programa resolve
   os offsets; o modelo não escreve coordenadas por fala. Alias proposto pela IA
   continua hipótese contextual. Vínculos não alteram os aliases do usuário.
   Um nome curto pode ser ligado ao completo quando ambos são apresentados como
   a mesma pessoa e não há reivindicação conflitante. Dois anônimos com a mesma
   descrição e introduções diferentes mantêm IDs diferentes.
3. Contexto integral quando a cena cabe em `scene_context_characters` (36.000
   caracteres por padrão), mantendo 24 alvos por chamada. Cenas maiores usam
   texto limitado ao redor do bloco e até seis hipóteses anteriores identificadas
   como hipóteses. Não há regra automática de alternância. O catálogo reinicia
   na próxima cena; IDs dos turnos permanecem estáveis no livro.
4. Sujeitos de atribuições literais reconhecidos por nomes/descrições do cadastro.
   Uma descrição ambígua entre duas pessoas não vira âncora. Uma resposta da IA
   contrária ao sujeito literal fica registrada sem apagar essa atribuição.
5. Uma segunda leitura direcionada a IDs faltantes/duplicados, incerteza,
   conflito com sujeito narrativo ou possível confusão com vocativo. A segunda
   leitura recebe o texto e os alvos, sem a resposta anterior. É limitada a uma
   tentativa por bloco e pode ser desativada para comparação.

O processamento recebe texto do livro; não usa gabarito, nomes desta obra,
características de voz ou respostas esperadas. Os cortes de áudio não foram
alterados. Ainda não modelamos explicitamente uma linha temporal de entradas e
saídas: a IA precisa inferi-la do texto. Em cenas muito longas, dependências fora
da janela continuam sendo uma limitação a medir.

## Avaliação no turno de testes

Usar `scripts/benchmark_book_speakers.py` com os mesmos argumentos de livro,
transcrição, alinhamento, configuração e gabarito usados antes. Executar uma
vez por pasta nova, sem apagar uma pasta pertencente a processo ativo.

- `--protocol compact`: referência da implementação anterior.
- `--protocol scene --no-scene-repair`: isola o cadastro/contexto e sujeitos.
- `--protocol scene`: mede o efeito adicional da revisão dirigida.

Priorizar a comparação sem revisão e, conforme seus erros, executar a variante
com revisão. Não executar processos simultâneos na mesma GPU ou saída. O script
reserva a pasta antes do aquecimento; erro de inicialização deixa a pasta para
diagnóstico. Usar outro nome na nova tentativa.

Comparar acurácia ponta a ponta, número absoluto correto/total, erros por
personagem, `per_scene`, atribuições brutas, falhas de cadastro e de atribuição.
`review.total_llm_calls` inclui cadastro, atribuição e segunda leitura; o tempo
de revisão inclui essas fases. `cold_response_cache_valid` deve ser verdadeiro
e cache hits deve ser zero. O relatório registra hashes dos cinco arquivos de
entrada. Testes com cache ou execuções sobrepostas não sustentam comparações de
tempo frio.

`book_speaker_analysis.scene_context` registra participantes, menções e papéis;
os turnos registram a primeira leitura, revisão dirigida, proposta final e
contradições. O gabarito continua congelado. Descrições anônimas e nomes curtos
equivalentes podem falhar na comparação literal: devem ser auditados por
identidade, mantendo a pontuação literal disponível. Não ajustar nomes ou
gabarito automaticamente para elevar números.

O resultado só conta como progresso se houver mais falas corretamente atribuídas.
Diminuir a quantidade de vozes convertidas não satisfaz a meta. A Parte 01 é
regressão de desenvolvimento; a aprovação para uso geral exige outros trechos
que não tenham orientado os ajustes.

## Verificação desta implementação

156 testes técnicos passaram, incluindo a integração do protocolo `scene` no
pipeline, o contexto entre blocos, identidades anônimas distintas, conflitos de
nomes abreviados, isolamento de cenas e revisão de vocativos. O script completo
de relatório também foi executado com `--without-llm` na pasta local
`output/scene-plumbing-20260907-implementation`: validou a leitura dos caches e
a geração das métricas/hashes. Seus 35 acertos são só as âncoras determinísticas
anteriores, com zero chamadas à IA; não são uma avaliação da nova atribuição.
A campanha com Qwen deve ocorrer no turno de testes.
