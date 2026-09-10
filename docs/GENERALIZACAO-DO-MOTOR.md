# Generalização do motor de atribuição de falantes

Auditoria feita em 10/09/2026 sobre `feat/hybrid-speaker-router` (commit `42efad2`).
Escrito para quem pegar o trabalho em outra máquina, sem o contexto da conversa que
o originou.

## A regra que rege tudo aqui

O produto vale para **qualquer livro e qualquer audiobook**. O `AGENTS.md` já dizia:

> O produto é de uso geral. Não codifique nomes, regras ou respostas específicas do
> livro usado para desenvolvimento dentro do motor.

E o `hybrid_speakers.py` abre com `Gold labels are deliberately absent from this module`.

O que faltava dito com todas as letras, e que esta auditoria acrescenta:

**O gabarito serve para medir ONDE o motor erra. Nunca para derivar a regra que
corrige o erro.**

Um padrão observado num trecho anotado é propriedade daquele trecho — não do
português, não do diálogo em geral. A distância entre "vi que aqui alterna" e "logo,
alternância é regra" é exatamente onde o motor deixa de servir ao próximo livro.

### O erro que motivou este documento

Durante a análise da Parte 03 foi proposta uma regra: "dentro de um bloco de
alternância estrita entre dois falantes, o turno *n* tem a identidade do turno
*n−2*". A proposta veio de olhar o gabarito e ver cinco blocos de aula com
alternância 100% perfeita (P861-1046: Lambert 28 turnos, Triss 41, Vasemir 29,
Coen 41, Geralt 43 — nenhuma quebra).

A regra está errada por dois motivos, e os dois valem como teste para qualquer
proposta futura:

1. **Quebra na própria parte de onde foi tirada.** A cena do conselho (P690-807) tem
   uma sequência de **6 falas seguidas do mesmo personagem**. A alternância estrita é
   propriedade dos blocos de aula, não da Parte 03.
2. **Quebra em qualquer livro** com narrador que interrompe o diálogo, fala dupla
   consecutiva, ou três pessoas em que duas alternam e uma comenta.

E ela era, além de errada, **redundante** — ver o item 2 da auditoria abaixo.

### Os quatro filtros de uma regra candidata

Aplicar nesta ordem, e parar no primeiro que reprovar:

1. **Observável em tempo de execução.** A regra decide com texto, estrutura da cena,
   âncoras literais e respostas anteriores da própria cena. Se precisa de algo que só
   o gabarito sabe, morre aqui.
2. **Auto-desligável.** Sem a premissa (não há alternância detectada, não há elenco
   estabelecido), a regra se abstém em vez de chutar.
3. **Neutra nas partes que já passam.** É o filtro mais barato e o mais revelador: a
   memória de cena completa fazia +24 na P3 e −7/−5 em P1/P2, e foi isso que a
   reprovou. Regra que melhora uma parte e mexe nas outras é suspeita.
4. **Só então holdout novo**, congelado e auditado antes da primeira execução.

Note a diferença entre *detectar* e *assumir*: "as últimas K atribuições formam
alternância estrita entre exatamente duas identidades" é observável em runtime e se
desliga sozinho onde a premissa não vale. "Blocos de aula alternam" é o gabarito
vazando para dentro do motor.

## Auditoria de especificidade — o que foi encontrado no código

### 1. `ROLE` é vocabulário fechado e enviesado para fantasia

`src/audiobook_voice_enhancer/dialogue.py:33`. A lista de papéis que serve de âncora
("disse **o bruxo**", "respondeu **a feiticeira**") é:

> artesã, artesão, artista, anão, anã, bardo, bruxo, bruxa, cavaleiro, cavaleira,
> chanceler, druida, elfo, elfa, feiticeiro, feiticeira, guerreiro, guerreira, mago,
> maga, poeta, sacerdote, sacerdotisa(s), trovador, trovadora, gnomo, gnoma,
> taberneiro, taberneira, albergueiro, albergueira, filha(s)

É fantasia medieval inteira. Não é o nome do livro de desenvolvimento, então não
viola a letra da regra do `AGENTS.md` — mas viola o espírito. Num policial, num
romance contemporâneo ou numa biografia, **nenhum** desses termos aparece, e os
papéis daquele gênero faltam todos: delegado, médico, capitão, professora, garçom,
enfermeira, padre, motorista, engenheiro.

