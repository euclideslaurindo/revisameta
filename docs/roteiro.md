# Roteiro de desenvolvimento

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

## 13. Roteiro de desenvolvimento (por etapas e critérios de saída)

> Cada etapa só começa quando a anterior cumpre o critério de saída. Se o prazo do congresso apertar, a **Etapa 3 pode vir antes da 2**, pois a meta-análise é a maior dificuldade da usuária.

**Etapa 0 — Fundação**
Docker Compose com todos os serviços (perfis padrão e `lite`), Caddy, FastAPI com autenticação (cadastro com verificação de e-mail e captcha), projetos, membros e convites, auditoria e soft delete, Angular com login, i18n pt/en e cliente da API gerado, serviço R com `/health`, MinIO com upload em partes, worker `arq` com progresso (SSE + polling), cotas básicas, `.claude/settings.json` e hook de commits, backup/restore, ~~`make tunnel`~~, CI rodando testes.
*Saída:* `docker compose up` sobe tudo; login funciona nos dois idiomas; `/health` do R responde com versões; teste de isolamento por projeto passa; upload de um PDF de 100 MB retoma após queda; ~~o sistema abre por um endereço do Cloudflare Tunnel em outro dispositivo;~~ um commit de teste sai sem nenhuma menção a IA; backup e restauração testados.

> **Decisão (2026-11-13):** o Cloudflare Tunnel saiu da Etapa 0 por decisão do desenvolvedor. Ele volta quando houver sessões de teste com usuários fora deste computador (fase F0, ver `docs/deploy.md`). O fallback de polling do progresso continua implementado e testado.

**Etapa 0 concluída em 2026-11-14.** Conferência dos critérios de saída:

| Critério | Como foi verificado |
|---|---|
| `docker compose up` sobe tudo | 9 serviços saudáveis (caddy, backend, worker, stats-r ×2, postgres, redis, storage, mailpit); perfil `lite` com 1 processo R |
| Login nos dois idiomas | Fluxo cadastro → e-mail → confirmação → login → projeto testado no navegador; troca para inglês mantida após recarregar |
| `/health` do R com versões | R 4.6.2, metafor 5.2-1, meta 8.5-0, irr 0.85, robvis no commit `0c59cf1` |
| Isolamento por projeto | `tests/test_isolation.py`: não membros (inclusive admin do sistema) recebem 404 em todas as rotas de projeto |
| PDF de 100 MB retoma após queda | `tests/test_uploads.py::test_100mb_pdf_resumes_after_connection_drop` |
| Commit sem menção a IA | Hook testado num clone (remove `Co-Authored-By`, barra menções); `scripts/check-commit-messages.sh` no CI |
| Backup e restauração | `scripts/test-backup.sh`: estado após a restauração idêntico ao do backup |
| CI rodando testes | GitHub Actions: backend, frontend, serviço R, auditorias de dependências, gitleaks e mensagens de commit |

**Etapa 1 — Estudos, PDFs e extração (P0)**
Cadastro e importação da lista final, upload e anotação de PDF, relatos agrupados, formulário padrão versionado com braços e desfechos por grupo, proteções anti-erro dos blocos A, C, D, F e G de 7.5.1, exportação XLSX/CSV com regra de consenso.
*Saída:* a usuária cadastra 4 estudos reais com dados dos dois grupos sem planilha paralela; os testes de casos sintéticos de 7.5.1 (blocos A, C, D, F e G) passam.

**Etapa 1 — implementação concluída em 2026-11-14; falta o teste com a usuária.**

| Critério | Situação |
|---|---|
| Testes sintéticos do bloco A (valores impossíveis e alertas) | `tests/test_safeguards.py` |
| Bloco C (frase de direção, inversão pela escala) | `tests/test_safeguards.py` |
| Bloco D (comparação, divergências, consenso, concordância) | `tests/test_consensus.py`; kappa contra o `irr` em `stats-r/tests/testthat/test-kappa.R` |
| Bloco F (conferência final e trava) | `tests/test_review.py` |
| Bloco G (digitar uma vez: toda mudança em números sobe a versão dos dados; exportação lê só o consenso) | `tests/test_extraction.py`, `tests/test_exports.py`. A marcação de análises "desatualizadas" chega com as análises, na Etapa 3 |
| Exportação XLSX/CSV com regra de consenso | `tests/test_exports.py` |
| A usuária cadastra 4 estudos reais com os dados dos dois grupos, sem planilha paralela | **Pendente:** depende de uma sessão de teste com a usuária |

As lacunas do passo 4 foram fechadas em 2026-11-14: editor do formulário de características (na página Protocolo), campos de efeito informado pelo artigo, valor p e estatística t (com as checagens de valores impossíveis e o alerta de efeito fora do IC) e destaque dos trechos salvos sobre a página do PDF.

