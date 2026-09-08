# Referências de falantes no compacto

## Resultado que orienta esta alteração

Em `compact-context-fixed-20260908`, o compacto acertou 178/255 (69,80%) em
247,735 segundos. O `lightweight-context-fixed-20260908` acertou 128/255
(50,20%) em 301,688 segundos. Ambos tiveram 14 chamadas, zero cache hits e
nenhum erro de execução. São tempos da atribuição textual, não da conversão.

O lightweight não é recomendado. Seu código permanece apenas para reproduzir o
experimento. O padrão continua compacto e esta alteração fica desativada até a
comparação controlada.

A hipótese de que o lightweight simplesmente reduziu o catálogo não é sustentada
pelo código: ele usa a mesma seleção básica de candidatos do compacto. Alterou
schema e informações do prompt, e suas respostas criaram novas identidades
anônimas até para nomes conhecidos. Isso fragmentou identidades e produziu
referências inexistentes/rejeitadas. Não é possível separar a contribuição de
cada mudança sem ensaios adicionais.

No compacto, 49 dos 77 erros estão na cena com muitos interlocutores. A inspeção
do texto revelou sujeitos explícitos com títulos e descrições que não eram
registrados adequadamente. Essa lacuna é o alvo deste experimento.

## Comportamento da opção source_subjects

- Localiza referências literais imediatamente após verbos de atribuição na narração.
- Descobre nomes com títulos, como “a capitã Luma”, por uma regra gramatical geral.
- Oferece descrições sem nome como candidatos com referência ao parágrafo original.
- Mantém candidatos já existentes, inclusive nomes mencionados; a pista do sujeito
  ajuda o modelo a distinguir quem fala de quem apenas aparece no assunto da fala.
- Permite escolher uma identidade já nomeada para uma descrição. Não transforma
  automaticamente duas descrições iguais em uma única pessoa.
- Mantém schema, janelas, limiar e uma chamada por janela do compacto. Não gera
  elenco em uma chamada extra e não incorpora as restrições do lightweight.

Não é um analisador gramatical completo: locuções extensas, sujeitos elípticos,
descrições longas e correferências ainda dependem do modelo. Referências de uma
mesma pessoa podem continuar fragmentadas; a avaliação deve verificar isso. Não
há regras com nomes do livro, aliases automáticos baseados em profissão ou
alterações do gabarito. Nomes curtos versus completos continuam pontuados pelo
mesmo critério literal.

As referências ficam em `turns[].source_subjects`; os contadores
`review.source_subjects` têm escopo do livro inteiro, não apenas do áudio avaliado.

## Verificação e próximo teste

181 testes passaram. As entradas dos 266 turnos da Parte 01 (14 janelas) foram
verificadas offline: cada referência aponta para um candidato existente e para
texto literal presente na janela. Essa verificação não executou Qwen.

O ensaio sem LLM `compact-subjects-plumbing-20260908` registrou 39/255 corretas
em 41 atribuições, versus 35/255 em 36 atribuições da referência anterior sem LLM.
Uma nova atribuição foi penalizada por nome curto versus completo. Esse teste
verifica as regras e a integração, não a acurácia contextual do Qwen.

Executar o script habitual com livro/transcrição/alinhamento/config/gabarito
congelados e os seguintes argumentos finais, em sequência e pastas inéditas:

```text
--protocol compact --output output/compact-subjects-control-20260908
--protocol compact --source-subjects --output output/compact-subjects-qwen-20260908
```

Os demais argumentos estão em [LIGHTWEIGHT_ATTRIBUTION.md](LIGHTWEIGHT_ATTRIBUTION.md).
Para uso experimental pela pipeline, a opção equivalente é
`book_first.source_subjects: true` com `book_first.protocol: compact`.

Comparar corretas/255, omissões, atribuições erradas, identidade dos anônimos e
tempo. Examinar regressões nos personagens principais e se o mesmo anônimo recebe
IDs diferentes. Não reconciliar nomes ou reduzir o denominador após olhar as
respostas. A meta continua pelo menos 230/255 neste gabarito de desenvolvimento,
seguida de avaliação independente em outros livros.
