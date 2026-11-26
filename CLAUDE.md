# CLAUDE.md — Sistema "RevisaMeta"

> Plataforma web única para revisões sistemáticas com meta-análise, pensada para pesquisadores **iniciantes**.
> Junta em um só lugar o que hoje está espalhado em Rayyan, Covidence, RevMan, robvis, JASP/R, GRADEpro e no gerador de fluxograma PRISMA.
> **Foco principal:** evitar os erros humanos que mais estragam meta-análises (ver seção 2.1 e 7.5.1).
> **Situação atual:** sem orçamento. Tudo precisa funcionar com **custo zero** na fase de testes com usuários (seção 10.6). Repositório **privado**. Sistema **aberto ao público** (cadastro livre) e **bilíngue** (português e inglês). Sem prazo: todas as funcionalidades entram, na ordem das etapas.

---

## Mapa da documentação

A especificação completa foi dividida para manter o contexto de cada sessão leve. Os números de seção originais foram mantidos, então referências como "ver 7.5.1" continuam valendo: use a tabela abaixo para achar o arquivo.

| Seções | Arquivo | Conteúdo |
|---|---|---|
| 0, 3, 4, 14, 15 | este arquivo | Instruções, stack, estrutura do repositório, convenções, riscos |
| 1, 2, 5, 6, 16, 17, 18 | [docs/dominio.md](docs/dominio.md) | Contexto, ferramentas de referência e lições (L1–L19), glossário, papéis e acesso, fora do escopo, perguntas em aberto, referências |
| 7.1–7.14, 10.3, 12 | [docs/modulos.md](docs/modulos.md) | Módulos funcionais (inclui 7.5.1, proteções anti-erro), usabilidade e acessibilidade, telas |
| 7.15 | [docs/ia.md](docs/ia.md) | IA assistiva: onde entra, onde nunca entra, regras contra alucinação, provedores |
| 8 | [docs/estatistica.md](docs/estatistica.md) | Serviço R: regras, contrato Python ↔ R, endpoints, medidas, conversões |
| 9 | [docs/modelo-dados.md](docs/modelo-dados.md) | Modelo de dados (rascunho) |
| 10.1, 10.2, 10.4, 10.5 | [docs/riscos.md](docs/riscos.md) | Segurança, privacidade (LGPD), confiabilidade, observabilidade |
| 10.6, 10.8 | [docs/deploy.md](docs/deploy.md) | Implantação por fases (F0/F1/F2), backup e retenção |
| 10.7 | [docs/arquivos.md](docs/arquivos.md) | Arquivos grandes: upload em partes, deduplicação, processamento |
| 11 | [docs/validacao.md](docs/validacao.md) | Testes de referência estatística, testes de domínio, critérios gerais |
| 13 | [docs/roteiro.md](docs/roteiro.md) | Roteiro por etapas (0 a 8) e critérios de saída |
| — | `docs/adr/` | Decisões de arquitetura (ADRs, ver 14.2) |

Antes de trabalhar em um módulo, leia o arquivo de `docs/` correspondente.

---

## 0. Instruções para você, Claude Code (leia antes de qualquer coisa)

### 0.1 Como trabalhar neste projeto
1. **Este documento é a fonte da verdade.** Se algo estiver ambíguo ou contraditório, **pare e pergunte** antes de implementar. Não invente regras de domínio.
2. **Na primeira sessão**, antes de escrever código *(divisão já feita; a seção 13 ficou em `docs/roteiro.md`)*:
   - Leia o documento inteiro.
   - Divida-o em: um `CLAUDE.md` curto (seções 0, 3, 4, 14 e 15) + arquivos em `docs/` (`docs/dominio.md`, `docs/modulos.md`, `docs/estatistica.md`, `docs/modelo-dados.md`, `docs/validacao.md`, `docs/riscos.md`, `docs/ia.md`, `docs/deploy.md`, `docs/arquivos.md`). O `CLAUDE.md` curto deve apontar para cada arquivo de `docs/`. Assim o contexto de cada sessão fica leve.
   - Liste as dúvidas que encontrar (além das da seção 17).
   - Proponha o plano da **Etapa 0** (seção 13) e espere aprovação.