**Etapa 2 — Risco de viés e migração (P0)**
Templates configuráveis (ROBINS-I, RoB 2, JBI, NOS, genérico), dupla avaliação cega, conflitos, consenso, tabela consolidada, gráficos robvis (versão fixada do GitHub, com "Sem informação" testado), solução para JBI/NOS, exportações, importação da tabela consolidada já existente.
*Saída:* a avaliação de um estudo feita à mão bate com a do sistema; os gráficos saem iguais aos do robvis web com os mesmos dados; a planilha atual do grupo é importada sem perda.

**Etapa 2 — implementação concluída em 2026-11-16; faltam as conferências com o grupo.**

| Critério | Situação |
|---|---|
| Templates ROBINS-I (2016 e V2), RoB 2, ROBINS-E, JBI (todos os desenhos), NOS e genérico, com versão registrada | `tests/test_rob_tools.py`; estrutura sem o texto oficial (regra 0.1.7) |
| Algoritmos oficiais de julgamento por domínio e geral | `tests/test_rob_algorithm.py`: caminhos de cada fluxograma e sorteio de respostas para as regras de "pular pergunta" |
| Dupla avaliação cega, conflitos, consenso e kappa | `tests/test_rob_assessments.py`, `tests/test_rob_consensus.py`; kappa contra o `irr` em `stats-r/tests/testthat/test-kappa.R` |
| Tabela consolidada e gráficos (robvis fixado; "Sem informação" e "Grave" juntos; muitos estudos e nomes longos) | `tests/test_rob_consolidated.py`, `stats-r/tests/testthat/test-rob-plots.R`; JBI/NOS/ROBINS-I V2/ROBINS-E no ADR-013 |
| Exportações (CSV do robvis, CSV, XLSX, DOCX), nunca em branco em silêncio | `tests/test_rob_exports.py` |
| Importação da tabela consolidada existente | `tests/test_rob_import.py` |
| Revisão e trava da etapa | `tests/test_rob_review.py` |
| A avaliação de um estudo feita à mão bate com a do sistema | **Pendente:** os algoritmos já batem com os exemplos dos manuais; falta conferir um estudo real com o grupo |
| Os gráficos saem iguais aos do robvis web com os mesmos dados | **Parcial:** RoB 2 e ROBINS-I 2016 são desenhados pelo próprio robvis (template `Generic`, com rótulos traduzidos); falta comparar lado a lado com o robvis web usando uma tabela do grupo. Os demais instrumentos usam o gráfico próprio do ADR-013 |
| A planilha atual do grupo é importada sem perda | **Pendente:** depende do arquivo do grupo (pergunta 17.5) |

**Etapa 3 — Meta-análise (P0)**
Serviço R completo (8.3), conversões, combinação de braços, blocos B e E de 7.5.1 (detector de EP, recálculo de p/IC, influência), assistente passo a passo, regras de ponto de corte, forest plot, intervalo de predição, histórico de análises com marcação de "desatualizada", script R exportável, Modo Aprendizado na tela de resultados.
*Saída:* todos os testes de referência (11.1) passam; o script exportado reproduz os números em um R limpo; o detector acusa os casos sintéticos de EP digitado como DP.

**Etapa 3 — implementação concluída em 2026-11-17; falta o teste de interface automatizado.**

| Critério | Situação |
|---|---|
| Testes de referência no R (11.1, itens 1 e 2): 28 casos de `dat.bcg` e `dat.normand1999` (REML, DL, Paule-Mandel, efeito fixo, com e sem Hartung-Knapp), tolerância 1e-6 | `stats-r/tests/testthat/test-meta-analysis.R`; fixtures geradas pelo metafor (`scripts/generate-fixtures.sh`) |
| Mesmos dados pelo cliente Python e pela API (11.1, item 3) | `backend/tests/test_stats_reference.py` (serviço R real, também no CI); `test_analysis_assembly.py`: estudos montados no banco dão os mesmos yᵢ/vᵢ e o mesmo efeito combinado do metafor |
| Mesmos dados pela interface (11.1, item 4) | `e2e/tests/meta-analysis.spec.ts` (Playwright): o efeito na tela (MD = 15,11; IC −6,11 a 36,32) é comparado com a fixture do metafor, com o sinal invertido |
| O script R exportado reproduz os números num R limpo (11.1, item 5) | `stats-r/tests/testthat/test-r-script.R` roda o script num processo `Rscript --vanilla` novo. Também conferido com um script baixado do app (diferença máxima 3,6e-14) |
| Conversões e combinação de braços (8.5) | `stats-r/tests/testthat/test-conversions.R`, `backend/tests/test_stats_reference.py` |
| O detector acusa os casos sintéticos de EP digitado como DP (bloco B) | `stats-r/tests/testthat/test-plausibility.R`, `backend/tests/test_analysis_assembly.py`. Nos dados reais da demonstração houve 3 falsos positivos (ver `docs/estatistica.md`); os limiares devem ser revistos com os dados do grupo |
| Influência e efeitos improváveis (bloco E) | Iguais ao `influence()` do metafor (`test-plausibility.R`) |
| Bloqueios (k < 2, SMD misturando final e mudança, estudo repetido), regras de corte, ajustadas à parte | `backend/tests/test_analysis_assembly.py`, `test_analysis_plan.py` |
| Histórico com marcação de "desatualizada" (bloco G) | `test_saved_analyses_become_outdated_and_export_the_r_script` |

