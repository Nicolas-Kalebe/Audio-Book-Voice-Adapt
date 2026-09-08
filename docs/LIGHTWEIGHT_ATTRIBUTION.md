# Correção da atribuição de falantes

Branch: `fix/lightweight-speaker-attribution`.

## Evidência que motivou a mudança

O teste `output/scene-qwen-controlled-20260907` marcou 141/255 (55,29%),
204 atribuições emitidas, 63 atribuições erradas e 51 falas sem atribuição correta
por omissão/ausência de detecção. Detectou 253/255 turnos. A identificação levou
687,968 s (11 min 28 s), com 12,589 s separados de carregamento do modelo.
Foram 27 chamadas, zero respostas reaproveitadas. ASR e conversão não foram executados.

O compacto anterior marcou 176/255 (69,02%). Seu tempo não é referência limpa:
houve cinco respostas reaproveitadas. É necessário repetir o controle compacto.

A explicação anterior de que o truncamento da cena 9 causou o resultado de
Geralt estava incompleta: as falas dele também falham nas cenas 8 e 14. Os
artefatos mostram pelo menos três mecanismos:

- Cena 9: catálogo truncado ao atingir 4096 tokens; restaram as identidades iniciais.
- Cenas 10 e 14: o modelo produziu frases em `mentions.text`, onde o validador
  exigia nomes/descrições curtos e `name` igual a uma menção validada. Rejeitou
  registros de Jaskier, Rience, Geralt e Ciri. A cena 10 ficou inicialmente só
  com Mama Lantieri; a 14, só com Eskel.
- As decisões ainda trocam falantes mesmo com candidatos disponíveis, como
  Yennefer/Jaskier. Corrigir o catálogo não garante resolver esse erro semântico.

Esses dados demonstram falhas do protocolo e de sua integração. Não demonstram
isoladamente incapacidade do Qwen 8B nem provam qual mudança atingirá 90%.

## Mudança implementada

`compact` volta a ser o padrão da configuração de desenvolvimento. O novo
protocolo `lightweight` é uma opção explícita para comparação controlada.

Ele usa as mesmas janelas limitadas do compacto e uma chamada por janela.
Seleciona candidatos pelas ocorrências locais e âncoras existentes, sem depender
de uma chamada anterior que construa ou aprove um elenco. Pessoas novas continuam
podendo ser propostas com uma menção curta literal, inclusive anônimas.

O schema de cada janela permite somente IDs de turnos existentes, IDs de
candidatos e uma quantidade limitada de IDs novos. Limita também o tamanho das
listas de resposta. Validação posterior continua necessária, inclusive para
duplicatas; JSON estruturalmente válido não comprova identidade correta.

O contexto informa quais candidatos aparecem na narração e aponta os intervalos
de narração ao redor dos fragmentos de cada turno. Proximidade de ação é uma pista
para o modelo, não uma atribuição automática. Não há alternância automática nem
exclusão de candidato baseada apenas em nome mencionado dentro de uma fala.

Sujeitos nominais após modificadores curtos de verbos de fala podem gerar âncoras
literais, por exemplo `respondeu por ele Iara`. Esses casos usam nomes já existentes
no catálogo, texto original e regras gerais. As âncoras explícitas são preservadas
em discordâncias do modelo, registradas para auditoria. Essa política também deve
ser avaliada: uma âncora textual incorreta pode manter um erro.

Repetir o mesmo nome literal num parágrafo não impede registrar sua existência.
Descrições anônimas repetidas continuam exigindo desambiguação. O relatório agora
registra motivos de rejeição de propostas de entidade em `review.entity_rejections`.

Nenhum nome deste livro foi adicionado às regras. Não houve ajuste de pesos,
alteração de gabarito ou reconciliação oportunista dos nomes para elevar a nota.

## Próximo turno de testes

Executar sequencialmente na worktree, com Ollama local disponível. Cada saída
deve ser inédita. O comando abaixo usa a transcrição e o alinhamento congelados;
cache vazio refere-se às respostas do LLM, não a refazer ASR.

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$benchmarkArgs = @(
  'scripts/benchmark_book_speakers.py',
  '--book', '../../books/O Sangue dos Elfos.epub',
  '--transcription', '../../cache/transcription/37a006528eea8622f6589b8a11310aa51e12ea0865343ffa42b0eba7f2093338.json',
  '--alignment', '../../cache/alignment/ae2e108189c7ea7e77b5600b4a2cf1eed1a8532bd0fd14f37574396d2026881a.json',
  '--config', 'config/config.yaml', '--gold', 'benchmarks/part01_gold.yaml'
)
& '../../.venv/Scripts/python.exe' @benchmarkArgs --protocol compact --output output/compact-context-fixed-20260908
# Aguardar a conclusão antes do próximo comando.
& '../../.venv/Scripts/python.exe' @benchmarkArgs --protocol lightweight --output output/lightweight-context-fixed-20260908
```

Conferir os hashes de livro, transcrição, alinhamento e gabarito; mesma configuração
exceto protocolo; zero cache hits em ambas as execuções. Comparar total correto/255,
erros, omissões, personagens, cenas, rejeições de entidades e tempo. Auditar casos
ganhos/perdidos antes de recomendar o novo protocolo. A meta requer pelo menos
230/255 falas corretas neste gabarito, e depois validação independente em outros
livros. Este gabarito é regressão de desenvolvimento, não teste independente.

Os testes técnicos usam respostas simuladas para verificar integração e invariantes.
Não são uma medição de acurácia do Qwen. O turno de implementação não executou
uma nova campanha com o modelo.

Verificação: 163 testes passaram. O ensaio da Parte 01 sem LLM também concluiu:
38 âncoras corretas entre 39 atribuições, contra 35 corretas entre 36 na referência
sem LLM anterior. Isso verifica a integração e três âncoras adicionais; não mede
o reconhecimento contextual do novo protocolo com Qwen.

## Correção após o primeiro teste real

O controle `compact-control-20260908` concluiu com 176/255, zero cache hits e
252,969 segundos. O `lightweight-control-20260908` falhou antes da chamada do
bloco 11 com `KeyError: 295`. Não tem pontuação final válida.

A continuação de uma fala começava pela palavra “Capítulo”. O inventário agrupou
os dois parágrafos como um turno, mas a segmentação de cenas tratou o segundo como
um cabeçalho. A janela então omitiu o contexto da continuação. A falha existia
também no contexto do compacto, embora ele não acessasse o mapa que causou a exceção.

A segmentação agora respeita a continuação reconhecida pelo inventário. A montagem
das janelas inclui todos os parágrafos do turno mesmo diante de uma fronteira de
cena inconsistente. Se o turno completo exceder o orçamento, gera `context_limit`
com o turno intacto. A expansão do protocolo por cena preserva esse intervalo.
A versão do motor foi incrementada para invalidar os checkpoints anteriores.

170 testes passaram, incluindo reprodução do erro, cabeçalhos reais por extenso,
turnos entre cenas e orçamento insuficiente. O contexto do livro foi inspecionado
sem Qwen, e a montagem de entradas lightweight foi exercitada com respostas
simuladas. Como as janelas mudaram para ambos os métodos, o próximo turno deve
repetir **compact e lightweight** nas pastas inéditas indicadas acima. Não comparar
diretamente o novo lightweight com o controle de janelas antigas para isolar seu
efeito. Relatórios anteriores permanecem disponíveis como histórico.
