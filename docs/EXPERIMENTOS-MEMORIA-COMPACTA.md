# Experimentos de memória compacta

Relatório de transferência para revisão por outra IA. Estado em 09/09/2026.

## Objetivo e regra de avaliação

O motor precisa atribuir falas a personagens em livros gerais. Não há regras com
nomes deste livro no código. A meta do produto é precisão ≥95% e cobertura ≥95%
sobre falas dubláveis. Abstenção mantém o narrador e é segura, mas conta contra a
cobertura. Figurantes anônimos de uma única cena não recebem voz.

P1, P2 e P3 já foram consultadas e são regressões de desenvolvimento. P3 foi o
último holdout genuíno antes de ser consumido. O ASR e o alinhamento são reutilizados
nas campanhas abaixo; os caches de respostas do Qwen são sempre novos.

## Melhor referência preservada na main

Motor: `compact-speakers-v1` + `turn-consistency-v2`, Qwen 3 8B local.

| Parte | Precisão | Cobertura | Observação |
|---|---:|---:|---|
| P1 | 94,74% | 98,12% | 198 certas, 11 erradas, 2 abstenções/213 dubláveis |
| P2 | 95,53% | 97,81% | 171 certas, 8 erradas, 3 abstenções/183 dubláveis |
| P3 | 90,68% | 88,86% | 282 certas, 29 erradas, 26 abstenções/350 dubláveis |

P3 levou 385,609 s, sem erro de chamada. A cena 27 (Coen/Ciri) acertou 21/41;
a cena 26 acertou 27/29.

## Experimento A — contexto ampliado e schema enumerado

Branch `fix/compact-scene-context`, commits `e4f56d9` e `ac258ac`.

- IDs globais estáveis, texto expandido até o orçamento e schema com enums de IDs.
- P3: 96,23% de precisão e 68,29% de cobertura.
- 230 certas, 9 erradas e 98 abstenções/350.
- 909,219 s; três timeouts e uma resposta truncada em 4096 tokens.
- Conclusão: precisão aparente veio de muitas abstenções. Prompt/schema grandes
  não são viáveis no Qwen 8B. Nada foi promovido à `main`.

## Experimento B — memória curta com IDs globais

Branch `feat/compact-memory`, commits `62299cf` e `49f48a8`.

- Janela e schema voltaram ao tamanho original; 8 âncoras literais e 6 hipóteses
  recentes eram enviadas. IDs continuavam globais e todo personagem já registrado
  permanecia no catálogo da cena.
- P3: 91,30% de precisão e 85,43% de cobertura.
- 273 certas, 26 erradas e 38 abstenções/350.
- 425,438 s, 19 misses, zero erro/truncamento.
- Cena 27 melhorou de 21/41 para 36/41, confirmando ganho de continuidade.
- Cena 26 caiu de 27/29 para 5/29. Os IDs locais apareciam como E10/E12/E13 e o
  catálogo chegou a 17 entidades. A representação mudou respostas do modelo.
- Conclusão: memória é útil, mas identidade global e catálogo acumulativo não.

## Candidato C — memória estritamente local à cena

Branch `feat/scene-local-memory`. Base direta: `main` em `1afb873`.

- IDs de entidade e turno reiniciam em E0/T0 por cena e permanecem estáveis apenas
  entre as janelas dessa cena.
- Catálogo = entidades do texto atual + identidades com âncora literal anterior +
  identidades presentes nas 6 hipóteses recentes.
- Hipóteses antigas expiram do histórico e do catálogo; âncoras literais persistem.
- Âncoras e hipóteses são campos separados. Uma hipótese é rotulada explicitamente
  e não recebe status de evidência.
- A janela não é expandida, o schema não enumera IDs e não há chamada adicional.
- O prompt proíbe copiar entidades E conhecidas para a lista de novas entidades;
  elas só podem aparecer como `speaker`. Isso ataca as centenas de propostas E
  redundantes observadas no experimento B sem aumentar o schema.
- Se uma chamada falha, suas hipóteses não entram na memória; âncoras literais ainda
  podem servir à janela seguinte.

## Pré-registro do próximo teste

Rodar P3 primeiro com cache de resposta vazio. Exigir simultaneamente:

- precisão ≥90,68%;
- cobertura >88,86%;
- zero lote perdido;
- tempo ≤482,011 s;
- nenhuma cena com 20+ turnos perdendo mais de 5 acertos contra a referência.

Somente se P3 passar, executar P1/P2. A campanha não demonstra generalização; uma
parte futura, congelada antes de qualquer inferência, ainda será necessária.
