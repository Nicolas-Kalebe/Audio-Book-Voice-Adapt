# Guia de uso — Audio-Book-Voice-Adapt

## O que você precisa

1. O audiobook em MP3, M4A, FLAC, WAV, OPUS, OGG ou AAC.
2. O texto da mesma edição do audiobook, preferencialmente EPUB.
3. Uma referência WAV limpa de 10–30 segundos para cada personagem em `mode: convert`.
4. Aproximadamente 15–25 GB livres para modelos e cache.
5. Direito ou autorização para usar o livro, o audiobook e as vozes.

O ambiente, FFmpeg, PyTorch CUDA e Seed-VC já estão instalados nesta máquina. Os pesos grandes do Whisper `large-v3` e do Seed-VC são baixados automaticamente no primeiro uso.

## Onde colocar os arquivos

```text
Audio-Book-Voice-Adapt/
├── input/                 MP3s dos capítulos
├── books/                 EPUB ou TXT para alinhamento
├── voices/                referências WAV dos personagens
├── config/
│   ├── config.yaml        opções gerais
│   └── characters.json    decisão por personagem
├── output/                análise, relatórios e capítulos finais
└── cache/                 etapas reutilizáveis e retomada
```

Para o audiobook dividido, mantenha um arquivo por capítulo:

```text
input/
├── Chapter 01.mp3
├── Chapter 02.mp3
├── Chapter 03.mp3
└── Chapter 10.mp3
```

O programa usa ordenação natural, portanto `Chapter 2` fica antes de `Chapter 10`. Ele processa e armazena cache separadamente para cada arquivo. Não junta os capítulos.

A saída conserva a divisão e os nomes:

```text
output/
├── Chapter 01 Enhanced.mp3
├── Chapter 02 Enhanced.mp3
├── Chapter 03 Enhanced.mp3
└── Chapter 10 Enhanced.mp3
```

Os arquivos fora das janelas convertidas preservam o conteúdo original; os metadados são copiados quando o formato permite. Se um capítulo não tiver nenhuma fala elegível, ele continua sendo emitido individualmente.

`input/`, `books/`, `voices/`, `output/`, `cache/` e `models/` não são enviados ao GitHub. Isso evita publicar audiobooks, livros, vozes, modelos e resultados.

## EPUB ou TXT?

Use o EPUB quando ele for da mesma tradução/edição narrada. Ele preserva capítulos, parágrafos, aspas e travessões, que ajudam a separar diálogo de narração.

Use TXT como alternativa quando ele corresponder melhor às palavras efetivamente narradas ou quando o EPUB for de outra edição. O sistema aceita somente um `--book-text` por execução; se houver dúvida, analise cada opção separadamente e compare `alignment_success_rate` em `output/report.json`.

Para os dois arquivos “O Sangue dos Elfos” encontrados em Downloads, o EPUB é a primeira escolha. Os conteúdos são quase iguais, mas o EPUB possui 7 capítulos e mais de 3 mil parágrafos estruturados. O TXT tem quebras de linha artificiais, nenhum espaçamento entre parágrafos e hífens simples. Ele também é aceito: o leitor agora detecta seu encoding Windows-1252.

Coloque o escolhido em:

```text
books/O Sangue dos Elfos.epub
```

## Configurar personagens

Liste a configuração:

```bat
run.bat character list
```

Modos:

- `original`: identifica e relata, mas sempre preserva;
- `convert`: converte quando referência e confianças são válidas;
- `auto`: conservador e original por padrão;
- `ignore`: preserva sem processamento adicional específico.

Exemplos para qualquer personagem, independentemente de gênero, idade ou espécie:

```bat
run.bat character add "Vesemir" --mode convert --voice voices/vesemir_ref.wav
run.bat character set "Geralt" --mode original
run.bat character set "Yennefer" --mode convert --voice voices/yennefer_ref.wav
```

O narrador fica protegido por `"__narrator__": {"mode": "original"}`. Não altere isso no primeiro processamento.

## Referências de voz

Use WAV com uma única pessoa, fala clara, pouco ruído ou eco, sem música e sem outras vozes:

```text
voices/
├── yennefer_ref.wav
├── triss_ref.wav
└── ciri_ref.wav
```

O nome pode ser diferente, desde que `voice_reference` aponte para ele. Personagens `original` e `ignore` não precisam de referência.

## Sequência recomendada

Abra um novo terminal na pasta do projeto para que o FFmpeg instalado esteja no `PATH`.

Para usar sem comandos, dê dois cliques em:

```text
ABRIR_INTERFACE.bat
```

Na aba **Processamento**, escolha a pasta `input`, o EPUB e a saída. Na aba **Personagens e vozes**, configure os modos e importe referências. Na aba **Configurações**, ajuste modelo, GPU, limites, formato e LLM.

### 1. Conferir o computador

```bat
check_gpu.bat
```

