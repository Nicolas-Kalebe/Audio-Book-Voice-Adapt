# Audio-Book-Voice-Adapt

Ferramenta local para detectar falas em audiobooks e aplicar **voice conversion somente a personagens explicitamente habilitados**, preservando a narração e qualquer trecho incerto.

> Estado: pipeline funcional e conservador. A qualidade final depende dos modelos Seed-VC, das referências de voz, da fidelidade do texto do livro e do áudio de entrada. Leia [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) para escolhas e limitações.

Para um roteiro direto, incluindo onde colocar cada arquivo, consulte [GUIA_DE_USO.md](GUIA_DE_USO.md).

## Requisitos

- Windows 11, Python 3.11 para a aplicação e Python 3.10 para Seed-VC
- NVIDIA recente e driver atualizado (CPU funciona, mas é muito lento)
- FFmpeg/FFprobe no `PATH`
- Aproximadamente 15–25 GB livres para ambientes e modelos

## Instalação

No Prompt de Comando:

```bat
setup.bat
setup_seedvc.bat
check_gpu.bat
```

`setup.bat` cria `.venv`, instala PyTorch CUDA 13.0, faster-whisper e as bibliotecas CUDA 12/cuDNN 9 exigidas pelo CTranslate2 lado a lado. Se FFmpeg estiver ausente e `winget` existir, tenta instalar `Gyan.FFmpeg`. Reabra o terminal após a instalação do FFmpeg.

`setup_seedvc.bat` clona o projeto oficial em `models/seed-vc` e usa um ambiente Python 3.10 separado. Como os pins PyTorch 2.4/CUDA 12.6 do upstream antecedem Blackwell, o script substitui somente o trio PyTorch pelo wheel oficial 2.11/CUDA 13.0. Os pesos são baixados pelo próprio Seed-VC no primeiro segmento convertido.

Para instalar Python 3.10, se necessário:

```bat
winget install Python.Python.3.10
```

## Preparação

1. Coloque um arquivo ou capítulos em `input/`. MP3, M4A, FLAC, WAV, OPUS, OGG e AAC são aceitos.
2. Coloque referências WAV limpas, de preferência de 10–30 segundos, em `voices/`.
3. Edite `config/characters.json`. Só personagens em `mode: convert` (ou `auto` explicitamente habilitado) e com referência existente são elegíveis.
4. Opcionalmente, forneça o livro em TXT, EPUB, SRT ou JSON. Isso melhora substancialmente a detecção estrutural e a atribuição.

Você é responsável por obter consentimento e direitos para as vozes e obras utilizadas. Não use o software para personificação enganosa ou fraude.

## Uso

Ative o ambiente ou use `run.bat`:

Interface gráfica no Windows (dê dois cliques):

```bat
ABRIR_INTERFACE.bat
```

Ela permite escolher capítulos/livro/saída, importar automaticamente os personagens encontrados, escolher suas vozes, alterar configurações e acompanhar capítulo, tempo e porcentagem sem digitar comandos.

Também inclui seleção individual de capítulos, aliases de personagens, estimativa de tempo/espaço, checkpoints retomáveis e prévias original/convertida para comparação A/B.

### Banco de voz

A aba **BANCO DE VOZ** recebe WAV, MP3, M4A, FLAC, Opus, OGG ou AAC e faz diarização local:

1. selecione o áudio e o intervalo a analisar (10 segundos a 1 hora);
2. deixe a quantidade de vozes em `Automático` ou informe quantas pessoas existem;
3. clique em **Reconhecer e separar vozes**;
4. ouça a amostra de cada grupo e informe o nome do personagem;
5. clique em **Cortar e salvar voz**.

O app escolhe os trechos mais limpos, monta até 25 segundos de referência em `voices/`, atualiza
`config/characters.json` e habilita o personagem para conversão. A diarização usa Resemblyzer no
ambiente local do Seed-VC; execute `setup_seedvc.bat` antes do primeiro uso. Falas simultâneas e música
de fundo não podem ser isoladas perfeitamente e devem ser evitadas.

```bat
.venv\Scripts\activate
python main.py analyze input --book-text livro.txt
python main.py process input --book-text livro.txt --dry-run
python main.py process input --book-text livro.txt
```

Idioma explícito e configuração alternativa:

```bat
python main.py analyze input\Chapter 01.mp3 --language pt
python main.py process input --config config\config.yaml --characters config\characters.json
python main.py analyze input\amostra.wav --model tiny --device cuda
```

`analyze` e `--dry-run` não criam áudio alterado; ambos geram `output/analysis.json`, `report.json` e `report.html`. `process` cria arquivos como `Chapter 01 Enhanced.mp3`.

## Regra de decisão

Um trecho só é convertido quando todas estas condições são verdadeiras:

1. o falante foi identificado e existe em `characters.json`;
2. o `mode` resolve para conversão e a referência existe;
3. confiança do falante atinge `speaker_confidence_threshold`;
4. com livro, alinhamento atinge `alignment_confidence_threshold`;
5. a duração mínima é atingida;
6. não é interjeição/som curto inseguro.