3. **Trabalhe em passos pequenos.** Uma funcionalidade por vez, com testes, commit e resumo do que mudou.
4. **Nunca calcule estatística no backend Python nem no frontend.** Toda conta estatística é feita pelo serviço R com `metafor`/`meta`/`robvis` (seção 8) e coberta por testes de referência (seção 11).
5. **Nunca gere valores esperados de teste "de cabeça".** Gere-os rodando o R/metafor e salve como fixture, junto com o script que os gerou.
6. **Nunca invente dados clínicos.** Dados de exemplo vêm de datasets públicos do `metafor` (ex.: `dat.bcg`) ou são claramente marcados como fictícios.
7. **Não copie textos protegidos por direitos autorais** (checklists JBI, manuais RoB 2/ROBINS-I, escala Newcastle-Ottawa). Os instrumentos são **templates JSON configuráveis** (seção 7.6); o texto oficial é inserido pelo usuário a partir da fonte oficial, respeitando a licença.
8. **Explique para leigos.** A usuária principal nunca fez meta-análise. Todo termo técnico na interface tem tooltip ou link para o Modo Aprendizado (seção 7.11).
9. **Não adicione dependências sem justificar** (o que resolve, licença, se é mantida). Prefira as listadas na seção 3.
10. **Isolamento por projeto é regra de segurança:** toda consulta ao banco filtra por `project_id` e verifica se o usuário é membro. Escreva teste para isso em todo endpoint novo.
11. Ao terminar cada etapa, rode lint, checagem de tipos, testes e testes de referência estatística, e mostre o resultado.
12. **Commits e PRs sem nenhuma menção a IA** (regra obrigatória, ver 14.1): nada de `Co-Authored-By` de assistente, rodapé "Generated with...", trailer de sessão ou link de sessão. Mensagens escritas como as de um desenvolvedor humano, em Conventional Commits.
13. **Custo zero é requisito:** não introduza serviço pago, nem serviço que exija cartão, sem aprovação explícita. Toda peça precisa rodar no Docker Compose local (seção 10.6).
14. **Nunca coloque texto fixo na interface:** tudo passa pelo i18n em `pt-BR` e `en` (seção 10.3).

### 0.2 O que NÃO fazer
- Não decidir sozinho que um estudo tem alto risco de viés ou que deve ser incluído/excluído: o sistema **sugere e organiza**; humanos **decidem**.
- Não criar "nota total" para checklists JBI (não existe ponto de corte oficial; o grupo define o critério).
- Não rodar Egger/funnel como conclusão com menos de 10 estudos sem um aviso explícito.
- Não esconder premissas: toda análise mostra modelo, estimador, medida de efeito, estudos incluídos e conversões usadas.
- Não apagar dados de decisões, extrações ou avaliações de forma definitiva (soft delete).
- Não deixar sugestões de IA virarem dado final sem confirmação humana.
- Não exportar dados incompletos em silêncio (ex.: extração sem consenso saindo em branco). Sempre avisar o que está faltando.
- Não remover duplicatas automaticamente quando a duplicata for só "provável".
- Não deixar a IA calcular estatística, decidir inclusão/exclusão, dar julgamento final de risco de viés ou escrever números em textos (seção 7.15).
- Não enviar conteúdo de projeto a um provedor de IA externo sem o projeto ter ligado a IA e aceitado o aviso de uso de dados.
- Não carregar um arquivo grande inteiro na memória do backend (seção 10.7).

### 0.3 Definição de "pronto" (vale para toda funcionalidade)
- [ ] Atende aos critérios desta especificação.
- [ ] Testes unitários e de integração passando; cobertura não caiu.
- [ ] Permissões e isolamento por projeto testados.
- [ ] Textos da interface em português, via i18n, com tooltips nos termos técnicos.
- [ ] Ação registrada na auditoria (quando altera dados).
- [ ] Tratamento de erro com mensagem clara para o usuário.
- [ ] Documentação atualizada (`docs/` e, se for decisão de arquitetura, um ADR).

---

## 3. Stack técnica