O efeito é silencioso, e é o pior tipo de falha para este projeto: não quebra nada,
apenas deixa de ancorar. Perde cobertura sem gerar um único erro visível.

Usada em quatro pontos de `dialogue.py` (linhas 203, 380, 388, 408), inclusive na
detecção de papel anônimo.

**Medir antes de mexer:** quantas âncoras literais de P1/P2/P3 vêm de `ROLE`? Se
forem poucas, a lista é peso morto enviesado. Se forem muitas, é uma dependência de
gênero disfarçada de regra geral — e o caminho passa a ser derivar o papel do texto
(aposto ao nome, artigo + substantivo que reaparece junto da mesma entidade) em vez
de manter uma lista fechada que alguém precisa lembrar de atualizar por gênero.

### 2. A regra de alternância já existe — melhor guardada do que a proposta

`src/audiobook_voice_enhancer/turn_consistency.py:92`:

```python
def apply_consistency(model, *, max_speakers: int = 2, window: int = 6)
```

A regra `sanduiche_de_tres_turnos` já faz o que foi proposto: se o turno anterior e o
seguinte são do mesmo falante e a janela local tem no máximo `max_speakers` vozes,
reescreve o do meio para o outro falante. E tem dois freios que a proposta não tinha:

- `sandwich_blocked_by_vocative` — não reescreve quando o turno chama o outro pelo
  nome, porque isso inverteria o par inteiro;
- `compound_monologue` — turno composto com 250 caracteres ou mais é tratado como
  monólogo retomado depois de inserção narrativa, não como resposta curta.

Há ainda `vocativos_reciprocos` (A chama B, B chama A — relação textual simétrica que
funciona mesmo com elenco grande), `referencia_em_terceira_pessoa` e
`resposta_ao_vocativo`, todas com abstenção explícita quando não há substituto
sustentado pelo texto.

**Consequência prática:** antes de propor regra estrutural nova, ler
`turn_consistency.py` inteiro. O que parece faltar provavelmente já está lá, com os
freios que a versão ingênua não tem.

### 3. Correção sobre o gate do roteador híbrido

Registrado porque a leitura errada circulou antes de ser conferida.

Em `hybrid_speakers.py`, o `plan()` calcula:

```python
recent = self.records[scene_id][-self.history_limit:]   # history_limit = 12
active = literal | {identity for identity, count in hypothesis_counts.items() if count >= 2}
if len(active) > self.max_speakers:  # max_speakers = 4
    self.audit["skipped"]["cast_too_large"] += 1
```

`active` sai dos **últimos 12 registros da cena**, não do elenco da cena inteira. Ou
seja, o gate mede **janela local**, não tamanho de cena. É incorreto afirmar que
cenas coletivas de sete vozes ficam sempre fora do roteador: elas ficam de fora
quando a janela local passa de quatro identidades, e a frequência disso é um dado que
o próprio audit já grava.

**Quem responde é `skipped["cast_too_large"]` no `analysis.json` da campanha.** Ler
esse contador antes de mexer no gate.

### 4. Menores

- `src/audiobook_voice_enhancer/gui.py:166` —
  `default_book = ROOT / "books" / "O Sangue dos Elfos.epub"`. O livro de
  desenvolvimento é o padrão da interface. É UI, não motor, mas é o nome do livro
  dentro do código.
- Comentários em `dialogue.py` e `turn_consistency.py` citam Geralt, Vasemir e Eskel
  como exemplo do caso que motivou a regra. **Não afetam comportamento e devem
  ficar**: explicam o porquê, que é o padrão de documentação da casa. A regra do
  `AGENTS.md` fala de codificar nomes *dentro do motor*, não de citá-los ao explicar
  uma decisão.

## A conta do que falta para 95×95 na Parte 03

Esta parte não depende de nenhuma inferência sobre o livro — é propriedade da métrica,
e vale para qualquer parte de qualquer obra.

O gabarito da P3 foi conferido: **nenhum turno duplicado** entre falantes, **nenhuma
sobreposição** entre `spoken_by` e `non_spoken`. 8 falantes, 358 turnos anotados.

