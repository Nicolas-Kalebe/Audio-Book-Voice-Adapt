# Resultado da rodada fria — 8 de setembro de 2026

Rodada do proprietário: `--protocol compact`, Qwen 3 8B local, cache de respostas
vazio (`cold_response_cache_valid: true`, 14 chamadas, 0 reaproveitadas), 267,6 s.

## O que a rodada mostrou

| | Antes (medida antiga) | Nesta rodada |
|---|---:|---:|
| Corretas / 255, comparação literal | 178 (69,80%) | 178 (69,80%) |
| Corretas / 255, por identidade | — | 178 (69,80%) |

**A correção de rótulo não moveu o placar de 255, e a hipótese que a motivou
estava errada.** Eu supus que o motor já reconhecia os papéis anônimos e só
errava a grafia. Não era isso: `literal_only_misses` veio **zero**, e a linha de
figurante ficou em **1 acerto entre 29 atribuições**. O motor genuinamente não
identifica figurante.

O que a correção fez foi outra coisa, e é ela que importa: **separou as duas
populações**, que antes se somavam num número só.

| Classe | Total | Atribuídos | Corretos | Errados | Sem atribuição | Precisão | Cobertura |
|---|---:|---:|---:|---:|---:|---:|---:|
| dublável | 213 | 208 | 177 | 31 | 3 | **85,10%** | **97,65%** |
| figurante | 42 | 29 | 1 | 28 | 13 | 3,45% | 69,05% |

Com a decisão de 08/09 — figurante de uma cena só não ganha voz — a linha que
decide o produto é a primeira. **O motor estava em 85,10% de precisão, não em
69,80% de acerto.** Os 69,80% misturavam o trabalho que vale com o trabalho que
foi descartado por decisão de produto.

## As regras de coerência

Os 31 erros dublaveis não eram difusos. Na cena 10 o diálogo alterna Jaskier e
Rience turno a turno, e **todo erro é a mesma pessoa três turnos seguidos** —
P158/P159/P160 todos Rience, quando o do meio é Jaskier. Mesmo padrão nas cenas
12 e 13.

`turn_consistency.py` aplica duas propriedades de diálogo depois que o modelo
responde. Não chama o modelo, não muda prompt nem schema.

| | Corretas | Errados | Sem atribuição | Precisão | Cobertura |
|---|---:|---:|---:|---:|---:|
| rodada original | 177 | 31 | 3 | 85,10% | 97,65% |
| + nome curto → completo | 181 | 27 | 3 | 87,02% | 97,65% |
| + vocativo e sanduíche | **191** | **14** | 6 | **93,17%** | **96,24%** |

O `Radcliffe` / `Radcliffe de Oxenfurt` eram duas entidades e uma pessoa: quatro
turnos perdidos por nomenclatura, o mesmo defeito do rótulo de anônimo.

O veto de vocativo não é enfeite. Sem ele o sanduíche quebrava 4 turnos certos,
porque invertia pares como *"Lembranças de Dijkstra, Jaskier"* — dito por
Yennefer, atribuído ao Jaskier, que é quem está sendo chamado.

## O que falta para 95% × 95%

Faltam **4 acertos**. Dos 20 turnos ainda pendentes, **12 estão na cena 9**, a do
carvalho, e a causa tem nome: **Vilibert não recebe nenhuma âncora explícita de
fala no livro inteiro.** O parser encontra `disse Sheldon` oito vezes, `disse
Donimir` quatro, `disse Vera` três — e nenhuma para Vilibert. Sem âncora, o
modelo entrega as falas dele a quem tem. Seis dos doze erros da cena são
exatamente isso.

Os outros dois grupos: quatro na cena 12 e quatro na cena 13, onde três já viraram
abstenção pela regra de vocativo — que é o comportamento pedido, não defeito.

## Confirmação: as duas rodadas frias

O proprietário rodou com e sem as regras, cache vazio nas duas:

| | Precisão | Cobertura | Corretos | Errados | Sem atribuição |
|---|---:|---:|---:|---:|---:|
| `--no-turn-consistency` | 87,02% | 97,65% | 181 | 27 | 3 |
| com as regras | **93,17%** | 96,24% | 191 | 14 | 6 |

Batem **exatamente** com a simulação offline, o que era esperado: as regras são
pós-processamento determinístico. O resultado caiu dentro da faixa pré-registrada
de 92–94%.

## A causa dos 12 erros da cena do carvalho não era o modelo

O livro atribui as falas do Vilibert **todas as vezes**:

```
P92:  — Comenta-se – observou o chanceler Vilibert – que Yennefer…
P116: — Tenho de admitir – falou o chanceler Vilibert…
P120: — Querem nosso sangue! – urrou o chanceler Vilibert.
P134: — Nilfgaard é governado… – esbravejou o chanceler Vilibert.
```

A regex de âncora aceitava `verbo + artigo + Nome`. Aqui há um **cargo entre o
artigo e o nome**, e ela não atravessava. Resultado: o Vilibert não recebia uma
única atribuição explícita no livro inteiro, e o modelo entregava as falas dele a
quem tinha âncora — `disse Sheldon` aparece 8 vezes.

Corrigido com `TITLE_GAP` (até duas palavras não funcionais entre o artigo e o
nome) mais os verbos que faltavam. **Âncoras corretas: 35 → 46. Falsas: 1 → 0.**

Reaplicado sobre a rodada fria: **95,15% de precisão, 96,71% de cobertura**. É
estimativa — âncora nova muda o payload do modelo, então os outros turnos podem
se mexer — e a próxima rodada fria decide.

Sobram cinco turnos de coreferência por descrição (`sorriu o feiticeiro`,
`refutou a guerreira`, `retrucou o anão`), que exigem ligar a descrição ao nome
que o próprio texto apresentou.

## Limite honesto destes números

As regras foram ajustadas **contra o mesmo gabarito que as pontua**. Foram 13
variantes na bancada e 12 combinações de parâmetro, todas medidas na Parte 01.
O número 93,17% é regressão de desenvolvimento, **não é estimativa de desempenho
em livro novo**, e a diferença entre ele e o 85,10% de partida deve ser tratada
como teto otimista até uma rodada fria confirmar e um segundo livro validar.

O que **não** depende deste gabarito são as duas propriedades: quem é chamado
dentro da fala não é quem fala, e três turnos seguidos da mesma pessoa não é
diálogo. As duas são de língua, não deste livro, e é por isso que têm chance de
transferir.

`scripts/simulate_rules.py` reaplica qualquer regra sobre um `analysis.json`
existente e reporta **ganhos e perdas separados**, sem GPU. Delta líquido esconde
troca de dez por oito.