**Etapa 4 — Sensibilidade e subgrupos (P1)**
Leave-one-out, exclusão por risco de viés e por dados estimados, subgrupos, funnel/Egger com avisos, síntese narrativa, forest plot combinado com o semáforo de risco de viés.
*Saída:* resultados batem com o metafor nas fixtures.

**Etapa 4 — concluída em 2026-11-21.** Critério de saída cumprido: cada análise nova tem fixture gerada pelo metafor e testes que comparam com ela, no R e pela API.

| Item | Onde |
|---|---|
| Sensibilidade (leave-one-out, sem alto risco de viés, sem dados estimados, fixo × aleatório, outro estimador) | `stats-r/fixtures/leave-one-out.json`; `tests/test_analysis_sensitivity.py` |
| Subgrupos (τ² separado, teste Q entre subgrupos) | `stats-r/fixtures/subgroup.json`; `tests/test_analysis_subgroups.py` |
| Funnel plot e Egger (aviso forte com k < 10) | `stats-r/fixtures/egger.json`; `tests/test_analysis_publication_bias.py` |
| Síntese narrativa (direção registrada pelo revisor) | `tests/test_analysis_narrative.py` |
| Forest plot com semáforo de risco de viés (ADR-014) | `stats-r/tests/testthat/test-forest.R`; `tests/test_analysis_sensitivity.py` |

Ainda falta, como na Etapa 3, o teste de interface automatizado (Playwright).

**Etapa 5 — Triagem, importação e PRISMA (P1)**
Importação RIS/BibTeX/CSV/nbib, deduplicação multicritério com explicação, triagem dupla com kappa, desfazer, lotes por revisor, marcador "útil como referência", motivos de exclusão editáveis, fluxograma e checklist PRISMA.
*Saída:* importar uma busca real, triar e obter o fluxograma com contagens corretas.

**Etapa 5 — decisões aprovadas em 2026-11-21:**
- **Passos (um commit cada):**
  1. Importação RIS/BibTeX/CSV/nbib com a busca registrada.
  2. Deduplicação.
  3. Triagem de título/resumo.
  4. Texto completo com motivos editáveis.
  5. Priorização por aprendizado de máquina.
  6. Fluxograma PRISMA, desenhado no R.
  7. Checklist PRISMA 2020.
- **Duplicata certa:** DOI ou PMID iguais.
- **Duplicata provável** exige tudo junto:
  - título inteiro normalizado com similaridade ≥ 0,95 (`rapidfuzz` `token_sort_ratio`);
  - mesmo ano (se um dos dois não tem ano, o critério não conta);
  - mesmo sobrenome do primeiro autor, sem acento;
  - revista, volume e páginas iguais quando os dois registros têm.
  
  Os limiares podem ser configurados por projeto, e a remoção sempre passa por confirmação humana.
- **Relacionado, nunca duplicata:** títulos que diferem em números ou em palavras como Parte, Errata, Correção, Comentário, Resposta e Retratação.
- **Conflito na triagem dupla:** qualquer diferença entre os dois revisores, inclusive qualquer "Talvez". Dois "Incluir" passam e dois "Excluir" saem.
- **Checklist PRISMA 2020:** o texto oficial dos 27 itens entra no sistema (licença CC BY 4.0), com a citação de Page et al. 2021 na tela e nas exportações.

**Etapa 5, passo 1 — importação de buscas (feito):**
- **Aba "Buscas":** cada arquivo importado é registrado com a base, a data, a estratégia, o nome do arquivo e o formato.
- **Formatos aceitos:** RIS, PubMed/MEDLINE (.nbib), BibTeX e CSV (separador `;` ou `,`, cabeçalhos em pt ou en). Os leitores são próprios, sem dependência nova.
- **Como o arquivo é lido:**
  - O arquivo vai direto para o armazenamento.
  - O worker copia o arquivo para um temporário em disco e lê linha a linha. As referências são gravadas em lotes de 500. Um arquivo de 20 mil registros é testado.
  - A codificação é UTF-8 ou, nos arquivos antigos, Windows-1252.
