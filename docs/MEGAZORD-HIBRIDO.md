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

## Limites e próxima decisão

A v1 não tenta consertar atribuições erradas de alta confiança. A memória completa
mostrou que isso poderia recuperar vários turnos da Parte 03, mas também destruir
acertos em P1/P2. Só uma campanha Qwen nova dirá se a reparação das lacunas passa
no pré-registro de `RODAR.md`. Se passar, o próximo passo é estudar discordâncias
entre as duas leituras em modo sombra; não é autorizar automaticamente a segunda.

P1, P2 e P3 são desenvolvimento. Um trecho novo, congelado e auditado antes da
primeira execução será necessário para qualquer alegação de generalização.