### 3.1 Decisão
| Camada | Tecnologia | Motivo |
|---|---|---|
| Frontend | **Angular 22**, **Angular Material/CDK** (*substitui o PrimeNG, que mudou para licença comercial; ver ADR-011*), **Transloco** (i18n pt-BR/en), `ngx-extended-pdf-viewer` (PDF.js) | Stack que o desenvolvedor domina; tabelas fortes para triagem e extração |
| Backend | **Python 3.12 + FastAPI**, Pydantic v2, **SQLAlchemy 2.0 assíncrono (asyncpg)**, Alembic | Rápido de desenvolver; muito I/O; ecossistema forte para dados, PDFs, importação e IA |
| Autenticação | JWT: access token curto **só em memória no front** + refresh token rotativo em **cookie httpOnly/Secure/SameSite**; senhas com **Argon2id** (`argon2-cffi`) | Evita tokens no localStorage |
| Banco | **PostgreSQL 16** com `unaccent`, `pg_trgm` e busca textual (pt/en) | Relacional + JSONB + busca nas referências sem Elasticsearch |
| IDs | **UUID v7** | Ordenáveis por tempo, melhores para índices |
| Armazenamento de arquivos | **RustFS** (compatível com S3) no Docker Compose. *Substitui o MinIO, descontinuado em 2025; ver ADR-004* | Upload direto em partes por URL assinada (10.7); migra para qualquer S3 sem mudar código |
| Estatística | **Serviço R** com `plumber` + `metafor` + `meta` + `robvis` (+ `irr` para kappa) | Padrão-ouro; evita reimplementar estatística |
| Tarefas longas | Fila com **Redis + `arq`** (assíncrona, como o FastAPI) desde a Etapa 1 | Processamento de PDF, importações grandes, ZIPs, gráficos, IA |
| Progresso em tempo real | **SSE** com **fallback automático para polling** | O túnel rápido da Cloudflare não suporta SSE (10.6) |
| Gráficos | Interativos no front com ECharts/Chart.js; **gráficos oficiais (PNG/SVG) gerados pelo R** | Iguais aos do metafor/robvis |
| Contrato da API | OpenAPI gerado pelo FastAPI → cliente TypeScript gerado para o Angular (`openapi-typescript` ou `ng-openapi-gen`) | Front e back nunca saem de sincronia |
| Infra | Docker Compose (caddy, frontend, backend, worker, stats-r ×2, postgres, redis, minio) + perfil `lite` para máquinas fracas | Sobe tudo com um comando, igual em qualquer máquina |
| Proxy/HTTPS | **Caddy** | Serve o front, faz proxy da API e balanceia os 2 processos R; HTTPS automático quando houver servidor público |
| Imagens | Todas com suporte **amd64 e arm64** | Permite migrar para servidores ARM gratuitos (Oracle) no futuro |
| API | REST versionada (`/api/v1`), erros em **Problem Details (RFC 9457)**, paginação por cursor | Padrão claro e listas grandes |
| Testes | `pytest` + `httpx` + Testcontainers; Jest ou Karma no front; `testthat` no R; Playwright (E2E) | Cobertura em todas as camadas |
| Qualidade | `ruff` (lint/format), `mypy` (tipos), ESLint/Prettier, `lintr` no R, pre-commit | Padronização automática |
| Dependências | `uv` (Python), `npm`, `renv` (R) com versões fixadas | Builds reprodutíveis |

### 3.2 Bibliotecas Python sugeridas
| Uso | Biblioteca |
|---|---|
| Importar RIS / BibTeX / PubMed | `rispy`, `bibtexparser`, parser próprio para `.nbib` |
| Deduplicação aproximada | `rapidfuzz` |
| Ler PDF (texto, busca, páginas) | `pypdfium2` (*PyMuPDF é AGPL; ver ADR-012*) |
| Ler planilhas e CSV | `pandas`, `openpyxl` |
| Exportar Word / Excel | `python-docx`, `openpyxl` |
| Cliente HTTP do serviço R | `httpx` (com timeout e retry) |
| E-mail (convites, senha) | `fastapi-mail` ou SMTP simples |
| Fila e tarefas | `arq` |
| Rate limiting | `slowapi` |
| Cliente S3 (URLs assinadas, multipart) | `aioboto3` |
| Validação do tipo real de arquivo | `python-magic` (libmagic) |
| OCR de PDF escaneado (P2) | `ocrmypdf` |
| Priorização de triagem (ML clássico, local e gratuito) | `scikit-learn` (TF-IDF + modelo linear), inspirado no ASReview |
| IA (camada de provedores, 7.15) | SDK oficial de cada provedor por trás de uma interface própria; sem acoplamento a um único fornecedor |

