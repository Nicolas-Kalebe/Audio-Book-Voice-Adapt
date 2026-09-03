# Decisões técnicas

Pesquisa revisada em 3 de setembro de 2026.

## Transcrição e alinhamento

- **faster-whisper** é o backend principal: é programático, oferece timestamps por palavra, usa CTranslate2 e decodifica por PyAV. O projeto usa `large-v3`, beam search e FP16 na GPU por padrão.
- **WhisperX** continua sendo uma boa opção para alinhamento fonêmico, mas adiciona uma pilha PyTorch/torchaudio e modelos de idioma. O pipeline atual evita essa dependência rígida e alinha o texto editorial aos timestamps por palavra do ASR com correspondência monotônica e fuzzy. Uma futura implementação WhisperX cabe atrás da mesma fase de transcrição.
- A diarização não é usada para decidir personagem: há um único ator interpretando múltiplos papéis.

## Voice conversion

| Backend | Escolha | Motivo |
|---|---|---|
| Seed-VC | padrão | VC zero-shot real; referência de 1–30 s; preserva o sinal-fonte e fornece CLI; modelo offline para fala. |
| OpenVoice V2 | adaptador/alternativa | zero-shot e licença MIT, mas o fluxo de referência oficial é mais voltado à clonagem de timbre acoplada a TTS e exige checkpoints/extrator próprios. |
| RVC | adaptador/alternativa treinada | CLI robusta, mas requer modelo treinado (o projeto recomenda ao menos 10 min de fala limpa); não atende ao requisito principal de referência curta sem treino. |

O Seed-VC é GPL-3.0 e é instalado como projeto externo em `models/seed-vc`; este repositório não redistribui seu código nem seus pesos. O adaptador chama sua CLI oficial. O ambiente separado em Python 3.10 reduz conflitos com a aplicação. Em setembro de 2026, o arquivo oficial mistura índices nightly CUDA 12.6 com pins PyTorch 2.4; o instalador filtra apenas essas três linhas e instala o trio oficial PyTorch 2.11/CUDA 13.0 para obter suporte Blackwell, mantendo as demais versões do upstream.

No Windows, a dependência transitiva `webrtcvad` tenta compilar C e exige Visual Studio Build Tools. O setup usa `webrtcvad-wheels`, fork que fornece o mesmo módulo/API com wheels CPython 3.10 para Windows, e instala `resemblyzer` sem repetir a dependência obsoleta.

## GPU e compatibilidade

A RTX 5060 Ti é Blackwell. PyTorch ganhou suporte Blackwell em 2.7 com wheels CUDA 12.8 e as versões atuais recomendam wheels CUDA 13.0+ para GPUs novas. O driver local 616.56 suporta CUDA até 13.4, portanto o setup instala o wheel `cu130`. CTranslate2/faster-whisper 4.8 ainda procura `cublas64_12.dll`; por isso o ambiente instala os wheels NVIDIA cuBLAS 12 e cuDNN 9 lado a lado e expõe seus diretórios de DLL. Drivers NVIDIA novos executam runtimes CUDA antigos por compatibilidade retroativa. O diagnóstico confirma o backend efetivo em vez de confiar no número mostrado pelo `nvidia-smi`.

## Segurança do processamento

A seleção é opt-in por `mode`, sem distinção de gênero, idade, espécie ou importância. O pipeline só converte se personagem, referência, duração e scores satisfizerem todos os limites. `original` e `ignore` sempre preservam; `auto` preserva por padrão até ser explicitamente habilitado globalmente. Exceções no VC são registradas e preservam o áudio original. O relatório permite auditar cada janela. A reconstrução silencia somente a janela com padding e mistura um WAV de mesma duração, normalizado por RMS limitado e com fades adaptativos.

## Limitações conhecidas

- Texto literário e áudio podem divergir substancialmente; blocos com baixa confiança nunca são convertidos.
- Fala sem aspas/travessão e sem atribuição explícita é deliberadamente subdetectada sem LLM.
- OpenVoice não tem execução automática neste release porque sua API oficial não expõe uma CLI genérica de VC fonte→referência equivalente à do Seed-VC.
- A primeira execução baixa vários gigabytes de modelos. Testes unitários não validam qualidade perceptual dos pesos; uma referência e um audiobook reais continuam necessários para essa avaliação.
