# Correcao de falas completas - Parte 01

## Resultado

| Metrica | Antes | Depois |
|---|---:|---:|
| Turnos encontrados | 250/255 (98,04%) | 251/255 (98,43%) |
| Turnos encontrados por inteiro | 105/255 (41,18%) | 250/255 (98,04%) |
| Pensamentos/textos confundidos com fala | 13 | 11 |
| Personagem correto | 143/255 (56,08%) | 156/255 (61,18%) |
| Personagem e limite ambos corretos | 58/255 (22,75%) | 155/255 (60,78%) |

O defeito de maior impacto foi corrigido. O motor agora divide um turno em regioes faladas ao redor
de atribuicoes narrativas como `disse Jaskier`, aplica a mesma identidade a todas as regioes e deixa a
voz do narrador intacta entre elas. Essas regioes continuam sendo apresentadas como uma unica fala nos
contadores da interface e do relatorio.

Das 145 falas que tinham algum defeito de limite, 144 foram recuperadas. A unica ainda incompleta e o
paragrafo 274: a interjeicao curta `Ha` nao aparece na transcricao Whisper, mas o restante da fala foi
encontrado. Permanecem quatro turnos curtos totalmente ausentes: paragrafos 38, 170, 204 e 291.

## Tempo observado

- Primeira execucao com os novos trechos e Qwen sem cache completo: 244,5 segundos para a etapa LLM.
- Reexecucao integral aproveitando o cache: aproximadamente 15 segundos para a etapa LLM.
- Medicao final apos mudar os agrupamentos: 103,4 segundos, pois alguns blocos ganharam novas chaves.
- Whisper e alinhamento foram reutilizados; nenhum MP3 original foi alterado.

## Proximo gargalo

A cobertura de limites deixou de ser o principal problema. A atribuicao de personagens agora e o
gargalo: 156 dos 255 turnos estao corretos ponta a ponta quando se considera apenas a identidade. As
maiores familias de erro continuam nas alternancias Jaskier/Rience e Jaskier/Yennefer e nos papeis
anonimos da cena do carvalho.