- **Relatório de leitura** (guarda os 200 primeiros problemas):
  - registro sem título: não é importado;
  - DOI, PMID ou ano ilegível: o registro é importado, com o campo vazio e um aviso. Nunca se perde uma referência por um campo secundário.
- **Duplicatas:** todas ficam guardadas, inclusive o mesmo DOI duas vezes. Quem decide é a deduplicação (passo 2). O DOI continua único só entre as referências dos estudos.
- **Auditoria:** as referências importadas são gravadas em bloco e auditadas uma vez, pela linha da busca (quem importou, qual arquivo, quantos registros), em vez de 20 mil registros de auditoria.
- **Quem pode importar e remover:** admin ou revisor. Todos os membros leem.
- **Remover uma busca** é soft delete: a busca e as referências dela saem da lista, mas nada é apagado.

**Etapa 5, passo 2 — deduplicação (feito):**
- **Onde fica:** "Buscas → Duplicatas". As regras são funções puras em `backend/app/modules/references/dedup_rules.py`.
- **Comparação:** os registros são comparados só dentro de blocos (mesmo DOI, mesmo PMID ou mesmo sobrenome do primeiro autor), nunca todos contra todos.
- **Tipos de par:**
  - certos: mesmo DOI ou PMID;
  - prováveis: todos os critérios aprovados juntos;
  - relacionados: o título é igual quando se deixam de lado números e palavras como Parte, Errata, Comentário, Resposta e Retratação. Nunca são confirmados como duplicata.
- **Cada par mostra** a similaridade do título e os critérios que bateram, com os dois registros lado a lado.
- **Decisão:**
  - A pessoa escolhe qual registro fica. O outro ganha `duplicate_of` e sai da triagem.
  - Rejeitar significa "não é duplicata". Desfazer volta o par para "a decidir".
  - Tudo é auditado e usa trava otimista. Em cadeias (A → B → C), o registro removido aponta para o que fica no fim.
- **Confirmar todas as certas** de uma vez: em cada par, fica o registro importado primeiro.
- **Limiar de similaridade** configurável pelo admin (0,80 a 1; padrão 0,95). Rodar de novo mantém os pares já decididos e descarta os pendentes que não aparecem mais.
- **Relatório:** contagens para o PRISMA (importadas, duplicatas removidas, seguem para a triagem) e CSV com cada par, os critérios e a decisão, para o Métodos.
- **Dependência nova:** `rapidfuzz` (MIT, mantida, listada na seção 3.2).
- **Limitação conhecida:** ao desfazer um par cujo registro removido tinha outros apontando para ele, esses outros continuam no registro que fica.

**Etapa 5, passo 3 — triagem de título e resumo (feito):**
- **Aba "Triagem":** um cartão por vez, com título, autores, ano, revista, DOI e resumo. As palavras-chave de inclusão aparecem em verde e as de exclusão em vermelho. Os destaques são configurados pelo admin e não decidem nada.
- **Decisões:** Incluir, Excluir ou Talvez, com observação opcional.
  - As mesmas três opções e os mesmos atalhos valem em qualquer tela (L8): I, E e T (ou 1, 2 e 3), U para desfazer, setas para navegar.
  - Decidem admins e revisores.
- **Resultado:** com dois "Incluir" a referência passa e com dois "Excluir" ela sai. Qualquer outra combinação, inclusive qualquer "Talvez", vira conflito, e o admin resolve com um motivo. A resolução pode ser retirada (soft delete).
- **Cegamento ligado por padrão:** o revisor vê só as próprias decisões, também pela API (fila, histórico e contagens). O admin vê tudo e revela desligando o cegamento.
- **Histórico e desfazer (L6):** decisões nunca são editadas.
  - Uma decisão nova substitui a anterior.
  - "Desfazer" retira a última decisão do revisor e traz de volta a anterior.
  - Tudo fica no histórico da referência e na auditoria.
- **"Útil como referência" (L7):** marca, na referência, estudos excluídos que servem para a Introdução ou a Discussão.
- **Lotes (L9):** o admin dá as próximas N referências a um revisor, com até dois revisores por referência. Uma referência de um lote só pode ser decidida pelos revisores do lote (e pelos admins). "Recolher" devolve o que ainda não foi decidido.
- **Kappa de Cohen** para cada par de revisores, calculado no R (`/kappa`, irr). A tela traz uma explicação e as faixas de Landis e Koch, só como ajuda de leitura.
- **Referências triadas:** só as importadas de buscas, sem as duplicatas confirmadas.

