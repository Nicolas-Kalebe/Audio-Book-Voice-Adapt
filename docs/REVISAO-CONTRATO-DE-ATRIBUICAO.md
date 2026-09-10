# Parecer e implementação para a próxima revisão (Claude/Codex)

10/09/2026. Branch `feat/hybrid-speaker-router`. O parecer detalhado original foi
preservado em `output/review-architecture/PARECER.md`, junto de `audit.py`.
Essa pasta não viaja por Git. Este documento registra as conclusões sem trechos
literários para permitir revisão na outra máquina.

## O diagnóstico anterior precisava ser corrigido

Na P4, o híbrido v1.1 teve 193 corretos, 50 errados, 5 abstenções e 2 não
localizados entre 250 dubláveis: 79,42% × 97,20%. O `hybrid-catalog` v1 teve
158 corretos, 39 errados, 51 abstenções e 2 não localizados: 80,20% × 78,80%.
O candidato salvou cinco decisões e estragou quarenta acertos.

Dos 40 danos, 18 chegaram a `unknown_or_below_threshold` (tipo unknown), dez a
`invalid_compact_decision`, quatro envolveram vocativos e oito outras atribuições
erradas. O Qwen chegou a devolver a identidade correta com confiança 1,0 e tipo
unknown; o tipo impediu a atribuição. Isso é distinto de rejeitar uma menção.

Das 25 propostas de entidade recusadas, sete têm correspondência única se
ignorarmos caixa, 12 não constam do parágrafo citado, quatro se repetem nesse
parágrafo e duas contêm campos inválidos. Não há evidência para culpar apenas
capitalização. Das 63 propostas novas do candidato, todas eram anonymous,
inclusive nomes próprios; 38 foram aceitas, mas só 23 criaram identidades.
No baseline, todas as 90 propostas eram named com ID E (recusadas como novas).

Em 26 dos 50 erros do baseline o nome esperado estava disponível no catálogo;
em outros 13 havia uma forma curta, verificada lexicalmente, sem garantir
equivalência semântica. Faltava correspondência em 11. Ausência de elenco explica
parte do problema, mas não basta. O benchmark detectou 248/250 dubláveis.

O baseline preserva capacidades úteis: 33/35 atribuições explícitas detectadas
corretas e 160/208 contextuais. As propostas brutas acertaram 186 dubláveis,
contra 193 no resultado final. Essa diferença inclui âncoras e todas as políticas,
não é a contribuição causal de uma regra isolada. Não apagar toda a pipeline.

## Implementado neste turno: experimento controlado do contrato

`attribution_contracts.py`, com opção `book_first.attribution_contract` e flag
`--attribution-contract`. Os modos experimentais exigem `--protocol hybrid`:

| Modo | Prompt base | Schema base | Conteúdo da janela |
|---|---|---|---|
| baseline | original | original | original |
| catalog-schema | original | estrito de hybrid-catalog | original |
| catalog-prompt | sufixo de hybrid-catalog | original | original |
| speaker-only | só identidade | assignments sem kind | original + input_kind |

`hybrid-catalog` continua reproduzível como condição prompt+schema juntos. As
ablação schema/prompt não mudam a versão nem o conteúdo inicial do payload;
o cache diferencia cada requisição pelo prompt/schema. Em janelas seguintes,
as entidades criadas podem alterar o catálogo: é efeito do experimento, não
garantia de que todos os payloads da campanha continuarão iguais entre modos.

Em speaker-only o modelo devolve `{id, speaker, confidence}`. `speaker=null`
expressa identidade não resolvida. O motor conserva a classificação de entrada;
unknown, thought e citation não recebem voz, inclusive pelo reparo híbrido.
Respostas antigas com kind são recusadas, não reinterpretadas retroativamente.
`raw_decisions` conserva a resposta original; `input_kind` e
`classification_source=upstream_inventory` registram de onde veio a classificação.
Âncoras explícitas e a política de confiança continuam em vigor.

**Limite deliberado:** o inventário não é um classificador perfeito. Um pensamento
com travessão pode chegar como speech; uma fala entre aspas pode chegar como
unknown. Esta ablação não cria um classificador independente, nem prova que os
tipos de entrada estão corretos. O prompt permite abster se um trecho marcado
speech não for audível. A campanha precisa acompanhar não-falas e cobertura,
sem usar o gabarito para definir input_kind em produção.

O reparo continua com seu contrato original e limiar próprio; neste experimento
somente recebe turnos de entrada speech. A separação estudada é a do primeiro
passe. Não alegar que toda a pipeline de classificação foi substituída.

`review.response_contract` contabiliza tipos de entidade, tipos das assignments
e unknown com identidade resolvida. `scripts/audit_attribution_contract.py`
compara relatórios existentes sem inferência, sem reavaliar rótulos e sem exportar
texto do livro. Distingue explicitamente escopo textual de denominador dublável.
O benchmark agora também aceita replay exato do protocolo hybrid-catalog;
ele só funciona com o cache do mesmo pedido, nunca por equivalência aproximada.

## Por que isso vem antes da camada de menções

O último experimento mudou prompt e schema simultaneamente. O colapso para
anonymous/unknown não permite atribuir a causa a uma dessas variáveis. Os dois
controles isolam isso; speaker-only testa a simplificação proposta. Nenhum ganho
do Qwen foi medido neste turno de implementação.

A evolução seguinte continua sendo `fala → menção → identidade`. Uma ocorrência
de “a médica” deve ter posição e ID próprios, sem virar automaticamente outra
pessoa ou ser fundida com todas as médicas. Essa camada de correferência ainda
não foi implementada. Reintroduzir source_subjects ou scene-memory inteiros
repetiria experimentos regressivos já registrados.

Essa divisão tem antecedentes em atribuição literária:

- [Vishnubhotla et al., ACL 2023](https://aclanthology.org/2023.acl-short.64/):
  personagens, correferência, identificação de falas e atribuição avaliadas separadamente.
- [BookNLP](https://github.com/booknlp/booknlp): componentes existentes, orientados
  ao inglês, sem validação direta no nosso português.
- [ModernBookNLP, preprint de agosto de 2026](https://arxiv.org/html/2608.02359v1):
  pontuação conjunta de falas e menções em contexto compartilhado. Os 94,5% no
  PDNC usam inglês e listas anotadas de personagens; não equivalem à nossa meta.
  A ideia de encoder especializado é alternativa futura, não promessa local.

## Handoff

Verificação técnica concluída: **304 testes passaram**. Inclui isolamento dos
contratos/cache, recusa de campos antigos, IDs inexistentes, respostas duplicadas,
confiança inválida, abstenção e proteção de não-falas na janela de reparo.
O replay técnico da P4 consumiu as **15 respostas exatas** do baseline, zero
inferências novas, e preservou todas as métricas by_class. O script da CLI foi
verificado; a auditoria dos dois relatórios antigos reproduziu os tipos e números.

Rodar a fila no topo do RODAR no turno de testes. Ela congela cinco condições e
critérios antes de ver resultados. Se uma condição se destacar, confirmar por
repetição e regressão P1–P3 antes de pensar em promoção. Partes 1–4 são
desenvolvimento. Preservar outro livro como holdout. Nenhuma conversão ou novo ASR
foi medido; o tempo anterior de 247,641 s cobre somente atribuição textual da P4.
