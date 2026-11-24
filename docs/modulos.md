# Módulos funcionais e interface

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 7. Módulos funcionais

Prioridades: **P0** = MVP obrigatório, **P1** = importante, **P2** = desejável.

### 7.1 Projetos e protocolo (P0)
- Projeto: título, pergunta, PICO/PECO estruturado, número PROSPERO (opcional), prazo (ex.: submissão do resumo), idioma dos relatórios.
- Critérios de inclusão/exclusão (lista editável), usados como checklist na triagem e no texto completo.
- **Desfechos**: nome, tipo (contínuo/dicotômico/tempo até evento — este último só P2), direção ("maior é melhor" ou "maior é pior"), momento(s) de medida, desfecho primário ou secundário.
- **Grupos de comparação** (ex.: "Cirurgia < 5 anos" × "Cirurgia ≥ 5 anos"), com a regra do ponto de corte e o que fazer quando o estudo usa outro corte (ver 7.7).
- **Plano de análise pré-definido** (medida de efeito, modelo, subgrupos e sensibilidades planejadas). Mudanças depois de ver os dados ficam marcadas como "não planejadas".
- **Emendas ao protocolo** (P1): registro de toda mudança com data, motivo e quem aprovou. Alimenta a seção de "desvios do protocolo" do relatório.
- **Painel do projeto**: progresso por etapa, pendências por membro, contagem de estudos em cada fase, contagem regressiva do prazo.

### 7.2 Importação, deduplicação e migração (P0 parcial)
- **(P0) Cadastro manual de estudos** e **importação de lista final** via CSV/XLSX, para projetos que já passaram da triagem.
- **(P0) Migração de projeto em andamento:** importar a tabela consolidada de risco de viés (CSV/XLSX no formato do robvis ou com mapeamento de colunas feito pelo usuário) e planilhas de extração. Tela de **mapeamento de colunas** com pré-visualização e relatório de erros por linha.
- **(P1)** Importar RIS, BibTeX, CSV e PubMed (`.nbib`), registrando base de origem, data e estratégia de busca.
- **(P1) Deduplicação multicritério** (lição L4):
  - DOI igual (normalizado) ou PMID igual = duplicata certa.
  - Duplicata provável exige **vários critérios juntos**: título completo normalizado (minúsculas, sem pontuação/acentos) com alta similaridade (`rapidfuzz`, comparando o título **inteiro**, não só o começo) + mesmo ano + primeiro autor compatível + revista/volume/páginas compatíveis quando existirem.
  - **Proteções contra falso positivo:** títulos que diferem em números, "Parte 1/Parte 2", "Errata", "Correção", "Comentário", "Resposta" ou "Retratação" **não** são marcados como duplicata; são marcados como "relacionados" (uma errata pode ser importante).
  - Cada par mostra **por que** foi marcado (critérios que bateram e pontuação) e os dois registros lado a lado.
  - Duplicatas prováveis nunca são removidas sem confirmação humana; a remoção é reversível e contada no PRISMA.
  - Relatório de deduplicação exportável (para o Métodos do artigo).
- **(P2)** Atualização de busca: nova importação marca só as referências novas.
- Todas as contagens alimentam o PRISMA.

### 7.3 Triagem de título/resumo (P1)
- Cartão com título, resumo, autores, ano e DOI; destaque de palavras-chave de inclusão (verde) e exclusão (vermelho), configuráveis.
- Decisão: Incluir / Excluir / Talvez, com atalhos de teclado e navegação rápida.
- Dupla triagem cega; conflitos vão para a fila de resolução.
- **Kappa de Cohen** entre dois revisores (Fleiss para três ou mais, P2), com explicação do que o número significa.
- Filtros: pendentes, em conflito, por revisor, por palavra-chave.
- **Desfazer** a última decisão (e histórico de decisões por referência) (lição L6).
- Marcador **"útil como referência"** para estudos excluídos que servem de contexto na Introdução/Discussão (lição L7).
- **Atribuição de lotes** de referências a revisores específicos (lição L9).
- **Mesmas opções de decisão em qualquer tamanho de tela** (lição L8).
- **(P1) Priorização por aprendizado de máquina** (sem LLM, local e gratuita): depois de algumas decisões dos revisores, reordena as referências pendentes pelas mais prováveis de inclusão (TF-IDF + modelo linear, estilo ASReview). **Nunca exclui nada sozinha**; só muda a ordem. Mostra quantas foram triadas e um aviso de que todas devem ser lidas, a menos que o protocolo defina critério de parada.

