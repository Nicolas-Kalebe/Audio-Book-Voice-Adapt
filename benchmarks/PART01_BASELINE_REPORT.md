# Baseline auditavel - Parte 01

## Resultado executivo

- Turnos falados no gabarito: **255**.
- Turnos encontrados: **250**; perdidos: **5**.
- Recall de deteccao: **98,04%**.
- Turnos encontrados por inteiro: **105/255 (41,18%)**; **145** possuem limites incompletos.
- Candidatos que eram pensamento ou texto escrito: **13**.
- Precisao da deteccao por turno: **95,06%**.
- Turnos com personagem atribuido: **186/250 (74,40%)**.
- Atribuicoes corretas: **143/250 (57,20%)**.
- Acuracia apenas entre respostas emitidas: **76,88%**.
- Acuracia ponta a ponta: **143/255 (56,08%)**.
- Personagem e limite da fala ambos corretos: **58/255 (22,75%)**.

A metrica principal e a acuracia ponta a ponta: omissoes e recusas contam como erro. Acuracia apenas
entre respostas emitidas pode parecer boa mesmo com baixa cobertura.

## Por personagem ou papel

| Personagem/papel | Corretas | Total | Recall |
|---|---:|---:|---:|
| Jaskier | 36 | 63 | 57,14% |
| Yennefer | 28 | 43 | 65,12% |
| Rience | 12 | 32 | 37,50% |
| Geralt | 14 | 16 | 87,50% |
| Sheldon Skaggs | 11 | 14 | 78,57% |
| Eskel | 8 | 10 | 80,00% |
| Elfo alto e louro | 0 | 9 | 0,00% |
| Vilibert | 7 | 7 | 100,00% |
| Ciri | 7 | 7 | 100,00% |
| Vera Loewenhaupt | 5 | 6 | 83,33% |
| Radcliffe de Oxenfurt | 5 | 5 | 100,00% |
| Donimir de Troy | 4 | 5 | 80,00% |
| Gnomo dos artigos metalicos | 0 | 5 | 0,00% |
| Cavaleiro de Cintra nao identificado | 0 | 4 | 0,00% |
| Guerreiro ruivo de Skellige | 0 | 4 | 0,00% |
| Rayla de Liria | 3 | 3 | 100,00% |
| Druida grisalho | 0 | 3 | 0,00% |
| Filhas de Vilibert | 0 | 3 | 0,00% |
| Sacerdote gordo | 0 | 3 | 0,00% |
| Bruxo nao identificado de Kaer Morhen | 1 | 2 | 50,00% |
| Elfa do gorro de arminho | 0 | 2 | 0,00% |
| Jovem aprendiz de artesao | 0 | 2 | 0,00% |
| Taberneiro | 0 | 2 | 0,00% |
| Campones anonimo | 0 | 1 | 0,00% |
| Membro anonimo da multidao | 0 | 1 | 0,00% |
| Vasemir | 1 | 1 | 100,00% |
| Capanga de Rience com lanterna | 0 | 1 | 0,00% |
| Mama Lantieri | 1 | 1 | 100,00% |

## Principais confusoes

| Esperado | Motor atual | Quantidade |
|---|---|---:|
| Jaskier | Sem atribuicao | 13 |
| Yennefer | Jaskier | 9 |
| Rience | Sem atribuicao | 8 |
| Rience | Jaskier | 8 |
| Jaskier | Rience | 6 |
| Yennefer | Sem atribuicao | 6 |
| Jaskier | Yennefer | 6 |
| Elfo alto e louro | Sem atribuicao | 5 |
| Cavaleiro de Cintra nao identificado | Sem atribuicao | 4 |
| Gnomo dos artigos metalicos | Sem atribuicao | 4 |
| Guerreiro ruivo de Skellige | Sem atribuicao | 4 |

## Falas inteiras perdidas

- P38 - Geralt: `Ciri!`
- P170 - Rience: `Sera?`
- P204 - Rience: `Sim?`
- P274 - Jaskier: `Ha. Diga-me, Yennefer, quando foi que voce viu Geralt pela ultima vez?`
- P291 - Jaskier: `Yennefer?`

## Leitura humana do resultado

O resultado atual e ruim para producao automatica. O motor parece mais correto quando se observa
somente aquilo que decidiu responder (76,88%), mas ele atribui personagem a apenas 74,40% dos turnos.
Quando omissoes e falas perdidas contam como erro, a acuracia real cai para 56,08%.

Existe um segundo problema, ainda mais grave para o audiobook: 143 falas possuem uma atribuicao
narrativa no meio, como `disse Jaskier`, seguida pela continuacao do dialogo. O detector atual para
nessa atribuicao e deixa o restante com a voz do narrador. Somando dois problemas especiais de limite,
somente 105 dos 255 turnos foram encontrados por inteiro. Exigindo simultaneamente personagem correto
e limite completo, o baseline e de apenas 22,75%.

O maior defeito nao esta concentrado em Geralt. Ele esta nas conversas longas: o motor troca Jaskier
por Rience durante o interrogatorio e troca Jaskier por Yennefer durante o dialogo na taverna. Isso
mostra que a inferencia de alternancia perdeu suas ancoras e propagou erros por varios turnos.

Ha tambem personagens anonimos que o texto identifica apenas pelo papel, como o druida, o sacerdote,
o gnomo e o elfo alto. Eles receberam rotulos de papel no gabarito. Em dois turnos finais, o livro diz
apenas que um dos bruxos presentes falou; o gabarito aceita Vasemir, Lambert ou Coen e nao inventa uma
identidade exata.

O relatorio possui quatro fragmentos audiveis que pertencem a turnos ja contados. Eles precisam herdar
a voz correta, mas nao inflam a quantidade de turnos. O candidato `249-0` mistura fala, narracao e
pensamento. O candidato `294-0` omite a continuacao que o EPUB colocou no paragrafo 295. Portanto,
tambem existe um problema de limite de corte alem da atribuicao do personagem.
