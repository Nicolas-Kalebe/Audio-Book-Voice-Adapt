# Preferências persistentes do proprietário

- Trabalhamos em turnos escolhidos pelo usuário: modelo de testes para executar
  benchmarks, coletar logs e analisar resultados; modelo mais capaz para código,
  arquitetura e propostas de melhoria. Ao precisar implementar durante um turno
  de testes, pause e peça a troca de modelo. A confirmação de troca pelo usuário
  autoriza a implementação combinada.
- No turno de implementação, execute as verificações técnicas necessárias, mas
  deixe a campanha comparativa com Qwen para o turno de testes, salvo pedido explícito.
- O usuário prefere resultados finais, sem narração contínua. Comunique erros ou
  esclarecimentos necessários e respeite instruções de comunicação de prioridade superior.
- O produto é de uso geral. Não codifique nomes, regras ou respostas específicas
  do livro usado para desenvolvimento dentro do motor.
- Preserve o app principal em execução e config/characters.json do usuário.
  Trabalhe na worktree de desenvolvimento. Mantenha livros, áudios, vozes e
  relatórios com texto literário fora do Git. O repositório segue privado.
- O gabarito da Parte 01 é regressão de desenvolvimento, não teste independente.
  Não afirme que os pesos do Qwen foram treinados por ajustar regras ou prompts.
- Prioridade **revista pelo proprietário em 08/09/2026**: *"é melhor que não mude
  uma voz se não tem certeza, deixe sem atribuição"* e *"figurante de uma cena só
  não precisa de voz"*. Isto substitui a regra anterior, que mandava contar
  omissões como erro e proibia filtros de conversão.
  - Abstenção é a **saída segura**, não erro: o turno mantém a voz do narrador.
    O único defeito que conta é **voz trocada errada**.
  - Figurante — descrição anônima que aparece numa cena só — não ganha voz.
    Esses turnos saem do denominador que decide o produto (`by_class.dublavel`),
    continuam visíveis para auditoria e nunca são escondidos.
  - A meta virou um **par**, e os dois lados valem juntos, porque precisão alta
    com cobertura baixa é abster em tudo: é a mesma trava que a proibição de
    filtros exercia antes. Números definidos pelo proprietário em 08/09/2026
    (*"pode colocar nossa meta de tudo em 95%"*): **precisão ≥95% e cobertura
    ≥95%, ambas sobre os turnos dubláveis.**
  - Na Parte 01 isso são 213 dubláveis, dos quais 5 não têm áudio. A cobertura de
    95% exige 203 atribuídos contra um teto de 208: **sobram 5 abstenções e 10
    vozes trocadas erradas**. A trava mais apertada é a cobertura, não a precisão
    — abster para não errar deixou de ser grátis.
  - Antes de qualquer campanha, rodar `scripts/gold_ceiling.py`: mede em 30s, sem
    GPU, se a meta é alcançável pelo gabarito. Cinco campanhas foram comparadas
    contra um teto de 81,57% sem que ninguém tivesse conferido.
  - Focar no reconhecimento antes de retomar desempenho/conversão. Não anunciar
    uso geral ou lançamento sem validar.
