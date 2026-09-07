# Revisão do motor para uso geral — 6 de setembro de 2026

## Decisão

Manter a arquitetura híbrida. O texto é a fonte principal para descobrir quem
fala; o áudio é a fonte dos horários e da interpretação original. A voz do
narrador não distingue necessariamente personagens. Não usar reconhecimento de
timbre como árbitro de identidade ficcional.

O problema não se resolve só trocando o modelo ou alongando o prompt. Atualmente
misturamos detecção de diálogo, identidade do falante e localização no áudio.
Também usamos confiança declarada pelo modelo como se fosse evidência medida.
Precisamos separar essas decisões e poder investigar cada perda.

Arquitetura-alvo (implementação incremental):

```text
Livro → inventário textual → cenas, entidades e atribuição textual
                ↓                          ↓
Áudio → ASR → alinhamento por palavras → decisão de conversão
                                           ↓
                                recorte original → conversão → remontagem
```

Cada fala deverá carregar ID textual, offsets, personagem ou abstenção, evidência
de atribuição, intervalo de áudio e método de alinhamento. Evidência de identidade
não deve ser confundida com qualidade dos horários.

## O que esta revisão implementa

- Inventário de candidatos textuais criado antes da transcrição; a cobertura é
  anexada a cada arquivo no JSON e no HTML. Falas não localizadas continuam visíveis.
  Ainda não há uma tela dedicada para navegar nesse inventário.
- Recuperação de falas de 1–4 palavras com correspondência exata entre âncoras
  textuais dos dois lados. Âncoras podem atravessar segmentos ASR. O intervalo
  deve estar em ordem, na mesma cena, com distância máxima de 12 segundos.
  Repetições ambíguas, disputas pelo mesmo intervalo e âncoras ausentes causam
  abstenção. O detector recebe apenas as palavras recuperadas para esse recorte.
- Descrições diferentes de pessoas com a mesma profissão não são fundidas por
  escolher a descrição mais longa. Pessoa nova/descritiva não herda automaticamente
  o personagem nomeado que exerce a mesma profissão.
- Segunda leitura do LLM sem receber a primeira proposta nem o palpite anterior
  do alvo. Consenso não reduz o limiar automático; confiança não finita ou fora
  da faixa não é aceita. IDs duplicados se tornam abstenções, não “último vence”.
- Cache do LLM inclui instruções, esquema, tipo de provedor e endpoint. Checkpoints
  também consideram essa identidade. Cache de detecção inclui a identidade do livro.
- Contagem de turnos separada por arquivo: IDs locais iguais em capítulos distintos
  não apagam falas das estatísticas.
- Regressões sintéticas com nomes inventados, repetições, profissões iguais,
  continuação EPUB, aspas ambíguas e falhas de resposta do LLM.

Isso é a fundação do motor orientado pelo livro, não a migração completa: a IA
ainda revisa os turnos já localizados no áudio. Candidatos sem horário ainda não
participam da atribuição contextual. A separação completa é a próxima etapa.

## Resultado medido, com limites explícitos

Reprocessamento determinístico da Parte 01, com os mesmos caches de transcrição
e alinhamento e sem aliases configurados, overrides, Qwen ou conversão de voz:

| Medida | v25 | Esta revisão |
|---|---:|---:|
| Turnos encontrados no gabarito | 251/255 | 253/255 |
| Turnos perdidos | 4 | 2 |
| Falante correto, contando omissões | 129/255 (50,59%) | 139/255 (54,51%) |
| Precisão entre atribuições emitidas | 83,77% | 84,76% |

Recuperadas P170 e P204. P38 e P291 permanecem sem localização. Os novos turnos
também ajudam a sequência contextual, daí o ganho de atribuições ser maior que
o número de falas recuperadas. O replay novo levou **0,733 s** para inventário,
detecção e cobertura; leitura de arquivos, avaliação, ASR e LLM estão fora desse
tempo. Não é tempo de análise completa de um audiobook.

O inventário encontrou 412 candidatos/fragmentos no intervalo P0–P369 e localizou
409; isso não significa 99% de acurácia de falante. Inclui fragmentos de uma mesma
fala e aspas que podem ser pensamentos. O denominador do gabarito é 255 turnos,
não 412 candidatos. Os horários novos ainda exigem escuta para auditoria acústica.

Os 167/255 da rodada histórica com Qwen não são comparáveis ao replay sem Qwen.
Não foi executada nova rodada completa do Qwen nesta revisão; seus testes aqui
usam provedores simulados para validar o protocolo, não a qualidade do modelo.