### 7.4 Texto completo e estudos (P0 parcial)
- **(P0)** Upload de PDF, visualizador embutido (PDF.js) com destaque e anotação, busca no texto.
- **(P1)** Exclusão no texto completo exige **motivo** de lista padronizada (população errada, desenho errado, sem grupo comparador, sem dados do desfecho, ponto de corte incompatível...). Os motivos alimentam o PRISMA. A lista é **editável pelo admin**: motivos sem uso podem ser removidos, e motivos em uso podem ser renomeados ou fundidos, com histórico (lição L5).
- **(P0) Estudo × relato:** vários artigos podem ser do mesmo estudo/coorte. O sistema agrupa relatos em um "estudo" e **bloqueia** a entrada do mesmo estudo duas vezes numa análise.
- **(P0)** Campo "desenho do estudo" (ECR, coorte prospectiva, coorte retrospectiva, caso-controle, transversal, série de casos...), usado para sugerir o instrumento de risco de viés.
- **(P1) Contato com autores:** registro de dados solicitados, data, resposta. Dados recebidos por contato ficam marcados com essa origem.

### 7.5 Extração de dados (P0)
- **Construtor de formulário** (texto, número, seleção, data, tabela) salvo em JSONB e **versionado**: mudar o formulário depois de dados inseridos cria nova versão e mostra o que precisa ser revisto.
- **Template padrão**:
  - Características: país, desenho, período, centros, n total, critérios de elegibilidade, financiamento, conflito de interesse.
  - Participantes por grupo: n, idade (média/mediana), sexo, diagnóstico, gravidade.
  - Intervenção/exposição por grupo: idade na cirurgia (corte usado pelo estudo), tipo de cirurgia, tempo de seguimento.
  - **Desfechos por grupo e por momento**, com formato conforme o tipo:
    - Contínuo: média e DP **ou** EP **ou** IC 95% **ou** mediana + IIQ/amplitude **ou** estatística t / valor p exato.
    - Valor final **ou** mudança desde a linha de base: campos separados. Se o artigo traz linha de base **e** final, os dois podem ser registrados, e o sistema explica qual usar (lição L11).
    - Dicotômico: eventos e total por grupo.
    - Efeito já calculado pelo artigo: efeito + IC/EP (ex.: OR ou HR ajustado), indicando se é **ajustado** e para quais variáveis; conversão automática para a escala log (lição L13).
  - Escala usada, faixa de valores e se "maior é melhor".
  - Página/tabela de origem + vínculo com o trecho anotado no PDF.
- **Estudos com mais de dois grupos** (ex.: < 2, 2–5, > 5 anos): registrar todos os grupos; a combinação em dois grupos é feita pela fórmula do Cochrane (8.5), nunca à mão.
- **Conversões automáticas** pelo serviço R (8.5), sempre mostrando valor original, valor convertido e método.
- **Dupla extração** com comparação campo a campo e destaque das divergências (detalhes em 7.5.1).
- **Salvamento automático** e indicador de "não salvo".

#### 7.5.1 Proteções contra erro de extração (P0 — prioridade máxima)
> Motivo: estudos metodológicos mostram que erros de extração (n, média, DP, sinal trocados, e principalmente DP confundido com EP) são comuns e podem anular ou inverter conclusões (lições L14 e L15). Este bloco é o maior diferencial do sistema.

Regras gerais: as checagens **avisam e pedem confirmação**, não bloqueiam (exceto erros impossíveis). Toda confirmação de um alerta exige justificativa curta e fica na auditoria. Os alertas aparecem no campo, no painel do estudo e na lista "Pendências de conferência" do projeto.

