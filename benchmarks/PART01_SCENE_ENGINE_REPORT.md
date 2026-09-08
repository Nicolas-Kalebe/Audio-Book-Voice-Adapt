# Motor contextual por cena — Parte 01

## Retificação metodológica — 6 de setembro de 2026

Este é um resultado histórico de desenvolvimento, não um teste independente.
As cenas 13–14 foram inspecionadas durante os ajustes: o nome `test_locked` não
corresponde mais a um conjunto intocado. Os 98,11% abaixo não estimam acurácia em
novos livros. O gabarito foi produzido pelo assistente e ainda precisa de auditoria
independente. “Treino” significa ajuste de regras/prompts, não treinamento dos pesos.

A crítica antiga via a primeira proposta do mesmo modelo; concordância não era
validação independente. A versão em desenvolvimento passa a ocultar essa proposta
e não reduz o limiar automático por consenso. Continua sendo o mesmo modelo:
duas leituras não transformam confiança declarada em probabilidade calibrada.

Os números e tempos abaixo pertencem à v25, não à versão nova. A rodada de 178,17 s
também reutilizou respostas intermediárias do cache; não é medição a frio.

## Resultado

Teste executado com `qwen3:8b`, EPUB completo e áudio da Parte 01. A transcrição e o
alinhamento foram reutilizados do cache; nenhuma confirmação por timbre foi usada.

| Conjunto | Falas corretas | Total | Ponta a ponta | Precisão entre atribuídas |
|---|---:|---:|---:|---:|
| Treino (cenas 8–11) | 88 | 161 | 54,66% | 81,48% |
| Desenvolvimento (cena 12) | 27 | 41 | 65,85% | 100,00% |
| Teste bloqueado (cenas 13–14) | 52 | 53 | 98,11% | 100,00% |
| Total | 167 | 255 | 65,49% | 89,30% |

O modo seguro atribuiu 187 dos 251 turnos detectados. Nas cenas de desenvolvimento e
teste, nenhuma atribuição automática emitida ficou errada. A única perda no teste
bloqueado foi uma abstenção, não uma troca de personagem.

Aceitar todo consenso do Qwen, inclusive em cenas com muitos participantes, elevou o
resultado bruto para 205/255 (80,39%), porém reduziu a precisão total para 85,77%.
Essa opção não virou o padrão: uma voz errada é mais prejudicial que deixar a fala
original. O limiar reduzido por consenso agora vale somente em blocos com exatamente
dois participantes textualmente sustentados.

## O que mudou

- Fragmentos do mesmo turno literário não contam como trocas de falante.
- Alternância só preenche intervalos confirmados por âncoras nos dois lados.
- Entrada de terceiro personagem por vocativo interrompe a inferência de duas pessoas.
- Nomes em autoapresentações e relações possessivas não viram falsos destinatários ou falantes.
- Papéis anônimos explicitamente descritos recebem rótulos estáveis por cena.
- O Qwen recebe participantes locais e a sequência cronológica, não a lista global do livro.
- Uma segunda leitura crítica precisa concordar antes do limiar de consenso ser usado.
- O relatório separa treino, desenvolvimento e teste bloqueado.

## Tempo medido

- Primeira rodada completa durante o desenvolvimento: 178,17 s.
- Rodada final com respostas do Qwen já em cache: 10,94 s.
- Transcrição e alinhamento não foram refeitos nessas medições.

## Limite atual

A meta global de 95% ainda não foi atingida. O principal gargalo é a cena de multidão
do conjunto de treino: o mesmo participante anônimo reaparece como “gnomo narigudo”,
“gnomo dos artigos” ou outra descrição, e há várias entradas curtas sem atribuição.
Também restam quatro falas curtas não detectadas pelo alinhamento. O resultado de
98,11% no subconjunto consultado durante o desenvolvimento é apenas regressão
local; não permite concluir desempenho em conversas de outros livros.

Durante a revisão do gabarito, P275 e P276 estavam invertidos. O texto mostra que
P275 é Yennefer e P276 é Jaskier; o gabarito foi corrigido antes do relatório final.