### 3.3 Divisão de responsabilidades
- **Python (FastAPI + worker):** autenticação, permissões, regras de fluxo, CRUD, importação/exportação, URLs assinadas e processamento de PDFs, auditoria, orquestração das análises, camada de IA e verificação das citações da IA.
- **R (plumber):** **somente** estatística e gráficos estatísticos. Funções puras, sem acesso ao banco.
- **Angular:** interface, validação de formulário para a usabilidade (a validação de verdade é sempre no backend).

### 3.4 Alternativas consideradas (não usar sem aprovação)
- Estatística em Python (`statsmodels`, `PyMARE`): **rejeitado** como motor principal. Menos estimadores maduros e menos confiança dos revisores. Pode servir só para conferência cruzada.
- `rpy2` (R dentro do Python): possível, mas acopla os processos e dificulta deploy e testes. Preferir o serviço HTTP separado.
- webR (R no navegador): avaliar só na P2.
- **Vercel + Supabase como plataforma principal: rejeitado.** O serviço R e a fila não rodam em funções serverless; o Supabase gratuito tem 500 MB de banco, 1 GB de arquivos, 5 GB de tráfego por mês, pausa após 7 dias sem uso e não tem backup diário. Poderia servir só para hospedar o frontend estático no futuro (atenção: o plano gratuito da Vercel é para uso não comercial; Cloudflare Pages é alternativa).
- Celery: mais pesado que o necessário; `arq` atende.
- Elasticsearch: desnecessário; a busca textual do Postgres resolve.
- Kubernetes: exagero para a escala atual.

---

## 4. Estrutura do repositório

```
revisameta/
├── CLAUDE.md
├── .claude/settings.json         # configuração do Claude Code do projeto (attribution desligado, 14.1)
├── .githooks/commit-msg          # remove qualquer menção a IA dos commits (14.1)
├── docs/                         # especificação dividida + docs/adr/ + docs/deploy.md
├── docker-compose.yml            # perfis: padrão (full), "lite" e "test"
├── Caddyfile
├── scripts/                      # backup.sh, restore.sh, setup-servidor.sh, tunnel.sh
├── .env.example
├── frontend/                     # Angular
│   └── src/app/
│       ├── core/                 # auth, interceptors, guards, cliente da API gerado
│       ├── shared/               # componentes reutilizáveis, glossário/tooltips, pipes de número
│       └── features/
│           ├── projetos/  protocolo/  importacao/  triagem/
│           ├── estudos/  extracao/  risco-vies/  meta-analise/
│           ├── grade/  prisma/  exportacao/  aprendizado/  resumo/
├── backend/                      # FastAPI
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── core/                 # config, segurança, dependências, erros
│       ├── db/                   # sessão, base, mixins (auditoria, soft delete, versão)
│       ├── modules/
│       │   ├── auth/  projects/  protocol/  references/  screening/
│       │   ├── studies/  extraction/  risk_of_bias/  analysis/
│       │   ├── grade/  prisma/  exports/  audit/  comments/  notifications/
│       │   └── (cada módulo: router.py, schemas.py, models.py, service.py, repository.py)
│       ├── integrations/
│       │   ├── stats_client.py   # cliente do serviço R
│       │   ├── storage.py        # interface de armazenamento
│       │   └── ai/               # P2
│       └── workers/              # tarefas da fila
│   └── tests/
├── stats-r/                      # serviço R
│   ├── plumber.R                 # só rotas e validação
│   ├── R/                        # funções puras
│   ├── renv.lock
│   ├── tests/testthat/
│   └── fixtures/                 # valores de referência + scripts que os geram
└── e2e/                          # Playwright
```