Se qualquer condição falhar ou o backend lançar erro, o original permanece. Não há decisão baseada apenas em uma voz “soar feminina”.

## Configuração

As opções documentadas ficam em `config/config.yaml`:

- `device`: `auto`, `cuda` ou `cpu`;
- `transcription.model`: modelo faster-whisper; `large-v3` prioriza precisão;
- `speaker_confidence_threshold` e `alignment_confidence_threshold`: limites de segurança;
- `padding_ms` e `crossfade`: integração de bordas;
- `minimum_segment_duration`: duração mínima global; pode ser sobrescrita por personagem;
- `voice_conversion.backend`: `auto`, `seedvc`, `openvoice` ou `rvc`;
- `output.format`/`bitrate`: MP3, M4A, FLAC, WAV, OPUS ou OGG;
- `llm`: Ollama local ou endpoint OpenAI-compatible. Deixe `model: ""` para não chamar LLM.

### LLM local com Ollama

```yaml
llm:
  enabled: true
  provider: ollama
  base_url: http://localhost:11434
  model: seu-modelo-local
```

Para API compatível, use `provider: openai-compatible`, uma `base_url` terminada antes de `/chat/completions`, e defina a variável indicada por `api_key_env`. Respostas são cacheadas pelo hash de todo o contexto.

## Personagens e referências

Exemplo mínimo:

```json
{
  "Ana": {
    "gender": "female",
    "age_group": "adult",
    "voice_reference": "voices/ana.wav",
    "mode": "convert",
    "pitch_shift": 0
  },
  "Carlos": {"gender": "male", "mode": "original"}
}
```

Compartilhar uma referência gera aviso quando `allow_shared_voice_references: true`; se falso, a configuração é rejeitada. `pitch_shift` é apenas complementar, não o mecanismo principal de identidade.

Os modos são `original` (preservar), `convert` (converter), `auto` (conservador; preserva por padrão) e `ignore` (preservar sem trabalho específico). Gênero, idade, espécie e pitch são metadados e nunca autorizam conversão. `__narrator__` é `original` por padrão.

Gerenciamento pela CLI:

```bat
python main.py character add "Vesemir" --mode convert --voice voices/vesemir_ref.wav
python main.py character set "Geralt" --mode original
python main.py character list
```

## Cache e retomada

Cada fase usa hashes do arquivo, configuração e dependências da etapa. Reexecutar reaproveita transcrição, alinhamento, detecção, LLM e conversões concluídas em `cache/`. Mudanças relevantes geram novas chaves automaticamente. Para invalidar tudo, mova a pasta `cache` para outro local; não edite arquivos de cache à mão.

## GPU e solução de problemas

Execute `check_gpu.bat`. Três estados são independentes: o driver pode detectar a GPU, PyTorch pode ou não ter CUDA, e CTranslate2 pode ou não carregar cuBLAS/cuDNN.

- `PyTorch CUDA: DISABLED`: recrie `.venv` pelo setup e confirme driver NVIDIA atual.
- erro `cublas64_12.dll`/`cudnn_ops64_9.dll`: confirme o wheel CUDA do PyTorch; o programa expõe automaticamente sua pasta `torch/lib` ao CTranslate2.
- memória insuficiente: troque `large-v3` por `medium` ou `distil-large-v3` e reduza processos concorrentes.
- `FFmpeg missing`: execute `winget install Gyan.FFmpeg`, reabra o terminal e repita o diagnóstico.
- RTX 50: use wheels CUDA 13.0 atuais; wheels antigos sem `sm_120` podem falhar.

## Backends de voice conversion

`auto` escolhe o primeiro backend instalado, priorizando Seed-VC. Ele é zero-shot e recebe diretamente áudio-fonte e referência. OpenVoice fica exposto como adaptador, mas não é executado automaticamente neste release devido ao fluxo/checkpoints específicos. RVC funciona apenas se `voice_model` apontar para um `.pth` treinado; uma referência curta não basta.

## Testes

```bat
.venv\Scripts\python -m pytest
```

Os testes cobrem configuração, referências compartilhadas, cache, alinhamento, segmentação em nível de palavra, elegibilidade, ordenação de capítulos e preservação byte a byte quando não há substituições. Um teste FFmpeg é executado quando as ferramentas estão instaladas.

## Saídas e auditoria

`report.json` inclui duração, segmentos, falantes, conversões, pulos, erros, GPU, backends, hits de cache e taxa de alinhamento. `report.html` contém os mesmos dados legíveis. Cada fala registra timestamps, scores, motivo, elegibilidade e ação.

## Licenças de terceiros

Este projeto é MIT. Seed-VC é GPL-3.0 e permanece uma instalação externa; faster-whisper, PyTorch, FFmpeg e modelos possuem suas próprias licenças. Confira-as antes de distribuir resultados ou empacotar dependências.
