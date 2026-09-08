# Handoff privado — gabarito da Parte 02

Esta branch temporária é privada e descartável. Ela contém material de referência
protegido e **nunca deve ser mesclada em `main`**. Quando a revisão terminar, a
branch deve ser apagada.

## Objetivo

Criar `benchmarks/part02_gold.yaml`: um gabarito humano, congelado antes de medir
o motor, para verificar se as melhorias da Parte 01 se transferem para um trecho
novo. A Parte 01 foi usada para desenvolver as regras; ela não serve como prova
de generalização.

Não alterar o motor, a configuração ou o gabarito da Parte 01 nesta tarefa.

## Insumos presentes nesta branch

| Papel | Arquivo |
|---|---|
| Áudio | `input/Parte 02.mp3` |
| Texto do livro | `books/O Sangue dos Elfos.epub` |
| Transcrição já pronta | `cache/transcription/d11a5d6e635d5117580da226dece31a0f30fa3fba636e21e1142461f11dc9002.json` |
| Alinhamento já pronto | `cache/alignment/9cf8832dc9a7c3dea287161d2572829fcb2201cfc840e4233e83b0f055afec06.json` |
| Exemplo de formato | `benchmarks/part01_gold.yaml` |

O alinhamento da Parte 02 cobre os parágrafos do livro **371–682**. Ele é
necessário para executar o benchmark depois de congelar o gabarito; não é uma
previsão de falante e não deve guiar os rótulos de autoria.

## Como anotar

1. Leia o EPUB no intervalo correspondente e use o áudio/transcrição apenas para
   confirmar quais trechos foram efetivamente narrados.
2. Comece por uma cópia estrutural de `part01_gold.yaml`: mantenha `version`,
   `language`, `evaluation_protocol`, `scope`, `split`,
   `anonymous_role_labels`, `role_aliases` e `spoken_by`.
3. Em `scope`, registre `input/Parte 02.mp3`, o EPUB e os limites 371–682.
4. Em `spoken_by`, relacione cada turno falado ao falante correto usando IDs no
   formato `paragrafo-fragmento` (por exemplo, `412-0`). Não copie longos trechos
   literários para o YAML.
5. Papéis anônimos devem ser rótulos estáveis e descritivos; registre equivalências
   humanas em `role_aliases`. Figurantes que aparecem em uma única cena podem
   continuar marcados como figurantes, conforme o protocolo atual.
6. Congele o arquivo antes de olhar resultados do Qwen. Se um rótulo for incerto,
   documente a dúvida na `note`; não ajuste o gabarito para favorecer o motor.

## Estado que motivou esta validação

Na Parte 01, a rodada fria do Qwen 3 8B com regras de coerência atingiu **93,17%
de precisão** e **96,24% de cobertura** nos 213 turnos dubláveis. A meta do
produto é 95% em ambas. A melhoria foi desenvolvida usando o gabarito da Parte
01, portanto a Parte 02 é a primeira validação externa relevante.

Os relatórios e CSVs comparando a rodada com e sem regras estão em
`output/fria-*-regras-20260908/`.

## Depois de criar o gabarito

Não rode o benchmark antes de salvar o gabarito. Em seguida, uma rodada fria
comparável pode usar:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
& .venv\Scripts\python.exe scripts\benchmark_book_speakers.py `
  --book "books\O Sangue dos Elfos.epub" `
  --transcription cache\transcription\d11a5d6e635d5117580da226dece31a0f30fa3fba636e21e1142461f11dc9002.json `
  --alignment cache\alignment\9cf8832dc9a7c3dea287161d2572829fcb2201cfc840e4233e83b0f055afec06.json `
  --config config\config.yaml `
  --gold benchmarks\part02_gold.yaml `
  --protocol compact `
  --output output\parte02-fria-<data>
```

Use uma pasta de saída inédita. Para isolar o efeito das regras, repita a rodada
em outra pasta com `--no-turn-consistency`.