**Etapa 5, passo 4 — texto completo e motivos de exclusão (feito; decisões aprovadas em 2026-11-21):**
- **Decisão no texto completo:** dupla e cega, como na triagem. A etapa aparece na mesma aba "Triagem" (seletor "Título e resumo" × "Texto completo"). Entram só os artigos incluídos em título e resumo.
- **Opções:** só Incluir ou Excluir, e excluir exige um motivo da lista do projeto.
- **Conflitos:** os revisores discordaram, ou os dois excluíram por motivos diferentes (o PRISMA precisa de um motivo por artigo). O admin resolve, escolhendo o motivo final.
- **Motivos de exclusão (L5):**
  - O projeto começa com uma lista padrão, guardada por chave e traduzida na tela.
  - O admin adiciona motivos e renomeia (o rótulo do grupo passa a valer no lugar da tradução).
  - Só remove motivos que nunca foram usados.
  - Pode juntar um motivo a outro: as decisões passam para o motivo que fica, e o juntado continua listado como "juntado a…".
  - Tudo é auditado.
- **Artigo incluído vira estudo** (aprovado: "botão, com escolha"):
  - A lista "Incluídos que ainda não viraram estudo" mostra os artigos que faltam.
  - O admin cria um estudo novo (nome sugerido: sobrenome do primeiro autor + ano) ou junta o artigo como mais um relato de um estudo existente, da mesma coorte.
  - A referência da busca vira o relato, sem cópia, e mantém o histórico da triagem.
  - Excluir o estudo não apaga a referência da busca: ela volta para a lista.
- **Rotas:** as da triagem recebem `stage=full_text`. As novas são `/screening/exclusion-reasons` e `/screening/included`.

**Etapa 5, passo 5 — priorização por aprendizado de máquina (feito):**
- **Modelo:** TF-IDF (unigramas e bigramas) + regressão logística com classes balanceadas, do `scikit-learn`. Roda no worker do próprio servidor, sem LLM e sem custo, no estilo do ASReview.
- **Treino:** usa as decisões atuais de título e resumo.
  - "Incluir" ou "Talvez" de algum revisor conta como incluída.
  - Só "Excluir" conta como excluída.
  - O treino exige pelo menos 5 de cada; com menos, a tarefa falha com uma mensagem clara.
  - O botão "Atualizar prioridade" treina de novo. Cada referência guarda a probabilidade em `priority_score`.
- **Uso:** "Mais prováveis primeiro" (`order=priority`) só muda a ordem da fila. Referências sem nota (importadas depois do último treino) ficam no fim, na ordem de importação.
- **O modelo nunca exclui, decide ou esconde nada.** A tela avisa que todas as referências precisam ser lidas, a menos que o protocolo defina um critério de parada.
- **Dependências novas:** `scikit-learn` (BSD, mantida, listada na seção 3.2), que traz `scipy` e `threadpoolctl` (BSD).
- **Por que no Python e não no R:** a ordenação não é estatística da meta-análise; a especificação põe essa função no Python (seção 3.2).

**Etapa 5, passo 6 — fluxograma PRISMA 2020 (feito):**
- **Aba "PRISMA":** contagens calculadas pelo sistema. A origem de cada caixa está explicada em `backend/app/modules/prisma/service.py`.
  - Identificados por base: o que veio de cada busca, antes de remover duplicatas.
  - Duplicatas removidas: as confirmadas por uma pessoa.
  - Triados, excluídos e buscados: decisões finais de título e resumo.
  - Não obtidos: excluídos no texto completo com o motivo "texto completo indisponível".
  - Avaliados e excluídos por motivo: decisões finais do texto completo.
  - Estudos e relatos incluídos: estudos e relatos do projeto.
  - Estudos em meta-análise: os que aparecem em pelo menos uma análise salva.
- **Ajuste manual** (para quem importou só a lista final): o admin digita a contagem com uma justificativa obrigatória. Isso é auditado, e o fluxograma marca a contagem com "*" e uma nota. "Usar a do sistema" desfaz o ajuste (soft delete).
- **Avisos:** a tela avisa quando há referências pendentes ou em conflito e quando as contas não fecham (identificados − duplicatas ≠ triados, por exemplo).
- **Desenho:** no serviço R (`/prisma-flow`), com `grid` do R base, sem pacote novo, no layout PRISMA 2020 para revisões novas.
  - Os textos de cada caixa chegam prontos do backend, no idioma escolhido (pt ou en, separado do idioma da interface).
  - Saídas em SVG, PNG a 300 dpi e DOCX (figura e lista dos ajustes com justificativa).

