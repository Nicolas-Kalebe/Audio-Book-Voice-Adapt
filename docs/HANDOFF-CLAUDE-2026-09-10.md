# Handoff: campanha de contratos da Parte 04

Data: 10/09/2026. Branch: `feat/hybrid-speaker-router`.

## Objetivo e regra de decisão

O produto precisa atribuir corretamente as falas antes de qualquer preocupação
com conversão de áudio. O placar de produto é calculado apenas sobre turnos
`dublavel`: meta de **precisão >=95% e cobertura >=95%**. Precisão é acertos
entre turnos atribuídos; cobertura é turnos atribuídos entre os dubláveis.
Abstenção preserva o narrador, mas não é grátis: reduzir erros por abstenção pode
derrubar cobertura. O motor não pode ter regras, nomes ou respostas específicas
do livro de desenvolvimento.

A Parte 04 é desenvolvimento, não validação independente. Ela foi congelada
antes desta campanha: 279 turnos falados; 250 dubláveis; 29 figurantes; 5
coletivos ambíguos. `scripts/gold_ceiling.py` confirmou que 95x95 é atingível
no gabarito (250/250 detectáveis). Dois turnos dubláveis não foram localizados
pelo alinhamento nas execuções abaixo.

## Hipótese testada

A hipótese era que o modelo estava recebendo duas tarefas acopladas: classificar
o trecho (`speech`, `thought`, etc.) e identificar o falante. Foi implementado
um contrato experimental `speaker-only`: o inventário textual continua sendo a
fonte de `kind`, e o Qwen recebe apenas a tarefa de devolver
`{id, speaker, confidence}` ou `speaker=null`.

Também foram feitas ablações para separar os efeitos do catálogo estrito:

| condição | alteração |
|---|---|
| baseline | contrato híbrido v1.1 original |
| catalog-schema | somente schema estrito de catálogo |
| catalog-prompt | somente instrução de catálogo no prompt |
| both | `hybrid-catalog`: prompt + schema |
| speaker-only | modelo decide só a identidade; `kind` vem do inventário |

Todos os modos fizeram uma rodada fria separada, sem cache, com Qwen 3 8B local,
15 blocos da Parte 04. A mudança está no commit `49a0efc`; a documentação do
resultado no commit `3ead555`.

## Resultado

| condição | corretas | erradas | abstenções | não localizadas | precisão | cobertura | chamadas | tempo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 193 | 50 | 5 | 2 | 79,42% | 97,20% | 16 | 256 s |
| catalog-schema | 169 | 40 | 39 | 2 | 80,86% | 83,60% | 19 | 348 s |
| catalog-prompt | 177 | 43 | 28 | 2 | 80,45% | 88,00% | 16 | 288 s |
| both | 158 | 39 | 51 | 2 | 80,20% | 78,80% | 16 | 256 s |
| speaker-only | **198** | **46** | **4** | **2** | **81,15%** | **97,60%** | **15** | **240 s** |

`speaker-only` foi o melhor resultado: +5 acertos líquidos contra o baseline,
com 12 decisões salvas e 7 acertos do baseline estragados. Ele não passou a faixa
pré-registrada de promoção (+10 acertos, menos erros, precisão não menor e
cobertura >=95%), nem chegou perto da meta 95x95. Portanto é uma pista, não o
novo padrão de produção.

O catálogo estrito é reprovado nesta forma. O principal efeito foi converter
atribuições em `unknown`, perdendo cobertura. O modo combinado teve a maior
regressão. Isso confirma que prompt+schema não podem ser tratados como uma única
variável causal.

## Evidência disponível localmente

Arquivos ignorados por Git, presentes somente na máquina de teste:

- `output/contracts-p04-20260910-201844-*/analysis.json`: cada execução crua.
- `output/contracts-p04-20260910-201844-audit.json`: auditoria estrutural sem LLM.
- `output/contracts-p04-20260910-201844-comparison/`: diferencial por turno.

O diferencial de `speaker-only` registra: 12 saves, 7 harms, nenhum turno
ausente preenchido com voz errada e nenhuma abstenção nova onde o baseline errava.
Os erros restantes se dividem em 41 sem regra de coerência, 4 escritos por
`sandwich_de_tres_turnos` e 1 por `resposta_ao_vocativo`. Isso sugere que a maior
parte do gargalo continua no primeiro passe de atribuição, não nas regras de
coerência; mas os 5 erros reescritos merecem auditoria antes de se ampliar regras.

## Código e garantias já existentes

- `src/audiobook_voice_enhancer/attribution_contracts.py`: encapsula os quatro
  contratos; contratos experimentais são permitidos apenas com `hybrid`.
- `compact_speakers.py`: registra `response_contract`, preserva a decisão crua e,
  em `speaker-only`, recusa resposta antiga com `kind` em vez de reinterpretá-la.
- O reparo híbrido não recebe turnos cuja classificação de entrada não seja
  `speech` no experimento speaker-only.
- `scripts/audit_attribution_contract.py`: sumariza resultados já existentes sem
  chamar LLM nem consultar o gabarito para decidir o motor.
- 304 testes passaram antes da campanha; o replay técnico do baseline reproduziu
  15/15 pedidos congelados e as mesmas métricas.

Leitura relacionada: `docs/REVISAO-CONTRATO-DE-ATRIBUICAO.md` e
`docs/GENERALIZACAO-DO-MOTOR.md`.

## Próxima investigação recomendada

Não promover nem descartar `speaker-only` ainda. Primeiro, usar o diferencial
para classificar manualmente os 46 erros dele por evidência disponível em runtime:
âncora explícita ausente, correferência de menção/descritivo, contexto local
insuficiente, erro de modelo, ou reescrita de coerência indevida. A mudança
seguinte deve atacar a categoria dominante e passar pelos quatro filtros em
`GENERALIZACAO-DO-MOTOR.md`: observável no runtime, auto-desligável, neutra nas
partes que já passam e validada em holdout somente no fim.

A hipótese arquitetural mais promissora é uma camada explícita
`fala -> menção localizada -> identidade`, em vez de confundir uma descrição
genérica com uma identidade global. Não implementar isso sem primeiro medir a
proporção dos erros que ela realmente explica. Não reintroduzir memória de cena
completa ou regras baseadas em padrões do gabarito: experimentos anteriores já
regrediram fora da região que os inspirou.
