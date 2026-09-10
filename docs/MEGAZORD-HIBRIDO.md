# Megazord híbrido de atribuição de falantes

## Decisão

Não existe hoje um “melhor motor” em todos os trechos. O `compact` é o baseline
mais estável; a memória local à cena resolve continuações longas, mas contamina
partes que o baseline já acertava. A v1 híbrida combina mecanismos por função,
e não soma prompts indiscriminadamente:

1. parser e âncoras literais determinísticos;
2. primeira leitura `compact-speakers-v1` sem memória;
3. proteção absoluta da âncora literal;
4. reparação com memória curta apenas nas lacunas elegíveis;
5. `turn-consistency-v2` sobre o resultado;
6. auditoria diferencial por turno para decidir a próxima mudança.

O gabarito só participa do benchmark e do comparador. O roteador executado no
produto usa exclusivamente texto, estrutura da cena, âncoras e respostas
anteriores da própria cena.

## Evidência que motivou o roteador

Comparação entre o baseline frio e `scene-local-memory-v1`:

| Desenvolvimento | Salva | Estraga | Saldo | Resultado completo da memória |
|---|---:|---:|---:|---:|
| Parte 01 | 4 | 11 | -7 | 95,02% precisão / 94,37% cobertura |
| Parte 02 | 0 | 5 | -5 | 93,26% / 97,27% |
| Parte 03 | 32 | 8 | +24 | 94,44% / 92,57% |

Na Parte 03, 16 ganhos sem dano ocorreram na cena 27. O baseline havia deixado
esses turnos sem atribuição por decisão estrutural inválida; eram exatamente a
continuação longa Coen/Ciri. Já P1 e P2 mostram que aplicar memória a toda janela
é regressivo. Esses nomes descrevem o diagnóstico do conjunto de desenvolvimento;
nenhum deles aparece nas regras do motor.

## Gate da v1

Uma janela recebe segunda leitura somente quando:

- já houve uma janela anterior na mesma cena;
- o primeiro passe deixou pelo menos um turno sem falante;
- o histórico recente estabelece entre 2 e 4 identidades;
- uma identidade sem âncora literal só entra após duas atribuições independentes
  do primeiro passe;
- a segunda leitura escolhe apenas o catálogo estabelecido, não cria entidade;
- a resposta é única, estruturalmente válida, marcada como fala e tem confiança
  declarada de pelo menos 0,95.

O reparador nunca sobrescreve uma atribuição contextual aceita. Essa assimetria
é deliberada: a v1 mira a falha comprovada de continuidade/ID que causou
abstenções, sem importar as regressões da memória completa.

## Auditoria diferencial

Exemplo:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
& .venv\Scripts\python.exe scripts\compare_speaker_runs.py `
  --gold benchmarks\part03_gold.yaml `
  --baseline output\p03-holdout-fria-20260908\analysis.json `
  --candidate scene_memory=output\p03-scene-memory-v1-20260909\analysis.json `
  --output output\comparacao-p03