**Etapa 5, passo 7 — checklist PRISMA 2020 (feito):**
- **Os 27 itens:** em 42 linhas, contando os subitens 10a–b, 13a–f, 16a–b, 20a–d, 23a–d e 24a–c. Para cada um, o grupo marca a situação (pendente, relatado, não se aplica) e onde o manuscrito relata. Edição auditada, com trava otimista; o leitor só vê.
- **Dica do sistema:** "o sistema tem dados para este item" quando há buscas, estratégia, triagem, extração, risco de viés, estudos ou análises. Essa dica nunca marca o item como relatado.
- **Mudança em relação ao que foi aprovado:**
  - O texto oficial dos itens **não** foi copiado, nem em inglês nem na tradução em português.
  - Ficaram o número, a seção e o tópico oficiais e um resumo curto de cada item, escrito para o sistema (pt e en).
  - A tela e o DOCX levam para o checklist oficial (prisma-statement.org) e citam Page et al., BMJ 2021;372:n71.
  - Motivo: evitar reproduzir por extenso um texto de terceiros dentro do sistema, mesmo com licença CC BY.
- **Exportação:** DOCX do checklist, agrupado por seção.

**Etapa 5 — implementação concluída em 2026-11-23.**
- **Critério de saída** ("importar uma busca real, triar e obter o fluxograma com contagens corretas"): ainda depende de uma sessão com o grupo e uma busca real.
  - Cada contagem do fluxograma é conferida pelos testes com dados fictícios em `tests/test_prisma.py`.
- **Pendências:**
  - teste de interface automatizado (Playwright), como nas Etapas 3 e 4;
  - revisar com o grupo os resumos dos itens do checklist e o limiar de 0,95 da deduplicação.

**Etapa 6 — decisões aprovadas (2026-11-23):**
- **Plano em 6 passos:** (1) GRADE por desfecho; (2) Summary of Findings em DOCX/XLSX; (3) comentários com menção; (4) notificações internas; (5) bibliografia RIS/BibTeX/Vancouver; (6) backup em ZIP, reimportação e retenção.
- **Certeza inicial:** escolhida por desfecho e registrada. No GRADE clássico, observacionais começam em baixa; com ROBINS-I, em alta.
- **Retenção:** após 12 meses sem acesso, o admin recebe um aviso e o projeto é marcado como arquivado (reversível). Nada é apagado.
- **Limiares das sugestões do GRADE** (padrão; o admin pode mudar por projeto):
  - Inconsistência: I² ≥ 50%.
  - Imprecisão: o IC 95% do efeito combinado cruza o nulo.
  - Risco de viés: mais da metade dos estudos com julgamento geral alto, grave, crítico, muito alto ou ruim.
  - Viés de publicação: Egger p < 0,10, só com k ≥ 10.
  - Evidência indireta: algum estudo incluído com ponto de corte tolerado, diferente do protocolo.
  - Efeito grande (elevar): RR/OR ≥ 2 ou ≤ 0,5, sem nenhum rebaixamento sugerido.

**Etapa 6, passo 1 — GRADE (feito):**
- O sistema roda a mesma análise da tela de meta-análise e sugere uma mudança por domínio, com o motivo. Dose-resposta e confundimento plausível ficam só com o grupo.
- O grupo decide cada domínio. Toda mudança diferente de zero e toda escolha diferente da sugestão exigem justificativa.
- Certeza final = inicial − rebaixamentos + elevações, dentro da escala. Edição com trava otimista e auditoria; remoção é soft delete.
- Os limiares são comparados com o que o R devolve; nada é calculado no Python.

**Etapa 6, passo 2 — Summary of Findings (feito):**
- Uma linha por julgamento GRADE salvo: desfecho, momento, estudos, participantes, efeito com IC 95% (RR/OR na escala natural, como o R devolveu ao salvar), certeza (com a inicial e a abordagem) e motivos.
- As justificativas do grupo saem como notas numeradas. DOCX e XLSX, em português ou inglês, independente do idioma da interface; vírgula decimal em português.
- Sem nenhum julgamento salvo, a exportação avisa em vez de gerar arquivo vazio.

**Etapa 6, passo 3 — comentários (feito):**
- Comentários em estudo, referência ou análise, com campo opcional (ex.: "group1.sd"). Na tela, por enquanto, no estudo.
- Todo membro comenta, inclusive o leitor (o orientador lê e comenta; comentário não é dado da revisão).
- Menção escolhendo membros do projeto numa lista (só nomes, nunca e-mails); quem não é membro não pode ser mencionado. O aviso à pessoa mencionada chega no passo 4.
- Só o autor edita (trava otimista, auditoria); o autor ou o admin remove (soft delete).