**A. Na digitação (frontend + backend)**
1. **Tipo de dispersão obrigatório:** ao digitar um número de dispersão, o extrator escolhe "DP", "EP", "IC 95%", "IIQ", "amplitude" ou "não informado", e marca **onde o artigo diz isso** (ex.: rodapé da Tabela 2). Sem isso, o campo não é confirmado.
2. **Erros impossíveis (bloqueiam):** DP ≤ 0, n ≤ 0, eventos > total, porcentagem > 100, IC com limite inferior maior que o superior, soma dos braços maior que o n total do estudo sem justificativa.
3. **Fora da escala:** média ou valor fora da faixa da escala informada (ex.: QI negativo); DP maior que metade da amplitude da escala → alerta.
4. **IC que não contém a média** → alerta.
5. **Trecho da fonte ao lado:** cada número tem vínculo com página/trecho do PDF; números sem fonte aparecem como "sem origem" na conferência final.

**B. Detector de EP no lugar de DP (serviço R, endpoint `/plausibility-checks`)**
6. Para estudos com a mesma escala/desfecho, compara o DP de cada estudo com o dos demais. Se o DP de um estudo for muito menor que o típico e próximo de "DP típico ÷ √n", alerta: "Este valor pode ser um EP. Confira no artigo."
7. Se o artigo também informa valor p ou IC da diferença, o serviço **recalcula** o p/IC a partir de média, DP e n e compara com o reportado. Diferença grande → alerta de dado inconsistente.
8. Os limiares exatos são parâmetros configuráveis e documentados; os valores padrão devem ser propostos pelo Claude Code com justificativa e aprovados antes do uso.

**C. Direção e sinal do efeito**
9. Para cada desfecho e estudo, o sistema escreve uma frase de conferência com os dados digitados, por exemplo: "No estudo Ballet 2025, o grupo < 5 anos teve média 92 e o grupo ≥ 5 anos teve 85 na escala X, em que maior é melhor. Isso favorece o grupo < 5 anos." O extrator confirma ou corrige.
10. Inversão de sinal para escalas "maior é pior" acontece em um único lugar (serviço R), nunca no formulário.

**D. Dupla extração e comparação**
11. Dupla extração obrigatória para campos numéricos de desfecho (configurável pelo admin; padrão ligado).
12. Comparação automática campo a campo, com tolerância só para formatação (vírgula/ponto, zeros à direita); qualquer diferença numérica real vira divergência.
13. Tela de divergências com os dois valores, as duas fontes no PDF e o valor de consenso.
14. Kappa/concordância da extração exibido ao final (indicador de qualidade do processo).

**E. Depois do cálculo do efeito (serviço R)**
15. **Diagnóstico de influência** (`influence()` do metafor) e efeitos muito distantes dos demais → alerta "confira os dados deste estudo antes de interpretar".
16. Efeito padronizado improvável em módulo (limiar configurável) → alerta.

**F. Conferência final antes de travar a extração**
17. Tela "Conferência final": para cada número usado em análise, mostra valor, tipo, origem no PDF, quem extraiu, quem conferiu e alertas pendentes. A etapa só trava com todos os alertas resolvidos ou justificados.

**G. Digitar uma vez (lição L12)**
18. Os dados de desfecho ficam em um só lugar (`outcome_data`). Análises, subgrupos, sensibilidades e exportações leem dali. Corrigir um número atualiza tudo e marca as análises antigas como "desatualizadas", com opção de rodar de novo.
- **(P2)** Digitalizador de gráficos estilo WebPlotDigitizer.
- **(P2)** IA sugere valores **sempre** com página e trecho citado; o campo fica marcado como "sugerido" até um humano confirmar.

### 7.6 Risco de viés (P0)

#### Instrumentos
| Instrumento | Uso | Respostas | Julgamento |
|---|---|---|---|
| **RoB 2** | Ensaios randomizados | Sim, Provavelmente sim, Provavelmente não, Não, Sem informação | Baixo / Algumas preocupações / Alto, por domínio e geral, **por resultado** |
| **ROBINS-I** | Intervenções em estudos não randomizados | Mesmas | Baixo / Moderado / Grave / Crítico / Sem informação, **por resultado** |
| **ROBINS-E** | Exposições em estudos observacionais | Mesmas | Conforme o instrumento |
| **JBI** (um checklist por desenho) | Coorte, caso-controle, transversal, série de casos, ECR... | Sim / Não / Incerto / Não se aplica | **Sem escore oficial**: regra definida pelo grupo e configurável por projeto |
| **Newcastle-Ottawa (NOS)** | Coorte e caso-controle | Estrelas por item (seleção, comparabilidade, desfecho/exposição) | Total de estrelas; faixas de qualidade definidas pelo grupo (não há corte universal) |
| **Genérico** | Qualquer outro | Configurável | Configurável |

