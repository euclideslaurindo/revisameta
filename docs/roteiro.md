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

Lacunas conhecidas, para depois: tela para o administrador editar o formulário de características (a API existe), campos de "efeito já calculado pelo artigo" na tela (o banco e a API aceitam) e marcação dos trechos salvos em cima da página do PDF.

**Etapa 2 — Risco de viés e migração (P0)**
Templates configuráveis (ROBINS-I, RoB 2, JBI, NOS, genérico), dupla avaliação cega, conflitos, consenso, tabela consolidada, gráficos robvis (versão fixada do GitHub, com "Sem informação" testado), solução para JBI/NOS, exportações, importação da tabela consolidada já existente.
*Saída:* a avaliação de um estudo feita à mão bate com a do sistema; os gráficos saem iguais aos do robvis web com os mesmos dados; a planilha atual do grupo é importada sem perda.

**Etapa 3 — Meta-análise (P0)**
Serviço R completo (8.3), conversões, combinação de braços, blocos B e E de 7.5.1 (detector de EP, recálculo de p/IC, influência), assistente passo a passo, regras de ponto de corte, forest plot, intervalo de predição, histórico de análises com marcação de "desatualizada", script R exportável, Modo Aprendizado na tela de resultados.
*Saída:* todos os testes de referência (11.1) passam; o script exportado reproduz os números em um R limpo; o detector acusa os casos sintéticos de EP digitado como DP.

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
