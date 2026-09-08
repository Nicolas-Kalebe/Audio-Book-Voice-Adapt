# Identificação compacta e orçamento de execução

Implementação experimental, ainda sem nova campanha com Qwen ou medição real de
velocidade do Seed-VC. Testes técnicos não demonstram 95% de identificação nem
conversão de um livro em 90 minutos. O aplicativo principal não foi atualizado.

## O que mudou

- `book_first.protocol: compact`: parágrafos originais e IDs curtos de turnos e
  entidades. Saída por turno: ID, personagem, tipo e confiança. Sem justificativas
  extensas nem offsets gerados pelo modelo. O programa continua definindo os cortes.
- Personagem ausente pode ser proposto com nome/descrição literalmente presente
  em um parágrafo. O programa encontra sua posição; isso não comprova quem fala.
- Mesmos limites de contexto e número de turnos do experimento anterior, para não
  misturar a mudança de contrato com outra estratégia de segmentação.
- Respostas brutas, propostas reconhecíveis, rejeições estruturais, baixa confiança
  e falhas de lote ficam separadas. Discordância confiante com uma âncora explícita
  continua sendo conflito; escolhas manuais prevalecem. Não há segunda leitura
  automática no modo compacto.
- O protocolo anterior permanece disponível como `book_first.protocol: evidence`.
  Desmarcar a análise textual na GUI continua selecionando o motor legado.

## Conversão

`voice_conversion.persistent_worker: true` inicia um processo oculto com o Python
privado do Seed-VC. A função oficial de inferência é reutilizada; seu carregador de
modelos é memorizado. Falas do mesmo capítulo compartilham modelos carregados.
O processo fecha ao terminar o capítulo, antes do próximo ASR/LLM, e em erros ou
interrupções normais. Há timeout por fala (`worker_timeout_seconds`, padrão 600).
Não há fallback silencioso de modelo nem redução dos 25 passos de difusão.

Não modificamos o checkout do Seed-VC. A integração pressupõe `main(args)` e
`load_models(args)` compatíveis com o checkout instalado. Testes de subprocesso
usam um backend mínimo, não provam compatibilidade/qualidade real na GPU.
Use `persistent_worker: false` para comparar com o CLI anterior.

O processamento da referência **ainda é repetido** em cada chamada oficial.
Cache de embeddings/referências fica para depois da comparação de áudio e tempo:
não alteramos simultaneamente a função de geração. A prévia encerra seu próprio
worker ao terminar; sessões separadas da GUI não compartilham GPU residente.

## Próximo turno de testes

1. Executar `scripts/benchmark_book_speakers.py` com `--protocol compact` e
   `--protocol evidence`, mesmos livro/gabarito/ASR/alinhamento e saídas novas.
   Comparar com o resultado congelado do motor legado, sem alterar o gabarito.
   O JSON contém `benchmark` (aceito) e `raw_proposal_benchmark` (antes da política
   de aceitação, mas depois de identificar IDs legíveis). Respostas malformadas
   não são atribuíveis; o contador de falhas deve aparecer junto das métricas.
2. Inspecionar `cache/llm_diagnostics`: resposta bruta, motivo de término,
   contagem de tokens e tempos do Ollama, inclusive quando o JSON falha.
   Esses arquivos podem conter texto do livro e não devem entrar no Git.
3. Executar `scripts/benchmark_conversion.py --mode persistent` e depois `--mode cli`
   com os mesmos argumentos `--root`, `--analysis`, `--config`, `--characters`,
   `--samples 8` e pastas `--output` diferentes e novas. Usa falas elegíveis do
   relatório, de personagens configurados em `convert`, variando voz e duração.
   Requer FFmpeg/FFprobe no PATH do ambiente do app. Não modifica capítulos finais.
   Ouvir as amostras originais e convertidas; registrar falhas e primeira chamada
   separadamente das chamadas seguintes. Não executar enquanto o app principal
   estiver usando a GPU. Checkpoints ausentes podem exigir download no primeiro uso.
4. Só então medir processamento completo de um capítulo representativo com saída
   e cache isolados. O relatório registra `stage_timings` por capítulo: transcrição,
   alinhamento, detecção, atribuição, planejamento, conversão e exportação.
   Cada etapa informa cache hits/misses. Capítulos retomados têm tempos históricos;
   `resumed_chapters` identifica retomadas. Não tratar um teste com cache como
   tempo de primeira execução. A criação do inventário e demais custos globais
   estão no tempo total, não nas etapas por capítulo.
5. Projetar tempo do livro usando duração total, densidade de diálogos e personagens
   selecionados. Um teste só de identificação ou só de conversão não é ETA global.
   Validar generalização em outros trechos/livros antes de afirmar 95%.

A meta desejada é aproximadamente 90 minutos, sem esconder omissões ou baixar a
qualidade para cumpri-la. A Parte 01 permanece regressão de desenvolvimento, não
holdout independente; rótulos equivalentes exigem auditoria separada, não ajuste
automático para aumentar a pontuação.
