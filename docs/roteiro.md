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
| Mesmos dados pela interface (11.1, item 4) | **Pendente:** ainda não há Playwright no repositório. Conferido à mão no projeto de demonstração (MD = 15,11; IC −6,11 a 36,32, igual à fixture com o sinal invertido) |
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