> Verificar a **versão atual** de cada instrumento antes de montar os templates (o ROBINS-I, por exemplo, ganhou uma versão 2). Registrar a versão usada em cada avaliação.

#### Templates configuráveis
- Cada instrumento é um JSON: domínios, perguntas, respostas possíveis, regras de "pular pergunta", **algoritmo sugerido** de julgamento e versão.
- O sistema traz a **estrutura** (nomes de domínios e quantidade de perguntas). O **texto oficial** das perguntas é colado pelo admin a partir da fonte oficial, respeitando a licença. Confirmar com o grupo antes de distribuir textos completos.
- Domínios RoB 2: (1) randomização, (2) desvios das intervenções pretendidas, (3) dados de desfecho faltantes, (4) mensuração do desfecho, (5) seleção do resultado relatado.
- Domínios ROBINS-I (versão original): (1) confundimento, (2) seleção dos participantes, (3) classificação das intervenções, (4) desvios das intervenções pretendidas, (5) dados faltantes, (6) mensuração dos desfechos, (7) seleção do resultado relatado. Ajustar se o grupo usar a versão 2.

#### Regras de julgamento
- O sistema **sugere** o julgamento pelo algoritmo do instrumento. O revisor pode discordar, com justificativa obrigatória.
- RoB 2, geral sugerido: Baixo se todos os domínios forem Baixo; Alto se algum for Alto; Algumas preocupações nos demais casos. O manual permite julgar Alto quando há várias "algumas preocupações": a decisão fica com o revisor, com aviso.
- ROBINS-I, geral sugerido: o pior julgamento entre os domínios.
- JBI/NOS: aplicar a regra que o grupo configurou; se não houver regra, o julgamento geral é livre e obrigatório.
- Toda resposta tem campo de **justificativa** e, opcionalmente, trecho do PDF.
- O modelo de dados suporta avaliação **por estudo e por resultado** (desfecho + momento).

#### Fluxo
1. O sistema sugere o instrumento pelo desenho do estudo; o admin confirma.
2. Dois revisores avaliam de forma independente (cegados), com PDF ao lado. *Opção do projeto "Dupla avaliação de risco de viés" (ligada por padrão): desligada pelo admin, uma avaliação enviada basta para abrir o consenso, que o admin confere e envia (decisão do grupo em 2026-11-24; relatar nos Métodos).*
3. Tela de **conflitos**: lado a lado, pergunta por pergunta, com justificativas.
4. Consenso registrado (quem decidiu, motivo); terceiro revisor opcional.
5. **Tabela consolidada** (estudo × domínio) gerada automaticamente.
6. Kappa entre revisores na avaliação de risco de viés (P1).

#### Saídas
- Gráfico **semáforo** e **resumo** (barras por domínio, ponderado ou não), gerados com `robvis` no serviço R, em PNG e SVG.
- **robvis fixado em um commit do GitHub via `renv`**, não a versão do CRAN, porque a do CRAN não aceita "Sem informação" no ROBINS-I (lição L16). Testes cobrem esse caso e o tamanho/posição de rótulos com muitos estudos ou nomes longos.
- **JBI e Newcastle-Ottawa** não têm template no robvis (lição L17): usar o template genérico com domínios configurados ou um gráfico próprio em `ggplot2` com o mesmo visual. Decidir no ADR da Etapa 2.
- Exportação no formato de entrada do robvis (CSV) e em XLSX/DOCX.
- Instrumentos com **versão registrada** em cada avaliação, evitando ficar preso a versões antigas (lição L3).
- Uso na meta-análise: sensibilidade excluindo estudos de alto risco (7.7), subgrupo por risco de viés e insumo para o GRADE (7.8).