`anonymous_role_labels` (a "Voz metálica através de Ciri", 8 turnos) é classificado
como **figurante** por `benchmark.py:171`, e figurante fica fora da conta que decide o
produto — decisão do proprietário em 08/09/2026. Logo:

| | |
|---|---:|
| Turnos dubláveis | **350** |
| Não detectados | 13 |
| Detectados | 337 |
| Abstenções | 10 |
| Atribuídos | **327** |
| Corretos | **299** |
| Errados | **28** |

Confere com o RODAR: 299/327 = 91,44% de precisão · 327/350 = 93,43% de cobertura.

**Para passar nos dois lados:**

- Cobertura ≥ 95% exige **333 atribuídos** (+6).
- Com 333 atribuídos, precisão ≥ 95% exige **317 corretos** (+18).
- Fecha assim: 6 abstenções viram acerto, 12 erros viram acerto → 333 atribuídos,
  317 corretos, 16 errados.

**Duas consequências que restringem a estratégia:**

1. **Abster mais não ajuda.** Trocar erro por abstenção sobe a precisão e derruba a
   cobertura, que já está no limite. Cada abstenção nova custa direto.
2. **Detecção sozinha não resolve.** Recuperar os 13 turnos perdidos, todos com
   acerto, dá 312/340 = 91,8% — ainda reprovado. O gargalo é precisão, e precisão só
   sobe convertendo erro em acerto.

### Mapa da parte, para orientar onde medir (não o que decidir)

| Região | Turnos dubláveis | Vozes | Alternância |
|---|---:|---:|---|
| Conselho coletivo P690-807 | 79 | 7 | 90%, sequência de até 6 |
| Transe Geralt/Triss P808-860 | 38 | 2 | 97%, máximo 2 |
| Aulas duas a duas P861-1046 | 182 | 6 (em pares) | 100% estrita |
| Coletiva final P1047-1126 | 51 | 7 | 90%, máximo 3 |

Esta tabela diz onde procurar. Não autoriza nenhuma regra.

## As duas perguntas que decidem o próximo passo

Nenhuma das duas precisa de suposição sobre o livro, e as duas são respondidas por
dados que a campanha v1.1 já produziu:

1. **Onde caem os 28 erros?** O `speaker-differential.csv` da P3 dá a contagem por
   região e por categoria (`candidate_harms`, `candidate_fills_but_wrong`,
   `candidate_abstains_on_error`). Sem isso, qualquer escolha entre atacar o gate,
   a alternância ou a terceira pessoa é chute.

2. **Quantos dos 28 já passaram por uma regra de `turn_consistency`?** Os contadores
   existem: `sandwich_rewrites`, `vocative_rewrites`, `reciprocal_vocative_rewrites`,
   `phase_slip_rewrites`, `third_person_rewrites`, mais as duas abstenções
   (`vocative_abstentions`, `third_person_abstentions`). Cada turno reescrito carrega
   `consistency_rule` com o nome da regra.

   **O comparador já responde isto** desde 10/09/2026: o diferencial traz a coluna
   `<candidato>_consistency_rule` no CSV, `wrong_by_consistency_rule` no JSON e a
   seção *"Erros que restaram, por regra que escreveu a voz"* no Markdown, com
   `sem_regra` para o que veio da primeira leitura. Não precisa de campanha nova —
   roda sobre os `analysis.json` que já existem.

   Se boa parte dos erros for reescrita feita por essas regras, **o problema não é
   falta de regra — é regra ativa demais em cena que não é de duas pessoas**. Nesse
   caso o caminho é apertar a condição `few` (hoje `max_speakers=2` sobre janela de
   6), não escrever mecanismo novo.

Os arquivos de saída ficam sob `output/`, que está no `.gitignore` e portanto não
viaja entre máquinas. Quem for continuar precisa rodar na máquina onde a campanha
existe, ou trazer os CSV/JSON à mão.

## O que não fazer

- Não escrever regra derivada de padrão visto no gabarito.
- Não propor mecanismo novo antes de ler `turn_consistency.py` inteiro.
- Não trocar erro por abstenção para "melhorar a precisão" — a cobertura da P3 não
  tem folga.
- Não afirmar que uma etapa foi pulada sem ler o contador do audit que registra
  exatamente isso.
- Não iniciar campanha nova sem pré-registro, como o MEGAZORD-HIBRIDO já exige.
