# Relatório do teste local — Qwen 3 8B

Data: 4 de setembro de 2026
Livro: *O Sangue dos Elfos* (EPUB)
Áudio: `Parte 01.mp3`
Modelo: `qwen3:8b` via Ollama 0.33.3

## Ambiente

- GPU: NVIDIA GeForce RTX 5060 Ti, 16 GB de VRAM.
- RAM: 15,8 GB.
- Modelo baixado: 5,2 GB.
- Pico observado com contexto de 32k: cerca de 10–11 GB de VRAM e 94% de uso de GPU.
- Todo o processamento do Qwen ocorreu localmente.

## Resultado principal

Na auditoria humana, a Parte 01 contém 15 falas de Geralt. O relatório antigo atribuía 7 e deixava
8 sem identificação. O motor novo encontrou as 15:

- 13/15 são resolvidas pelas regras contextuais, sem Qwen;
- 1/15 adicional (`Não precisa ter medo de nada`) foi aceita pelo Qwen com 0,98;
- 1/15 (`Espere aqui, com Eskel`) foi encontrada corretamente pelo Qwen com 0,95 e permaneceu na
  fila de revisão por estar abaixo do limite automático de 0,98;
- nenhum falso positivo de Geralt apareceu entre as falas atribuídas automaticamente.

Assim, para Geralt, a cobertura encontrada foi 15/15 (100%) e a automação conservadora foi 14/15
(93,3%). A fala restante requer um clique de confirmação.

## Tempos medidos

| Ensaio | Tempo | Observação |
|---|---:|---|
| Cena 14, lote único, modo rápido | 103,3 s | Recuperou 7 das 8 falas ausentes, mas misturou personagens futuros. |
| Cena 14, raciocínio prolongado | 67,9 s | Modelo já carregado; ainda errou a pergunta dirigida a Eskel. |
| Cena 14, 10 blocos com raciocínio | 203,0 s | Mais preciso em parte, mas ainda errou uma fala e ficou lento. |
| Parte 01, modo rápido, primeira passagem otimizada | 213,9 s | 24 blocos locais; transcrição e alinhamento vieram do cache. |
| Reanálise parcial com cache | 63,1 s | Grande parte das respostas foi reutilizada. |
| Validação final após mudar as regras | 103,5 s | 12 hits e 15 misses de cache; 75 falas chegaram ao Qwen. |

Uma tentativa com raciocínio prolongado em um bloco grande atingiu o timeout de 300 segundos. Por
isso o padrão final usa modo rápido, blocos locais, limite de 90 segundos e cache.

Esses tempos não incluem uma transcrição Whisper do zero. Em um capítulo novo, deve-se somar o
tempo normal do Whisper; em reanálises, transcrição, alinhamento e respostas idênticas são reutilizados.

## Parte 01 completa

Na validação final:

- 2.726 segmentos de transcrição;
- 267 trechos de fala detectados;
- 75 ambiguidades faladas enviadas ao Qwen (pensamentos/citações foram excluídos);
- 15 atribuições da IA ultrapassaram 0,98;
- 51 sugestões ficaram para revisão;
- 9 permaneceram sem solução;
- desconhecidos no relatório caíram de 126 para 81, mas ainda não existe gabarito humano completo
  para afirmar a precisão de todos os personagens.

## Decisão técnica

O Qwen 3 8B é útil como revisor textual, mas não deve ser tratado como autoridade isolada: ele
superestimou a própria confiança e chegou a atribuir uma saudação ao personagem chamado dentro dela.
O fluxo final usa:

1. regras e contexto do EPUB;
2. Qwen somente nas ambiguidades, em blocos locais;
3. trava contra escolher o destinatário como falante;
4. aceitação automática apenas a partir de 0,98;
5. revisão manual abaixo desse limite;
6. áudio apenas para transcrição, alinhamento e corte do original — nunca para decidir personagem.
