# O gabarito bate com o livro? — 8 de setembro de 2026

Pergunta do proprietário, e legítima: o gabarito da Parte 01 foi escrito por um
assistente, foi consultado durante os ajustes e nunca recebeu auditoria
independente. Se estivesse errado, todo o esforço estaria mirando a resposta
errada.

**Resposta: nas verificações que dá para fazer por máquina, o gabarito bate com o
livro. Não achei nenhum erro nele.**

## O que foi verificado

### 1. Toda atribuição explícita do livro concorda com o gabarito

O parser extrai do texto as 49 falas que o livro atribui de forma explícita —
`disse Jaskier`, `observou o chanceler Vilibert`, `eu, Sheldon Skaggs`. Todas
foram comparadas com o rótulo do gabarito.

**49 concordâncias, 0 divergências.**

Estas são as únicas que dá para conferir mecanicamente contra o texto: o livro
diz quem fala, e o gabarito diz o mesmo.

### 2. Todo id do gabarito existe como fala no livro

**0 ids órfãos.** Não há numeração deslocada nem turno inventado.

### 3. O gabarito não se contradiz nas duas propriedades de diálogo

- Atribuir a fala a quem é **chamado dentro dela**: 1 suspeita, examinada à mão
  (P77) e descartada — o detector é que deu falso positivo, o gabarito está certo.
- **Três turnos seguidos da mesma pessoa** em cena de dois falantes: **0 casos.**

A segunda importa: é a mesma propriedade que a regra do sanduíche usa para
corrigir o motor. Se o gabarito a violasse, a regra estaria consertando na direção
errada.

### 4. Os turnos em disputa, lidos à mão

Os quinze turnos onde motor e gabarito discordavam foram lidos no texto do livro,
um a um. **Em todos, o gabarito está certo e o motor errado.** Alguns exemplos:

| | O que o livro escreve | Gabarito | Motor |
|---|---|---|---|
| P248 | `perguntou a feiticeira` | Yennefer | Jaskier |
| P351 | `respondeu por ela Geralt` | Geralt | Ciri |
| P90 | `Vera Loewenhaupt virou-se para Radcliffe` | Vera | Radcliffe |
| P339 | `— Sim, Eskel, sou eu.` | Geralt | Eskel |

## O que esta auditoria NÃO prova

Ela cobre as 49 falas atribuídas explicitamente mais os quinze turnos em disputa.
**As outras ~190 continuam sem verificação independente** — são as que o livro
não atribui, e conferir cada uma exige ler o capítulo inteiro decidindo à mão.

Nada aqui foi feito por outra pessoa. Continua sendo o assistente conferindo um
gabarito de assistente, e a única auditoria que resolveria isso de vez é uma
pessoa lendo a Parte 01 sem ver as respostas.

O que mudou é o peso da dúvida: as verificações mecânicas que **poderiam** ter
denunciado um gabarito ruim não denunciaram nenhuma, e todo caso em disputa que
foi ao texto deu razão ao gabarito.