### Como reproduzir o replay

`scripts/replay_cached_detection.py` recebe `--transcription`, `--alignment`,
`--book`, `--output`, opcionalmente `--aliases` (JSON alias→nome) e `--gold`.
Selecionar caches correspondentes à mesma execução; o script não adivinha o par.
Não executa ASR/LLM, não altera caches e recusa sobrescrever relatório existente.
Os resultados locais desta revisão estão em `output/v27-audit/` na worktree.

## Métricas que precisamos para chegar a 95%

O antigo `test_locked` foi consultado durante ajustes. Todo o conjunto da Parte
01 agora é regressão de desenvolvimento. Seu gabarito foi feito pelo assistente,
teve correções e ainda não recebeu auditoria independente. Nenhum número dele
comprova desempenho em livros novos. “Treino” até agora foi ajuste de regras e
prompts: os pesos do Qwen não foram treinados.

Para uma meta publicável:

1. Congelar versões do parser, modelo, prompts, gabarito e parâmetros antes do teste.
2. Separar por **livro**, não apenas por cena. Livros de teste não podem ser lidos
   para ajustar o motor. Se forem consultados, passam a desenvolvimento e precisam
   ser substituídos por outro teste intocado.
3. Anotar narrador, fala, pensamento/citação e entidade, além dos trechos ausentes
   da transcrição. Nomes ambíguos devem admitir abstenção ou alternativas justificadas.
4. Medir detecção, falante correto ponta a ponta, precisão entre aceitas, cobertura,
   cortes acústicos e resultados por personagem/livro/estilo. Omissões e abstenções
   entram como perdas no resultado ponta a ponta.
5. Auditar uma amostra por outro revisor e ouvir os cortes. Publicar tamanho da
   amostra, incerteza e desempenho por livro; não só uma média que esconda minorias.
6. Comparar uma mudança por vez com a mesma entrada; separar tempos a frio e com cache.

Testes sintéticos passam ou falham em propriedades específicas; não estimam a
acurácia em literatura real. Tampouco duas respostas do mesmo modelo são revisores
estatisticamente independentes.

## Alternativas e próxima prioridade

**Motor textual de entidades e cenas:** é o maior investimento recomendado.
Criar IDs de entidade separados dos nomes exibidos; registrar aliases, descrições
e evidências locais de correferência. Atribuir todos os turnos do inventário antes
de alinhá-los, levando todas as partes de uma fala ao contexto do LLM. Limitar
contexto por cena e orçamento; nunca pressupor que uma profissão significa uma
pessoa. Aplicar restrições explícitas e revisão dos casos contraditórios.

**BookNLP como referência ou adaptador de inglês:** sua organização separa entidades,
correferência e atribuição de citações, compatível com essa direção. A implementação
documentada é para livros em inglês; não é solução pronta para português.
[Documentação oficial do BookNLP](https://github.com/booknlp/booknlp).

**Alinhamento forçado nos trechos problemáticos:** ferramentas como WhisperX
oferecem alinhamento de palavras com modelos específicos por idioma. Vale testar
como backend opcional, sobretudo para pausas, falas curtas e cortes ruins. Isso
resolve localização, não quem é o personagem. A integração precisa verificar
compatibilidade de idioma, edição textual e dependências; não foi instalada nesta
revisão. [Documentação oficial do WhisperX](https://github.com/m-bain/whisperX).

**Modelo textual maior ou especializado:** comparar o Qwen atual com candidatos
sobre o mesmo conjunto congelado antes de trocar. Mais parâmetros não corrigem
gabarito contaminado, identidade mal representada ou corte errado. Ajuste fino só
depois de haver exemplos diversos, direitos de uso e validação independente.

**Ressintetizar o livro inteiro:** simplifica algumas decisões de duração, mas perde
a interpretação original do narrador e muda o produto. Não é a opção adotada.

## Antes da publicação

Manter livros, MP3, referências de voz e relatórios com trechos literários fora
do Git. Usar textos próprios/licenciados em testes públicos. Conferir licenças
de modelos e consentimento para vozes, dependências opcionais, instalação limpa
e comportamento sem GPU. O repositório continua privado; publicação exige decisão
expressa do proprietário.

O parser atual privilegia travessões e aspas duplas e as regras são principalmente
em português. Não anunciar suporte irrestrito a idiomas, estilos ou edições. A
worktree de desenvolvimento fica isolada em `output/dev-worktree`; o programa
principal que já estava aberto não recebeu estas alterações.