### 7.7 Meta-análise (P0)

#### Assistente passo a passo (estilo JASP, para leigos)
1. **Escolha o desfecho e o momento.** O sistema mostra quais estudos têm dados e **por que os outros ficaram de fora** (ex.: "não reporta o grupo ≥ 5 anos", "usa corte de 6 anos").
2. **Escolha a medida de efeito**, com recomendação automática:
   - Contínuo, mesma escala em todos → MD.
   - Contínuo, escalas diferentes (comum em cognição: QI, Bayley, etc.) → **SMD (g de Hedges)**.
   - Dicotômico → RR ou OR (com explicação da diferença).
   - Mistura de valor final e mudança desde a linha de base: permitido com MD, **bloqueado com SMD** (com explicação).
   - Mistura de estimativas ajustadas e não ajustadas: seguir o plano do protocolo; padrão é analisar separado e mostrar aviso.
3. **Confira a direção.** Se em uma escala "maior é pior", o sistema inverte o sinal e avisa. Rótulos do forest plot dizem o lado favorecido (ex.: "Favorece < 5 anos" | "Favorece ≥ 5 anos").
4. **Escolha o modelo.** Padrão: efeitos aleatórios, estimador **REML**, com ajuste **Hartung-Knapp** quando houver poucos estudos. O estimador pode ser trocado (DL, Paule-Mandel), com explicação em linguagem simples (lição L10).
5. **Resultado** com explicação automática em português claro, por exemplo: "Considerando 6 estudos, o grupo operado antes dos 5 anos teve escores cognitivos maiores (g = X; IC 95% A a B). A heterogeneidade foi moderada (I² = Y%)". Os números vêm sempre do resultado, nunca de texto fixo.

#### Pontos de corte diferentes entre estudos
- Os estudos podem usar cortes diferentes (ex.: 4, 5 ou 6 anos). O protocolo define a regra:
  - **Estrita:** só entra quem usa exatamente o corte da pergunta.
  - **Tolerante:** aceita cortes dentro de uma faixa definida, com subgrupo e sensibilidade por corte.
- Se o estudo reporta idade na cirurgia como variável contínua (ex.: correlação com o escore), ele **não entra** na meta-análise de dois grupos; fica listado na síntese narrativa (P1) ou em meta-regressão (P2).

#### Saídas obrigatórias
- Efeito combinado, IC 95%, valor p, τ², I², Q (gl e p), **intervalo de predição**.
- **Forest plot** (estudos, pesos, combinado, intervalo de predição, marcação de dados convertidos/estimados) em PNG/SVG, com rótulos em português configuráveis.
- Tabela de dados de entrada e efeitos por estudo.
- (P1) **Forest plot combinado com o semáforo de risco de viés** ao lado de cada estudo (lição L18). Avaliar a função de forest do robvis na versão de desenvolvimento ou montar com `metafor::forest()` + colunas extras; decidir em ADR.

#### Análises adicionais (P1)
- **Subgrupo** (variável categórica do formulário ou risco de viés), com teste de diferença entre subgrupos.
- **Sensibilidade**: leave-one-out; excluir alto risco de viés; excluir dados estimados (mediana → média); trocar efeito fixo/aleatório; trocar estimador.
- **Funnel plot** e **teste de Egger**, com aviso forte se k < 10.
- **Meta-regressão** (P2), com aviso se poucos estudos.
- **Desfechos dependentes** (vários momentos ou escalas do mesmo estudo): no MVP, escolher um por estudo seguindo regra do protocolo; modelo multinível (`rma.mv`) só na P2.
- **Síntese narrativa** (P1): tabela organizada dos estudos que não puderam entrar na meta-análise, com direção do efeito.

#### Avisos automáticos
- k < 2: não roda.
- k < 5: estimativas de heterogeneidade instáveis.
- Mesmo estudo/coorte duas vezes: bloqueia e explica.
- Grupo de controle compartilhado em estudos com vários braços: avisa sobre dupla contagem.
- Dados convertidos ou estimados: marca no gráfico e sugere sensibilidade sem eles.
- Zero eventos nos dois grupos (dicotômico): estudo excluído do pooling de OR/RR por padrão, com aviso.
- Análise rodada com configuração diferente do plano do protocolo: marca como "não planejada".
- Estudo com alertas de extração não resolvidos (7.5.1): a análise roda, mas o estudo aparece marcado e o resultado ganha aviso.
- Dado de entrada alterado depois da análise: análise marcada como "desatualizada".