### Comandos (criar e documentar aqui quando existirem)
- `docker compose up -d` — sobe tudo
- `cd backend && uv run pytest` / `uv run ruff check .` / `uv run mypy app`
- `cd frontend && npm test` / `npm run lint`
- `cd stats-r && Rscript -e 'testthat::test_dir("tests/testthat")'`
- `scripts/test-e2e.sh` — testes de interface (Playwright, imagem oficial no Docker) contra o sistema no ar; cria contas de teste `@example.org` com senha aleatória e um projeto de demonstração novo. Relatório em `e2e/report/index.html`
- `make seed-demo EMAIL=...` / `scripts/seed-demo.sh <e-mail>` — cria projeto de demonstração com dataset público (`dat.normand1999`) para um usuário existente (também pelo botão em Aprendizado). `scripts/export-demo-data.sh` recopia os dados da fixture do R para o backend
- `scripts/create-user.sh <e-mail> "<nome>"` — cria uma conta já confirmada com senha provisória (mostrada uma vez), sem precisar de e-mail; a pessoa aceita os termos no primeiro acesso
- `scripts/make-admin.sh <e-mail>` — torna uma conta existente administradora do sistema (tela `/admin`: usuários, cotas e situação dos serviços); `--remove` desfaz. Use uma vez para criar o primeiro administrador
- `docker compose --profile lite up -d` — versão leve (1 worker, 1 processo R) para máquinas com pouca RAM
- `scripts/tunnel.sh start` / `stop` / `url` — expõe o sistema local pelo túnel rápido da Cloudflare (10.6): endereço `https://….trycloudflare.com` que muda a cada início; o script grava `.env.tunnel` (endereço público para links, CORS, uploads e cookie seguro) sem mexer no `.env`
- `scripts/backup.sh` / `scripts/restore.sh <arquivo>` — backup criptografado e restauração (10.8); teste: `scripts/test-backup.sh`
- `git config core.hooksPath .githooks` — ativa o hook de commits (rodar uma vez após clonar)
- `scripts/check-commit-messages.sh` — confere se nenhuma mensagem de commit menciona IA (também roda no CI)
- `scripts/test-backend.sh` / `scripts/test-stats-r.sh` — lint, tipos e testes dentro dos containers
- `scripts/export-openapi.sh` — regenera o cliente da API do frontend a partir do backend
- `scripts/generate-fixtures.sh` — regera as fixtures estatísticas rodando o R no contêiner (nunca escrever valores esperados à mão)
- Depois de mudar o `Caddyfile`: `docker compose restart caddy` (a API de admin do Caddy fica desligada, então ele não recarrega sozinho)

---

## 14. Convenções de código
- Código, nomes técnicos e commits em **inglês**; textos da interface em **português do Brasil** (arquivos de i18n, nunca texto fixo em componentes).
- **Python:** módulos por domínio (`router` → `service` → `repository`), schemas Pydantic separados dos models SQLAlchemy, type hints em tudo (`mypy` sem erros), `ruff` para lint e formatação, erros de domínio mapeados para respostas HTTP claras em português, injeção de dependências do FastAPI para sessão e permissões.
- **Angular:** componentes standalone, serviços por feature, formulários reativos, signals para estado simples; nada de chamada HTTP fora do cliente gerado.
- **R:** funções puras em `R/`; `plumber.R` só faz roteamento e validação; `lintr` sem erros.
- Toda decisão de arquitetura relevante vira um ADR curto em `docs/adr/` (ver 14.2).
- Nada de segredos no repositório.
- Repositório **privado** por enquanto. Ainda assim, escrever como se fosse público (sem segredos, README em pt e en, licença definida antes de abrir).

