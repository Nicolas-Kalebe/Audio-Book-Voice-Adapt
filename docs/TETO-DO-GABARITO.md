# O teto do gabarito — 8 de setembro de 2026

## O que estava errado

Um motor que acertasse o falante de **todos** os 255 turnos da Parte 01 marcava
**208/255 (81,57%)** neste gabarito. A meta do proprietário é 230/255 (90%).
Nenhuma troca de modelo, prompt, schema ou protocolo alcançava a meta.

As cinco campanhas registradas em [`SPEAKER_ATTRIBUTION_HANDOFF.md`](SPEAKER_ATTRIBUTION_HANDOFF.md)
— evidence 35/255, scene 141/255, compact 178/255, lightweight 128/255 e
compact+source_subjects 139/255 — foram comparadas com um instrumento que tinha
um limite fixo 8,5 pontos abaixo do alvo. A diferença entre 69,80% e 90% nunca
foi só identificação.

## A causa

`benchmark.evaluate` compara o falante literalmente:

```python
is_correct = _fold(predicted) == _fold(expected)
```

`predicted` é o `display_name` da entidade. Para toda entidade anônima,
`book_speakers._entity` escrevia o desambiguador dentro do próprio rótulo:

```python
label = canonical[0].upper() + canonical[1:]
if kind == "anonymous":
    label += f" [cena {scene + 1}, P{paragraph}:{origin}]"
```

O gabarito rotula 42 turnos (16,5% do total) por papel: `Elfo alto e louro`,
`Gnomo dos artigos metalicos`, `Sacerdote gordo`, `Taberneiro`, `Druida grisalho`
e mais nove. O motor emitia `Taberneiro [cena 3, P12:40]`. Os dois nunca casam.

Isso explica sozinho a coluna de 0,00% desses papéis em
[`../benchmarks/PART01_BASELINE_REPORT.md`](../benchmarks/PART01_BASELINE_REPORT.md)
e boa parte dos **49 dos 77 erros concentrados na cena de multidão** relatados em
[`SOURCE_SUBJECTS.md`](SOURCE_SUBJECTS.md): a cena de multidão é onde moram os
papéis anônimos.

## A cena de multidão era, em boa parte, o mesmo defeito

`SOURCE_SUBJECTS.md` registra que **49 dos 77 erros** do compacto estavam "na cena
com muitos interlocutores", e a conclusão tirada dali foi que o gargalo era o
raciocínio do modelo em cenas de elenco grande.

Os parágrafos do gabarito dizem outra coisa. A cena do carvalho ocupa mais ou
menos P70–P148, e dentro dela moram **34 turnos de papel anônimo**: Elfo alto e
louro (9), Gnomo dos artigos metálicos (5), Sacerdote gordo (4), Guerreiro ruivo
de Skellige (4), Filhas de Vilibert (3), Druida grisalho (3), Elfa do gorro de
arminho (2), Jovem aprendiz de artesão (2), Camponês anônimo (1) e Membro anônimo
da multidão (1). Todos os 34 pontuavam zero **por construção do avaliador**, e
não por falha de identificação.

Ou seja: dos 49 erros da cena de multidão, até 34 podiam ser artefato do
instrumento. Sobram ~15 erros reais ali. A conta que dizia "mesmo consertando
vocativo e alternância o motor para em 206/255, logo a meta é inalcançável"
partia desse 49 contaminado e não se sustenta.

Quanto exatamente cada coisa vale só a rodada fria dirá — o motor pode reconhecer
mal a descrição do papel mesmo com o rótulo corrigido. Mas a leitura de que a
cena de multidão é um problema de raciocínio do modelo estava, no mínimo,
superdimensionada.

## O segundo defeito, este de produto

`_entity(..., fresh=True, origin=span["start"])` criava uma identidade nova a
cada menção. O mesmo figurante que fala cinco vezes virava cinco pessoas — e no
audiobook receberia cinco vozes diferentes. É o mesmo defeito que
`SOURCE_SUBJECTS.md` observou ("fragmentou uma mesma pessoa em vários nomes de
descrição") e atribuiu ao protocolo; a origem é a função de identidade.

## O que mudou

- `display_name` é o texto do livro. Cena e offset viraram o campo
  `disambiguator` e só entram no rótulo quando outra identidade já ocupa o mesmo
  nome. A unicidade continua no ID.
- `anonymous_scope` (padrão `"scene"`): a mesma descrição literal dentro de uma
  cena é uma pessoa só. Descrições diferentes continuam separadas — a fusão é
  por descrição, nunca por profissão. `"mention"` reproduz o comportamento
  anterior.
- `evaluate` ganhou `speaker_correct_turns_by_identity` **ao lado** da coluna
  literal, que ficou intacta, e `literal_only_misses` para auditar a diferença.
  `role_aliases`, no gabarito, recebe descritores equivalentes por revisão
  humana, escritos antes da rodada.
- `scripts/gold_ceiling.py` mede o teto com um oráculo perfeito e sai com código
  1 quando a meta é inalcançável. `tests/test_gold_ceiling.py` trava a
  propriedade: toda perda do oráculo tem de ser fala não localizada no áudio.

**Teto: 208/255 (81,57%) antes, 250/255 (98,04%) depois.** As cinco perdas
restantes são P38, P170, P204, P274 e P291, que o alinhamento não localiza.

## Troca assumida

Dois anônimos com a mesma descrição literal na mesma cena passam a ser a mesma
pessoa. Isso contraria a regra escrita em [`SCENE_ATTRIBUTION.md`](SCENE_ATTRIBUTION.md)
("dois anônimos com a mesma descrição e introduções diferentes mantêm IDs
diferentes"). O motivo de inverter: duas pessoas com uma voz incomoda menos que
uma pessoa com cinco, e a regra antiga custava 42 turnos por si só. Volta com
`anonymous_scope: mention`.

## O que isto obriga na próxima rodada

O `178/255` foi medido sob o avaliador quebrado. **Não é linha de base.** A
próxima rodada fria tem de reestabelecer a linha de base sob a métrica corrigida
**antes** de qualquer regra nova de identificação, senão o ganho de uma regra
fica indistinguível do ganho desta correção. Comando único e ganho
pré-registrado em [`../RODAR.md`](../RODAR.md).

## A lição de método

Rodar `scripts/gold_ceiling.py` custa trinta segundos e não precisa de GPU.
Rodar uma campanha custa minutos de GPU e a presença do proprietário. A ordem
certa é medir o teto do instrumento antes de medir o motor com ele — nenhuma das
cinco campanhas anteriores teria sido informativa sem isso.
