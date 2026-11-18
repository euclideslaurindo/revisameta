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

**Etapa 5 — Triagem, importação e PRISMA (P1)**
Importação RIS/BibTeX/CSV/nbib, deduplicação multicritério com explicação, triagem dupla com kappa, desfazer, lotes por revisor, marcador "útil como referência", motivos de exclusão editáveis, fluxograma e checklist PRISMA.
*Saída:* importar uma busca real, triar e obter o fluxograma com contagens corretas.

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