```

Arquivos gerados:

- `speaker-differential.csv`: uma linha por turno, adequada para filtros;
- `speaker-differential.json`: dados e totais para outra ferramenta/IA;
- `speaker-differential.md`: resumo humano e saldo por cena.

Categorias centrais: `candidate_saves`, `candidate_harms`,
`candidate_fills_but_wrong`, `candidate_abstains_on_error`, `both_correct` e os
casos em que ambos erram. Isso permite construir versões posteriores a partir
de causas observáveis, sem selecionar manualmente respostas usando o gabarito.

## Primeira medição da v1

| Desenvolvimento | Precisão | Cobertura | Tempo | Chamadas extras |
|---|---:|---:|---:|---:|
| Parte 01 | 93,30% | 98,12% | 456,7 s | 2 |
| Parte 03 | 91,03% | 89,14% | 642,7 s | 3 |

O resultado reprovou. Em cada parte uma resposta de reparação trouxe `entities`
apesar da instrução de devolver lista vazia; a v1 descartou toda a resposta. Na
P3 isso bloqueou a continuação que concentrava as lacunas. A execução ainda
mostrou custo alto: três chamadas extras acrescentaram trabalho suficiente para
levar a atribuição textual a 642,7 segundos.

## Correção v1.1 e campanha medida

O schema da reparação agora é gerado por janela e permite somente:

- os IDs exatos dos alvos daquela chamada;
- os IDs R do catálogo já estabelecido ou `null`;
- uma decisão por alvo, sem propriedade `entities`.

Se um backend ignorar o schema e ainda devolver entidades, elas são contadas e
descartadas. Uma assignment só entra se apontar para um R permitido; portanto,
ignorar a lista não abre caminho para criar personagens. O limite de geração da
reparação caiu de 4096 para 72 tokens por alvo, limitado ao intervalo 256–2048.
O texto usado para decidir não foi encurtado.

| Desenvolvimento | Precisão | Cobertura | Tempo | Reparações aceitas |
|---|---:|---:|---:|---:|
| Parte 01 | 95,24% | 98,59% | 281,8 s | 1/1 |
| Parte 02 | 95,53% | 97,81% | 196,4 s | 0/0 |
| Parte 03 | 91,44% | 93,43% | 372,5 s | 25/28 |

Não houve erro de reparação. A P3 recebeu três chamadas de continuidade, recuperou
16 das 16 lacunas antes observadas na cena 27 e reduziu o tempo de 642,7 para
372,5 segundos. O saldo diferencial contra o baseline P3 foi +17 acertos (19
salvos, 2 estragados). A P1 não sofreu dano no diferencial (+2); a P2 não acionou
o roteador e repetiu o baseline. A meta final, porém, segue reprovada pela P3.

## v1.2 — a revisão de quem está fora do elenco (escrita, não medida)

A v1.1 fechou a reparação de lacuna. O que sobra na P3 são 28 turnos **já
atribuídos**, e o roteador não olha para eles.

A v1.2 acrescenta um segundo tipo de alvo, por um critério observável e estreito:
turno `contextual` cujo falante **não aparece no elenco estabelecido da própria
cena**. O elenco é o mesmo `active` do gate — âncoras literais recentes mais
hipóteses repetidas ao menos duas vezes.

A escolha do critério importa mais que o mecanismo. "Revisar o que parece errado"
não é observável sem gabarito e reabre a porta que a memória completa arrombou.
"Revisar quem escolheu alguém que ninguém viu falando nesta cena, e sem âncora
literal" é uma afirmação sobre a estrutura da cena, verificável em tempo de
execução, e que se desliga sozinha onde não há elenco estabelecido.

Continua valendo tudo que protegia a v1.1: âncora literal intocável, catálogo
fechado no que já está estabelecido, piso de 0,95, e o roteador não revisa o que ele
mesmo reparou. A diferença é o desfecho neutro: responder `null` **mantém** o
primeiro passe, e isso é contado à parte (`revisao_mantida`) em vez de virar
reparação rejeitada — uma revisão que quase sempre mantém está funcionando, não
falhando.

Trocar voz **não** soma em `assigned`. Só a lacuna preenchida move a cobertura;
contar a troca faria o denominador da cobertura mentir.

Entra como protocolo próprio (`hybrid-revisao`) para ser medida lado a lado com a
v1.1. Pré-registro, critério de aprovação e comando no `RODAR.md`.

## Limites e próxima decisão

A v1.1 não tenta consertar atribuições erradas de alta confiança. A memória completa
mostrou que isso poderia recuperar vários turnos da Parte 03, mas também destruir
acertos em P1/P2. A correção de lacunas passou; o próximo passo é estudar as
atribuições erradas de alta confiança da P3 por meio das discordâncias
entre as duas leituras em modo sombra; não é autorizar automaticamente a segunda.

P1, P2 e P3 são desenvolvimento. Um trecho novo, congelado e auditado antes da
primeira execução será necessário para qualquer alegação de generalização.