### 14.1 Commits e PRs (regra obrigatória)
- Padrão **Conventional Commits** (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`), em inglês, pequenos e descritivos.
- **Nenhuma menção a IA ou assistente**: sem `Co-Authored-By` de assistente, sem "Generated with...", sem trailer ou link de sessão, sem emojis de robô. Vale para commits, descrições de PR, comentários no código e changelog.
- Três camadas de garantia:
  1. `.claude/settings.json` do projeto com `"attribution": {"commit": "", "pr": ""}` (e a chave equivalente para links de sessão, se a versão do Claude Code tiver; **verificar a documentação atual**, porque já houve versões que adicionavam um trailer de sessão mesmo com attribution vazio).
  2. Hook `.githooks/commit-msg` que **remove** linhas `Co-Authored-By:` com e-mail `@anthropic.com`, linhas `Claude-Session:` e rodapés "Generated with", e falha o commit se ainda sobrar alguma menção.
  3. Esta regra no CLAUDE.md, que o Claude Code deve seguir mesmo que a configuração falhe.
- Teste no CI que varre o histórico do branch e falha se encontrar essas menções.

### 14.2 ADRs iniciais (criar na Etapa 0)
- ADR-001: Backend em Python + FastAPI.
- ADR-002: Toda estatística no serviço R (metafor/robvis).
- ADR-003: Custo zero e implantação por fases (F0 túnel local → F1 Oracle/UFAPE → F2 paga); Vercel + Supabase rejeitados como plataforma principal.
- ADR-004: Arquivos em armazenamento S3 (RustFS, no lugar do MinIO descontinuado) com upload direto em partes e deduplicação por hash.
- ADR-005: Fila `arq` + Redis; progresso por SSE com fallback de polling.
- ADR-006: Autenticação (access token em memória, refresh em cookie httpOnly, Argon2id).
- ADR-007: IA desligada por padrão, camada de provedores trocáveis, citação verificada e métricas de precisão.
- ADR-008: i18n pt-BR/en com idioma das saídas separado do idioma da interface.
- ADR-009: Commits sem menção a IA (settings + hook + regra).

---

## 15. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Erro estatístico silencioso | Resultado errado em congresso | Toda conta no metafor + testes de referência + script R exportável |
| Escopo grande demais para o prazo | Sistema não fica pronto a tempo | Etapas com critério de saída; Etapa 3 pode ser antecipada; P1/P2 só depois |
| Uso indevido de texto dos instrumentos | Problema de licença | Templates sem texto oficial; confirmação com o grupo |
| Dupla contagem de pacientes | Viés no resultado | Modelo estudo × relato + bloqueio na análise |
| Estudos com cortes de idade diferentes | Comparação inválida | Regra no protocolo + subgrupo/sensibilidade |
| Dependência de uma só pessoa para manter | Sistema abandonado | Documentação, ADRs, testes, deploy reproduzível |
| Serviço R fora do ar | Análises indisponíveis | Healthcheck, mensagem clara, fila com retry |
| Perda de dados | Trabalho do grupo perdido | Soft delete, auditoria, backup diário testado, exportação completa |
| Confiança excessiva em sugestões automáticas | Decisões sem julgamento humano | Sugestões marcadas, confirmação obrigatória, justificativa ao discordar |
| DP confundido com EP, sinal trocado ou n errado | Efeito inflado ou invertido | Bloco 7.5.1 inteiro: tipo de dispersão obrigatório, detector, frase de conferência, dupla extração, conferência final |
| Alertas demais (usuário passa a ignorar) | Proteções perdem efeito | Limiares configuráveis, só alertas acionáveis, justificativa curta para dispensar, revisão dos limiares com dados reais |
| Bugs de versão do robvis | Gráfico errado | Commit fixado + testes dos casos conhecidos |
| Deduplicação errada | Estudo perdido ou contado duas vezes | Multicritério, explicação, confirmação humana, remoção reversível |
| Provedor gratuito muda regras ou corta cota (Oracle, Gemini, Cloudflare) | Sistema ou IA fora do ar | Tudo em Docker, camada de provedores de IA, backup fora da hospedagem, script de recriação do servidor |
| Computador do desenvolvedor desligado ou com defeito (F0) | Sistema indisponível ou perda de dados | Testes agendados, backup diário externo, restauração testada |
| IA inventa trecho ou número | Dado errado na revisão | Citação verificada, números inseridos pelo sistema, confirmação humana, métricas de precisão |
| Dados do projeto usados pelo provedor de IA gratuito | Exposição de dados não publicados | IA desligada por padrão, aviso e aceite, contexto mínimo, nada privado enviado |
| Abuso do cadastro aberto (spam, lotar o servidor) | Servidor cheio ou fora do ar | Captcha, verificação de e-mail, cotas, painel de administração |
| PDFs com direito autoral expostos | Problema legal | PDFs sempre privados ao projeto, URLs assinadas curtas, canal de remoção |
| Menção a IA vazar nos commits | Histórico "sujo" | Settings + hook + teste no CI |