#### Reprodutibilidade
- Toda análise salva: dados exatos, parâmetros, estudos incluídos, versões do R e dos pacotes, data e autor.
- Botão **"Exportar script R"**: gera um `.R` com os dados e as chamadas `escalc()`/`rma()` exatas que reproduzem o resultado no RStudio.

### 7.8 Certeza da evidência — GRADE (P1)
- Por desfecho: certeza inicial conforme o desenho e a abordagem escolhida (registrar qual).
- Rebaixar por: risco de viés, inconsistência, evidência indireta, imprecisão, viés de publicação. Elevar (observacionais) por: efeito grande, dose-resposta, confundimento plausível que reduziria o efeito.
- O sistema **pré-preenche sugestões** a partir dos dados (I² alto → inconsistência; IC largo cruzando o nulo → imprecisão; muitos estudos de alto risco → risco de viés; corte de idade diferente da pergunta → evidência indireta). A decisão final é humana, com justificativa.
- Gera a tabela **Summary of Findings** (DOCX/XLSX).

### 7.9 PRISMA 2020 (P1)
- **Fluxograma** automático com as contagens do sistema: identificados por base, duplicatas removidas, triados, excluídos, texto completo avaliado, excluídos com motivos, incluídos na síntese e na meta-análise.
- Ajuste manual das contagens (registrado na auditoria) para quem importou só a lista final.
- **Checklist PRISMA 2020** (27 itens): o grupo marca onde cada item é atendido no manuscrito. O sistema marca automaticamente os itens que já tem dados (ex.: fluxograma, risco de viés, análises).
- Exportar SVG/PNG/DOCX.

### 7.10 Exportação central (P0 parcial)
| Item | Formatos | Prioridade |
|---|---|---|
| Tabela consolidada de risco de viés | CSV (robvis), XLSX, DOCX | P0 |
| Gráficos de risco de viés | PNG, SVG | P0 |
| Dados extraídos | XLSX, CSV | P0 |
| Forest plot e tabela de resultados | PNG, SVG, DOCX | P0 |
| Script R reprodutível | `.R` | P0 |
| Backup completo do projeto | JSON + PDFs (ZIP), reimportável | P1 |
| Características dos estudos | DOCX, XLSX | P1 |
| Bibliografia dos incluídos | RIS, BibTeX, texto em Vancouver | P1 |
| PRISMA (fluxograma e checklist) | PNG, SVG, DOCX | P1 |
| Summary of Findings | DOCX, XLSX | P1 |
| Rascunho de Métodos/Resultados | DOCX com os números preenchidos, para o grupo editar | P2 |

Regras de exportação:
- CSV para Excel em português: separador `;`, vírgula decimal, UTF-8 com BOM. CSV para R/robvis: separador `,`, ponto decimal. O usuário escolhe.
- Gráficos em alta resolução (≥ 300 dpi no PNG) para pôster e resumo.
- Nome dos arquivos com projeto, tipo e data.
- **Nunca exportar em branco em silêncio** (lição L2): se faltar consenso em algum estudo, o sistema avisa quais estudos estão incompletos e oferece (a) exportar só o consenso, com a lista do que falta, ou (b) exportar as extrações individuais, identificadas por revisor e marcadas como "pré-consenso".
- Relatório de deduplicação e de alertas de extração resolvidos (úteis para o Métodos e para revisores do congresso).

### 7.11 Modo Aprendizado (P0)
- Glossário (seção 5) acessível de qualquer tela; termos técnicos com tooltip.
- Em cada etapa, um painel recolhível "O que estou fazendo aqui?" com explicação curta, exemplo e erros comuns.
- Na meta-análise, "Como ler este gráfico" com o forest plot anotado (linha do nulo, losango, tamanho do quadrado = peso, intervalo de predição).
- Tutorial guiado com projeto de demonstração (`dat.bcg` do metafor), marcado como exemplo.
- Links para as fontes oficiais (Cochrane Handbook, manuais dos instrumentos).