Espere ver CUDA, RTX 5060 Ti, PyTorch CUDA e FFmpeg disponíveis.

### 2. Teste rápido

```bat
run.bat analyze input --book-text "books/O Sangue dos Elfos.epub" --model tiny --language pt
```

`tiny` verifica a instalação, mas não deve ser usado para aprovar a análise final.

### 3. Análise de qualidade

```bat
run.bat analyze input --book-text "books/O Sangue dos Elfos.epub" --language pt
```

Sem `--model`, o padrão é `large-v3`, que prioriza precisão. O primeiro uso baixa os pesos.

### 4. Revisar

Abra `output/report.html`, `output/analysis.json` e `output/report.json`. Confira falantes, timestamps, `skip_reason`, confidências, personagens preservados e plano de conversão.

### 5. Dry run

```bat
run.bat process input --book-text "books/O Sangue dos Elfos.epub" --language pt --dry-run
```

Isso valida o plano sem criar áudio alterado.

### 6. Processar todos os capítulos

```bat
run.bat process input --book-text "books/O Sangue dos Elfos.epub" --language pt
```

Uma única execução percorre todos os MP3s e cria um MP3 Enhanced para cada capítulo.

## Retomar após interrupção

Execute o mesmo comando novamente. Transcrições, alinhamentos, chamadas de LLM e conversões concluídas são reaproveitados. Cada capítulo tem cache independente.

## LLM opcional

O LLM só resolve ambiguidades contextuais. Atualmente `model` está vazio em `config/config.yaml`, portanto nenhuma chamada ocorre. Sem LLM o pipeline funciona, mas preserva mais falas ambíguas.

Para Ollama local:

```yaml
llm:
  enabled: true
  provider: ollama
  base_url: http://localhost:11434
  model: nome-do-modelo
```

## Interface gráfica

A interface gráfica é iniciada por `ABRIR_INTERFACE.bat` e possui tema preto com azul-escuro. Ela oferece:

- seleção da pasta de capítulos, livro e saída;
- botões Analisar, Dry run, Processar e Cancelar;
- painel de logs e atalhos para saída/relatório;
- cadastro, alteração e exclusão de personagens;
- inclusão automática dos personagens encontrados após a análise, sempre em modo `original`;
- marcação `Revisar` quando nenhuma atribuição do personagem atingir a confiança mínima;
- importação de uma referência de áudio, convertida automaticamente para WAV;
- indicador de referência existente ou ausente;
- edição das principais configurações de transcrição, confiança, voice conversion, saída e LLM;
- banco local de vozes com diarização, amostras por falante e corte automático da referência;
- diagnóstico da GPU.

Durante a análise, a barra e o log mostram o capítulo atual, a porcentagem geral e quanto tempo de áudio daquele capítulo já foi transcrito. Ao importar uma voz para um personagem, a interface salva a referência e muda seu modo para `convert` automaticamente.

Na lista de capítulos, dê dois cliques em um arquivo para incluí-lo ou ignorá-lo. O botão **Estimativa** calcula duração, espaço de saída e uma faixa aproximada de tempo. Cada capítulo concluído recebe um checkpoint; se houver interrupção, uma nova execução com os mesmos arquivos e configurações retoma do capítulo seguinte.

Use a aba **Prévia A/B** para escolher capítulo, personagem, ponto inicial e duração. **Gerar prévia** cria duas amostras de mesma duração; use **Ouvir original** e **Ouvir convertido** para comparar. Na aba de personagens, **Ouvir** reproduz diretamente a referência escolhida.

Na aba **BANCO DE VOZ**, selecione um áudio com uma ou mais pessoas, escolha o intervalo e deixe a quantidade de vozes em `Automático` ou informe o total esperado. Depois da análise, ouça cada grupo, informe o nome e use **Cortar e salvar voz**. O aplicativo combina até 25 segundos dos trechos mais limpos, grava a referência em `voices/` e configura o personagem em modo `convert`. Execute `setup_seedvc.bat` antes do primeiro uso e evite música, eco ou falas simultâneas.

O campo **Aliases** aceita nomes separados por vírgula, como `Lobo Branco, bruxo`. Quando o livro usar um desses nomes em uma atribuição de fala, ele será associado ao personagem principal.

A interface chama o mesmo pipeline da CLI, portanto mantém cache, retomada, segurança e um arquivo de saída por capítulo.

## Problemas comuns

- **Referência não encontrada:** coloque o WAV em `voices/` ou mude o personagem para `original`.
- **Alinhamento baixo:** confirme tradução/edição, teste o outro texto e compare o relatório.
- **CUDA indisponível:** execute `check_gpu.bat` e, se necessário, `setup.bat`.
- **Modelo demora para iniciar:** a primeira execução está baixando pesos; as seguintes usam cache.
- **Poucas falas convertidas:** isso é intencional quando identificação ou alinhamento não atingem os limites de segurança.