**Etapa 6, passo 4 — notificações internas (feito):**
- Avisos na barra do topo, atualizados a cada minuto (polling; funciona no túnel rápido, sem SSE).
- **Menção:** quem foi mencionado num comentário, na criação ou quando é acrescentado numa edição; nunca o próprio autor.
- **Conflito de triagem:** os admins do projeto, uma vez por referência e etapa.
- **Prazo:** quando faltam 7 dias ou menos, gerado ao abrir os avisos (sem agendador), uma vez por data.
- Cada pessoa vê só os próprios avisos, e só de projetos de que ainda é membro. Os avisos não guardam e-mails.
- "Pendências por membro" já aparecem no painel do projeto; o resumo semanal por e-mail fica para quando houver e-mail transacional (10.6).

**Etapa 6, passo 5 — bibliografia (feito):**
- Todos os artigos (relatos) dos estudos do projeto, o principal primeiro, em RIS (Zotero/Mendeley), BibTeX ou texto em Vancouver (até 6 autores e "et al").
- Os campos saem como estão guardados; nada é inventado. A tela lista os estudos com artigo sem autores, ano ou revista, para completar antes de citar.
- Sem nenhum artigo, a exportação avisa em vez de gerar arquivo vazio.

**Etapa 6, passo 6 — backup do projeto, reimportação e retenção (feito):**
- **Backup (admin):** ZIP gerado pelo worker, sem carregar tudo na memória. Contém todas as tabelas do projeto, inclusive registros removidos (soft delete) e a auditoria, os nomes das pessoas (nunca e-mails) e os PDFs. Ficam de fora só avisos, convites e tarefas de fila. Download por link assinado de 10 minutos.
- **Reimportação:** cria um projeto NOVO (o original pode continuar existindo), com ids novos também dentro dos campos JSON. Quem tem conta no sistema mantém seus registros; o que foi feito por quem não tem conta fica atribuído a quem restaura, e a tela lista esses nomes. O PDF já guardado (mesmo SHA-256) não é duplicado. Só aceita backup da mesma versão do banco.
- **Retenção:** todo dia às 3h15 o worker marca como arquivado o projeto sem nenhuma alteração há 12 meses e avisa os admins. É só uma marca: nada é apagado, o projeto continua funcionando e o admin reativa com um clique.
- **Limite conhecido:** pelo túnel da Cloudflare, cada envio vai até 100 MB; um backup maior que isso precisa ser restaurado direto no servidor (sem túnel) até haver envio em partes para backups.

**Etapa 6 — implementação concluída em 2026-11-23.**
- **Critério de saída:**
  - tabela SoF em DOCX com justificativas: coberta por `tests/test_grade.py`;
  - restauração de backup testada: `scripts/test-backup.sh` (banco inteiro, Etapa 0) e `tests/test_backup.py` (projeto);
  - reimportação de um projeto exportado sem perda: `tests/test_backup.py` compara a contagem de todas as tabelas, inclusive registros removidos.
- **Pendências:** teste de interface automatizado (Playwright), como nas etapas anteriores; conferir com o grupo os limiares do GRADE com dados reais; resumo semanal por e-mail quando houver e-mail transacional.

**Etapa 6 — GRADE, colaboração e entrega (P1)**
GRADE e Summary of Findings, comentários, notificações, backup/reimportação do projeto, bibliografia, retenção de projetos inativos.
*Saída:* tabela SoF em DOCX com justificativas; restauração de backup testada; reimportação de um projeto exportado sem perda.

**Etapa 7 — IA confiável (P1/P2)**
Camada de provedores (Gemini gratuito primeiro, mock nos testes), aviso e aceite de uso de dados, tutor (IA1), localizador de trechos (IA2), verificação de citação, métricas de precisão, cotas e cache. Depois IA3 a IA6.
*Saída:* nenhuma sugestão de IA vira dado final sem confirmação humana; citações inexistentes são descartadas; a precisão aparece contra o consenso humano (testes automatizados garantem isso).

**Etapa 8 — Extras (P2)**
Digitalizador de gráficos, OCR, meta-regressão, modelos multinível, apoio ao resumo (PRISMA-A), rascunho de Métodos/Resultados, 2FA.
*Saída:* cada extra com testes e documentação nos dois idiomas.

**Mudança de fase de hospedagem (F0 → F1)** pode acontecer entre qualquer etapa, quando houver uso contínuo; segue o checklist de `docs/deploy.md` e exige teste de restauração.