### 7.12 Auditoria e histórico (P0)
- Registro de toda alteração (entidade, campo, antes, depois, usuário, data).
- Histórico por estudo e por análise.
- Etapas podem ser travadas pelo admin; destravar exige justificativa.

### 7.13 Colaboração e notificações (P1)
- Comentários por estudo/campo, com menção (@nome).
- Notificações internas: conflitos novos, pendências, etapa liberada, prazo chegando.
- E-mail opcional para convites, senha e resumo semanal de pendências.

### 7.14 Apoio ao resumo para congresso (P2)
- Checklist **PRISMA para Resumos** (PRISMA-A).
- Rascunho estruturado (Introdução, Métodos, Resultados, Conclusão) com os números das análises inseridos automaticamente.
- Contador de palavras/caracteres com o limite do congresso configurável.
- O texto é sempre editado e aprovado pelo grupo; o sistema só preenche números e estrutura.

---

### 10.3 Usabilidade e acessibilidade
- **Bilíngue: português do Brasil e inglês** em toda a interface, Modo Aprendizado, glossário, e-mails, mensagens de erro, termos de uso e exportações. Idioma escolhido por usuário e detectado do navegador no primeiro acesso.
- **Idioma das saídas separado do idioma da interface:** forest plot, gráficos de risco de viés, tabelas, PRISMA e SoF podem ser gerados em pt ou en, independentemente de como o usuário usa o sistema (ex.: usar em português e exportar o forest plot em inglês para o congresso). O serviço R recebe o idioma como parâmetro.
- Formato de número segue o idioma das saídas (vírgula em pt, ponto em en), configurável.
- Interface responsiva (triagem e consulta no celular; extração e risco de viés pensados para tela grande).
- **Números:** exibição com vírgula decimal; entrada aceita vírgula e ponto; armazenamento sempre numérico; casas decimais configuráveis (padrão 2 na tela, precisão total no banco).
- Contraste adequado, navegação por teclado, labels em todos os campos; cores do semáforo **sempre** acompanhadas de rótulo em texto.
- **Mesmas opções e mesma lógica em celular e computador** (lição L8): o layout muda, as escolhas não.

---

## 12. Interface — telas principais
1. Login, cadastro, aceite de convite
2. Meus projetos (cartões com progresso e prazo)
3. Painel do projeto (etapas, pendências por pessoa, contagem regressiva)
4. Protocolo (PICO, critérios, desfechos, grupos, plano de análise, emendas)
5. Importação, mapeamento de colunas e duplicatas
6. Triagem (cartão + atalhos)
7. Estudos (lista, PDFs, desenho, relatos agrupados, contato com autores)
8. Extração (PDF à esquerda, formulário à direita)
9. Risco de viés (PDF à esquerda, perguntas por domínio à direita, julgamento sugerido em destaque)
10. Conflitos (lado a lado)
11. Tabela consolidada de RoB + gráficos
12. Assistente de meta-análise (passos 1 a 5), resultados e histórico de análises
13. GRADE / Summary of Findings
14. PRISMA (fluxograma e checklist)
15. Exportações
16. Resumo para congresso (P2)
17. Aprendizado (glossário, tutoriais, projeto de demonstração)
18. Configurações do projeto e membros (inclui ligar a IA e aceitar o aviso de uso de dados)
19. Tutor de IA (painel lateral disponível em todas as telas)
20. Meu perfil (idioma, formato de números, uso de cotas, exclusão de conta)
21. Administração do sistema (usuários, cotas, status dos serviços, uso de IA)
22. Termos de uso e política de privacidade (pt e en)

Padrões de UI:
- Cores do semáforo consistentes: verde = baixo; amarelo = algumas preocupações/moderado; vermelho = alto/grave; vermelho escuro = crítico; cinza = sem informação. Sempre com rótulo em texto.
- Estados vazios explicam o que fazer ("Nenhum estudo ainda. Cadastre ou importe sua lista.").
- Ações destrutivas pedem confirmação.
