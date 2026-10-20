# Audio-Book-Voice-Adapt

> **⚠️ Projeto abandonado até segunda ordem (20/10/2026).** Não há manutenção nem suporte.

Ferramenta local para trocar, num audiobook narrado por uma só pessoa, a voz das falas de
personagens escolhidas, mantendo a narração original.

## Por que parou

- **Resolvido:** saber quem fala cada fala (protocolo `frontier`, com Claude Fable 5.1: nenhuma
  voz trocada errada nas Partes 01–03 de desenvolvimento) e onde ela começa e termina no áudio
  (alinhamento forçado do texto do livro).
- **Não resolvido:** a voz convertida não soa natural. O narrador é homem (~151 Hz) e interpreta
  personagens femininas e infantis; Seed-VC (22 kHz e 44 kHz com controle de tom) e RVC treinado
  soaram artificiais de ouvido. TTS foi descartado pelo mesmo motivo.

O projeto só volta se surgir conversão de voz local que soe natural nesse caso.

## O que foi tentado e não deu certo

| Quando | Tentativa | Resultado |
|---|---|---|
| 03/09 | Whisper + regex "disse Fulano" + Seed-VC | Só acertava falas com indicação explícita |
| 04–11/09 | Qwen 3 8B local com regras de coerência, memória, roteador híbrido | Bom no desenvolvimento, reprovou nos holdouts (~90%) |
| 18/10 | Claude Fable 5.1 (`frontier`) | Funcionou para atribuição |
| 19/10 | Corte por busca na transcrição | Cortava no meio da frase; trocado por alinhamento forçado |
| 19–20/10 | Seed-VC sem treino, depois com controle de tom | Voz "muito IA" |
| 20/10 | RVC treinado (52 min de voz em domínio público) | Também artificial; fim das tentativas |

Detalhes, números e cada decisão: [RODAR.md](RODAR.md) e [docs/](docs/).