**Testes de interface (Playwright), 2026-11-23:**
- `scripts/test-e2e.sh` roda `e2e/` na imagem oficial do Playwright (1.65.0, Apache-2.0), na mesma rede do Caddy, contra o sistema no ar. Cria contas de teste verificadas em `@example.org` com senha aleatória a cada execução (`app.scripts.e2e_users`, recusado em produção) e um projeto de demonstração novo (`dat.normand1999`).
- Os textos da interface vêm do próprio arquivo de i18n; os números esperados, das fixtures do metafor. Nada é digitado à mão.
- Cobertos (9 testes): login; meta-analise com o mesmo efeito do metafor (11.1, item 4); forest plot, histórico e script R; aviso forte do Egger com menos de 10 estudos; risco de viés com dois revisores, conflitos decididos pelo admin, consenso e semáforo (fluxo mínimo de 11.3); GRADE com justificativa e Summary of Findings; comentário com menção chegando como aviso; checklist PRISMA; backup baixado e restaurado como projeto novo.
- Primeiro achado: a tela do GRADE mostrava "I² = 99.0%" com ponto em português; corrigido para usar o formato de número do app.
- **Ainda fora:** no fluxo mínimo de 11.3, o cadastro dos 4 estudos e a extração pela interface (o teste usa o projeto de demonstração já extraído), e a migração de uma tabela de RoB existente. Ficam para quando houver os dados reais do grupo.

**Etapa 7 — decisões aprovadas (2026-11-23):**
- **Plano (primeira parte):** (1) camada de provedores, com provedor falso nos testes e adaptador Gemini; (2) liga/desliga por projeto com aviso de uso de dados (pt/en) e aceite auditado; (3) fila com limite de taxa global, cota por usuário/dia e cache; (4) tutor IA1, que só explica números já calculados pelo R, com marcadores (`{{pooled_effect}}`) e sinalização de número inventado; (5) localizador de trechos IA2, com a citação conferida no texto do PDF e descartada se não existir; (6) métricas de precisão contra o consenso humano e desligamento automático. IA3 a IA6 ficam para a segunda parte.
- **Limiares (padrão, configuráveis):** 30 chamadas por usuário por dia; 10 chamadas por minuto no sistema todo; função desligada no projeto se o acerto ficar abaixo de 80% nas últimas 30 sugestões decididas por pessoas (só a partir de 10).
- **Provedor:** Gemini gratuito primeiro, com a chave criada depois pelo responsável no Google AI Studio (sem cartão). Sem chave, a IA fica indisponível e o resto funciona; os testes usam só o provedor falso.
- **Termos conferidos em 2026-11-23** (ai.google.dev: rate-limits, pricing, billing): no plano gratuito, prompts e respostas podem ser usados para melhorar produtos do Google (por isso o aviso); as cotas valem por projeto do Google, não por chave, mudam sem aviso (há relatos de queda para 20 chamadas por dia) e zeram à meia-noite do Pacífico; desde 19/06/2026 só chaves restritas são aceitas. Por isso há também um teto diário global configurável, e o sistema trata "cota esgotada" como estado normal.

**Etapa 7, passo 1 — camada de provedores (feito):**
- `app/integrations/ai/`: interface única (`complete`, `complete_structured`, `embed`), provedor falso para testes e adaptador Gemini por REST (httpx, já usado no projeto; sem SDK do fornecedor, para manter a camada trocável).
- A chave vai no cabeçalho, nunca na URL (não aparece em logs). Instruções do sistema separadas do conteúdo. Resposta fora do esquema é descartada (`AIInvalidOutputError`).
- Cota esgotada (429) vira estado normal (`AIQuotaExceededError`); sem chave, a IA fica indisponível (`AIUnavailableError`) e o resto funciona.
- Configuração em `.env` (`AI_PROVIDER=none` por padrão). Nenhum teste chama um provedor real.

**Etapa 7, passo 2 — IA por projeto e aviso de uso de dados (feito):**
- Nova aba "Configurações" do projeto. A IA começa desligada; só um admin liga, e só marcando o aceite do aviso atual (pt/en, em `app/modules/ai/notice.py`, com versão). Quem aceitou, quando e qual versão ficam em `ai_settings` e na auditoria.
- O aviso diz quem recebe os dados (Google, plano gratuito, pode usar para melhorar produtos), o que é enviado (só o trecho ou resultado pedido) e o que nunca é enviado (anotações, comentários, nomes e e-mails de membros, decisões, extrações e avaliações em andamento, PDFs inteiros).
- Se o texto do aviso mudar, o aceite antigo deixa de valer e a IA fica desligada até novo aceite.
- `require(ctx, função)`: toda função de IA chama antes de qualquer coisa; recusa se a IA estiver desligada, a função não estiver liberada, tiver sido desligada por baixa precisão ou não houver provedor no servidor. Nada chega ao provedor nesses casos.

