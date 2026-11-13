# CLAUDE.md — Sistema "RevisaMeta"

> Plataforma web única para revisões sistemáticas com meta-análise, pensada para pesquisadores **iniciantes**.
> Junta em um só lugar o que hoje está espalhado em Rayyan, Covidence, RevMan, robvis, JASP/R, GRADEpro e no gerador de fluxograma PRISMA.
> **Foco principal:** evitar os erros humanos que mais estragam meta-análises (ver seção 2.1 e 7.5.1).
> **Situação atual:** sem orçamento. Tudo precisa funcionar com **custo zero** na fase de testes com usuários (seção 10.6). Repositório **privado**. Sistema **aberto ao público** (cadastro livre) e **bilíngue** (português e inglês). Sem prazo: todas as funcionalidades entram, na ordem das etapas.

---

## 0. Instruções para você, Claude Code (leia antes de qualquer coisa)

### 0.1 Como trabalhar neste projeto
1. **Este documento é a fonte da verdade.** Se algo estiver ambíguo ou contraditório, **pare e pergunte** antes de implementar. Não invente regras de domínio.
2. **Na primeira sessão**, antes de escrever código:
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

## 1. Contexto e objetivo

### 1.1 Problema
Uma estudante da área da saúde participa de uma revisão sistemática em grupo, para um resumo que será enviado a um congresso de neurocirurgia. Ela:
- foi colocada na etapa de **avaliação de risco de viés** e não tem experiência;
- considera a **estatística** (meta-análise) a parte mais difícil;
- usa ferramentas separadas, algumas pagas, e arquivos espalhados (Google Drive, um `.docx` de formulário por estudo, planilhas consolidadas).

Pergunta de pesquisa típica do grupo (formato de exemplo, sem dados reais):
> Pessoas com determinada condição que fizeram determinada cirurgia **antes dos 5 anos** tiveram melhor desfecho cognitivo do que as que fizeram **depois dos 5 anos**?

É uma comparação **entre dois grupos dentro de cada estudo** (precoce × tardio). Só entram na meta-análise principal os estudos que reportam os dois grupos. Os estudos provavelmente são **observacionais** (coortes), não ensaios randomizados.

### 1.2 Objetivo do sistema
Um lugar único, simples e guiado, que cubra o fluxo inteiro:

```
Protocolo → Importação → Deduplicação → Triagem → Texto completo → Extração
→ Risco de viés → Meta-análise → Certeza da evidência (GRADE) → PRISMA → Exportação/Resumo
```

O sistema também precisa **receber um projeto já em andamento** (lista final de estudos e avaliações já feitas em planilhas), porque é a situação real do grupo.

### 1.3 Princípios de produto
1. **Guiado:** cada etapa diz o que fazer, o que falta e qual o próximo passo.
2. **Dupla avaliação nativa:** dois revisores independentes + tela de conflitos nas etapas críticas.
3. **Rastreável:** toda decisão tem autor, data, justificativa e, se possível, trecho do PDF.
4. **Reprodutível:** toda análise pode ser exportada como **script R** que reproduz exatamente o resultado.
5. **Correto antes de bonito:** estatística validada contra o `metafor`.
6. **Gratuito e aberto:** sem dependências pagas obrigatórias.
7. **Prevenir erro humano:** o sistema desconfia dos números digitados, aponta o que parece errado e mostra a fonte no PDF ao lado. Este é o maior diferencial em relação às ferramentas existentes.
8. **Digitar uma vez, usar em tudo:** cada dado entra uma única vez e é reaproveitado em todas as análises, subgrupos e exportações.

---

## 2. Ferramentas de referência (o que estamos juntando)

| Ferramenta | O que pegamos dela | Módulo |
|---|---|---|
| **Rayyan** | Triagem rápida, destaque de palavras-chave, cegamento, motivos de exclusão | 7.3 |
| **Covidence** | Fluxo por etapas, conflitos, extração com formulário, contagens para PRISMA | 7.2 a 7.6 |
| **RevMan (Cochrane)** | Tabela "características dos estudos", forest plot, subgrupos | 7.7 |
| **robvis** | Gráficos semáforo (traffic light) e resumo de risco de viés | 7.6 |
| **RoB 2 / ROBINS-I / ROBINS-E (riskofbias.info)** | Domínios, perguntas sinalizadoras, algoritmos de julgamento | 7.6 |
| **JBI Critical Appraisal Tools** | Checklists por desenho (Sim/Não/Incerto/Não se aplica) | 7.6 |
| **Newcastle-Ottawa Scale (NOS)** | Avaliação de coortes e caso-controle por estrelas (muito usada em neurocirurgia) | 7.6 |
| **metafor / meta (R)** | Motor estatístico de referência | 8 |
| **JASP** | Interface de meta-análise "clicar e ver" | 7.7 |
| **Comprehensive Meta-Analysis (CMA)** | Entrada flexível de dados (médias, EP, IC, eventos, t, p) com conversão | 7.5 e 8.4 |
| **GRADEpro** | Tabela Summary of Findings e certeza da evidência | 7.8 |
| **PRISMA 2020 (fluxograma, checklist e PRISMA para resumos)** | Fluxograma automático e acompanhamento dos itens a relatar | 7.9 e 7.14 |
| **Zotero/Mendeley** | Exportação da bibliografia dos estudos incluídos | 7.10 |
| **WebPlotDigitizer** | (P2) Extrair valores de gráficos de artigos | 7.5 |

**Diferencial do RevisaMeta:** tudo integrado + **proteções contra erro de extração** + importação de projetos em andamento + Modo Aprendizado + script R exportável + gratuito.

### 2.1 Lições dos concorrentes (reclamações de usuários e estudos metodológicos)

Levantamento feito em fóruns, avaliações de usuários, issues do GitHub e artigos sobre as ferramentas. Cada problema virou um requisito.

| # | Problema encontrado | Onde | Requisito no RevisaMeta | Seção |
|---|---|---|---|---|
| L1 | Ferramentas fragmentadas: triagem/extração não fazem estatística; estatística não organiza a revisão | Covidence, Rayyan, RevMan | Fluxo completo em um lugar | 1.2 |
| L2 | Exportação da extração sai **em branco** se a etapa de consenso foi pulada | Covidence | Aviso antes de exportar + opção explícita de exportar extrações individuais | 7.10 |
| L3 | Modelo padrão de qualidade baseado em instrumento antigo (RoB 1) | Covidence | Instrumentos atuais com versão registrada | 7.6 |
| L4 | Deduplicação com muitos **falsos positivos** (compara só o começo do título; "Parte 1" e "Parte 2" viram duplicata) e duplicatas reais que passam | Rayyan | Deduplicação multicritério, explicada e sempre confirmada por humano | 7.2 |
| L5 | Lista de motivos de exclusão só cresce; não dá para apagar | Rayyan | Motivos editáveis (com histórico) | 7.4 |
| L6 | Sem **desfazer** a última decisão de triagem | Covidence (pedido de usuários) | Desfazer | 7.3 |
| L7 | Não dá para guardar referências excluídas mas úteis como contexto | Covidence (pedido de usuários) | Marcador "útil como referência" | 7.3 |
| L8 | Opções diferentes no celular e no computador (Sim/Não/Pular × Sim/Não/Talvez) | Covidence | Mesmas opções em qualquer tela | 7.3 e 10.3 |
| L9 | Não dá para dividir a triagem em lotes por coautor | Covidence (pedido de usuários) | Atribuição de lotes | 7.3 |
| L10 | Sem meta-regressão, sem rede, viés de publicação só visual; versão antiga presa ao estimador DerSimonian-Laird | RevMan | Motor metafor com estimador selecionável; Egger, leave-one-out, meta-regressão (P2) | 7.7 |
| L11 | Aceita só uma média e um DP: usuário com linha de base + final não sabe o que fazer | RevMan (fóruns) | Campos separados para valor final e mudança, com orientação | 7.5 |
| L12 | Subgrupos obrigam a **digitar os mesmos dados várias vezes**, gerando erros de cópia | RevMan | Digitar uma vez, reutilizar em todas as análises | 1.3 e 7.7 |
| L13 | Usuários travam ao inserir efeitos ajustados (HR/OR com IC) | RevMan (fóruns) | Entrada "efeito + IC" com conversão automática para log e EP | 7.5 e 8.5 |
| L14 | **Erros de extração são comuns e mudam conclusões**: em meta-análises com SMD, uma parte relevante não pôde ser replicada por n, média, DP ou sinal errados; a concordância entre extratores é baixa | Estudos metodológicos | Proteções anti-erro como prioridade máxima | 7.5.1 |
| L15 | **Confundir DP com EP** é um dos erros mais comuns e pode inflar muito o efeito | Estudos metodológicos | Tipo de dispersão obrigatório + detector de EP suspeito | 7.5.1 |
| L16 | robvis da versão CRAN quebra com "Sem informação" no ROBINS-I; rótulos sobrepostos | robvis (issues) | Versão fixada do GitHub + testes desses casos | 7.6 e 11.2 |
| L17 | robvis não tem template para JBI nem Newcastle-Ottawa (só o genérico) | robvis | Template genérico configurado ou gráfico próprio | 7.6 |
| L18 | Pedido antigo e popular: **forest plot com o semáforo de risco de viés ao lado** | robvis (issues) | Gráfico combinado | 7.7 |
| L19 | Custo: sem plano gratuito permanente | Covidence, CMA | Gratuito | 1.3 |

Regra para o Claude Code: ao implementar um módulo, consulte esta tabela e garanta que os requisitos ligados a ele estão cobertos.

---

## 3. Stack técnica

### 3.1 Decisão
| Camada | Tecnologia | Motivo |
|---|---|---|
| Frontend | **Angular** (versão LTS atual), **PrimeNG** (tabelas com filtro, ordenação e rolagem virtual), **Transloco** (i18n pt-BR/en), `ngx-extended-pdf-viewer` (PDF.js) | Stack que o desenvolvedor domina; tabelas fortes para triagem e extração |
| Backend | **Python 3.12 + FastAPI**, Pydantic v2, **SQLAlchemy 2.0 assíncrono (asyncpg)**, Alembic | Rápido de desenvolver; muito I/O; ecossistema forte para dados, PDFs, importação e IA |
| Autenticação | JWT: access token curto **só em memória no front** + refresh token rotativo em **cookie httpOnly/Secure/SameSite**; senhas com **Argon2id** (`argon2-cffi`) | Evita tokens no localStorage |
| Banco | **PostgreSQL 16** com `unaccent`, `pg_trgm` e busca textual (pt/en) | Relacional + JSONB + busca nas referências sem Elasticsearch |
| IDs | **UUID v7** | Ordenáveis por tempo, melhores para índices |
| Armazenamento de arquivos | **MinIO** (compatível com S3) no Docker Compose | Upload direto em partes por URL assinada (10.7); migra para qualquer S3 sem mudar código |
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
| Ler PDF (texto, busca, páginas) | `PyMuPDF` |
| Ler planilhas e CSV | `pandas`, `openpyxl` |
| Exportar Word / Excel | `python-docx`, `openpyxl` |
| Cliente HTTP do serviço R | `httpx` (com timeout e retry) |
| E-mail (convites, senha) | `fastapi-mail` ou SMTP simples |
| Fila e tarefas | `arq` |
| Rate limiting | `slowapi` |
| Cliente S3/MinIO (URLs assinadas, multipart) | `boto3` ou `aioboto3` |
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
├── docker-compose.yml            # perfis: padrão e "lite"
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
- `cd e2e && npx playwright test`
- `make seed-demo` — cria projeto de demonstração com dataset público
- `docker compose --profile lite up -d` — versão leve (1 worker, 1 processo R) para máquinas com pouca RAM
- `make tunnel` — expõe o sistema local pelo Cloudflare Tunnel (10.6)
- `make backup` / `make restore` — backup criptografado e restauração (10.8)
- `git config core.hooksPath .githooks` — ativa o hook de commits (rodar uma vez após clonar)

---

## 5. Glossário de domínio (usar na interface e no Modo Aprendizado)

| Termo | Explicação simples |
|---|---|
| Revisão sistemática | Estudo que reúne todos os estudos sobre uma pergunta, seguindo um método fixo e transparente |
| Meta-análise | Parte estatística que combina os números de vários estudos em um resultado único |
| PICO / PECO | População, Intervenção (ou Exposição), Comparação, Outcome (desfecho) |
| Protocolo / PROSPERO | Plano registrado antes de começar, para evitar mudar regras no meio |
| Emenda ao protocolo | Mudança no plano depois de começar; precisa ser registrada e justificada |
| Triagem | Ler título/resumo e decidir se o estudo pode servir |
| Texto completo | Segunda triagem, lendo o artigo inteiro |
| Estudo × relato | Um mesmo estudo (mesmos pacientes) pode ter vários artigos publicados |
| Extração de dados | Copiar do artigo os números necessários (n, média, DP, eventos...) |
| Risco de viés | Avaliar se o jeito como o estudo foi feito pode ter distorcido o resultado |
| Domínio (RoB) | Uma área avaliada (ex.: confundimento, dados faltantes) |
| Pergunta sinalizadora | Pergunta que ajuda a julgar um domínio |
| Confundimento | Outro fator que influencia tanto o grupo quanto o desfecho e distorce a comparação |
| Estimativa ajustada | Resultado corrigido para fatores de confusão (comum em estudos observacionais) |
| Medida de efeito | Número que resume a diferença entre grupos (MD, SMD, OR, RR) |
| SMD / g de Hedges | Diferença de médias padronizada; usada quando estudos medem com escalas diferentes |
| IC 95% | Faixa onde o valor verdadeiro provavelmente está |
| Efeito fixo | Supõe que todos os estudos medem o mesmo efeito verdadeiro |
| Efeitos aleatórios | Supõe que o efeito verdadeiro varia entre estudos (mais comum na prática) |
| Heterogeneidade | Quanto os resultados dos estudos diferem entre si |
| I² | % da variação entre estudos que não é explicada pelo acaso |
| τ² (tau²) | Variância do efeito verdadeiro entre estudos |
| Intervalo de predição | Faixa onde provavelmente cairia o efeito de um novo estudo |
| Forest plot | Gráfico com o resultado de cada estudo e o combinado (losango) |
| Funnel plot | Gráfico para investigar viés de publicação |
| Sensibilidade | Refazer a análise mudando algo para ver se o resultado se mantém |
| Subgrupo | Analisar separado por característica (ex.: tipo de cirurgia) |
| Meta-regressão | Ver se uma característica numérica dos estudos (ex.: idade média) explica a diferença nos resultados |
| Unidade de análise | Garantir que os mesmos pacientes não sejam contados duas vezes |
| GRADE | Classifica a certeza da evidência (alta, moderada, baixa, muito baixa) |
| PRISMA | Diretriz de como relatar a revisão; inclui fluxograma e checklist |

---

## 6. Usuários, papéis e acesso

| Papel | Pode |
|---|---|
| **Administrador do projeto** | Criar projeto, convidar membros, configurar protocolo, formulários e instrumentos, resolver conflitos, travar etapas, registrar emendas |
| **Revisor** | Triar e avaliar risco de viés; com cegamento ativo, vê só as próprias decisões |
| **Extrator** | Extrair dados nos formulários |
| **Estatístico** | Configurar e rodar análises, exportar resultados |
| **Leitor** | Ver tudo, sem editar (ex.: orientador) |

Regras:
- Um usuário pode ter vários papéis no mesmo projeto e participar de vários projetos.
- **Convites** por link com expiração (e-mail opcional no MVP: o admin pode copiar o link).
- **Recuperação de senha** por e-mail (P1; no MVP, o admin do sistema redefine).
- **Cegamento:** enquanto ativo, um revisor não vê as decisões do outro naquela etapa, nem pela API. O admin revela quando os dois terminaram.
- Toda ação de escrita gera registro na **auditoria**.
- O criador do projeto não pode ser removido sem transferir a administração.

**Sistema aberto ao público (cadastro livre):**
- Cadastro com **verificação de e-mail** e **captcha gratuito** (Cloudflare Turnstile).
- **Cotas por usuário e por projeto** configuráveis pelo administrador do sistema (ex.: número de projetos, espaço de PDFs, uso de IA por dia), com painel de uso. Sem cotas, um único usuário pode lotar o servidor gratuito.
- Papel global **administrador do sistema** (diferente do admin de projeto): gerencia cotas, usuários, denúncias e status; **não** acessa o conteúdo dos projetos sem ser membro.
- Aviso permanente de **"versão beta, sem garantia de disponibilidade"** enquanto estiver na infraestrutura gratuita.
- Canal de contato para pedidos de remoção (direitos autorais, LGPD).

---

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
2. Dois revisores avaliam de forma independente (cegados), com PDF ao lado.
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

### 7.15 IA assistiva (P1/P2, desligada por padrão)

> **Filosofia:** IA sozinha não é diferencial; quase todos os concorrentes já têm. O diferencial é **IA em que dá para confiar**: mostra a prova, é verificada automaticamente, é medida contra os humanos e ensina. Em revisão sistemática, uma IA que inventa um número é pior que nenhuma IA.

#### 7.15.1 Onde a IA entra (por ordem de prioridade e segurança)
| # | Função | O que faz | Prioridade |
|---|---|---|---|
| IA1 | **Tutor** | Chat que explica conceitos e **os resultados do próprio projeto** ("o que significa meu I² de 68%?"). Recebe os números já calculados pelo R e só explica. | P1 |
| IA2 | **Localizador de trechos** | "Onde o artigo fala de cegamento?", "onde está o DP do grupo controle?" → aponta página e trecho; a pessoa lê e decide. | P1 |
| IA3 | **Extração assistida** | Sugere valores **com citação exata**; lê legendas/rodapés e avisa "este valor parece ser EP, não DP" (reforça 7.5.1). | P2 |
| IA4 | **Segunda opinião em risco de viés** | Sugere respostas às perguntas sinalizadoras com o trecho que justifica. | P2 |
| IA5 | **Ajuda na estratégia de busca** | Sugere termos MeSH/DeCS e combinações para PubMed/LILACS; humano revisa e roda a busca. | P2 |
| IA6 | **Rascunho de Métodos/Resultados e do resumo** | Gera estrutura e texto; **os números são inseridos pelo sistema**, nunca escritos pela IA. | P2 |

A priorização de triagem (7.3) **não usa LLM**: é aprendizado de máquina clássico, local e gratuito.

#### 7.15.2 Onde a IA nunca entra
- Cálculos estatísticos (sempre o serviço R).
- Decisão final de inclusão/exclusão.
- Julgamento final de risco de viés.
- Qualquer número sem fonte verificada.

#### 7.15.3 Regras de segurança contra alucinação
1. **Citação verificada:** toda sugestão de IA2, IA3 e IA4 vem com a frase exata do PDF e a página. O backend confere se a frase existe no texto extraído do PDF (comparação normalizada, tolerando quebras de linha e hifenização). **Se não existir, a sugestão é descartada** e registrada como falha.
2. **Números do tutor e dos rascunhos:** a IA recebe os resultados como dados estruturados e escreve com marcadores (ex.: `{{pooled_effect}}`); o sistema substitui pelos valores reais. Se o texto da IA contiver um número que não veio dos dados, ele é sinalizado.
3. **Sugestão nunca é dado final:** campo fica "sugerido pela IA" até confirmação humana; o histórico registra a origem.
4. **Saída estruturada** (JSON com schema validado por Pydantic); resposta fora do schema é descartada.
5. **Contexto mínimo:** só os trechos/páginas necessários vão para o provedor, nunca o projeto inteiro.
6. **Prompt injection:** texto de PDF é tratado como dado, nunca como instrução; instruções do sistema separadas do conteúdo.

#### 7.15.4 Precisão medida (diferencial)
- Como há dupla avaliação humana, o sistema compara as sugestões da IA com o **consenso** dos revisores e mostra a taxa de acerto por tipo de tarefa e por projeto (ex.: "nas últimas 50 extrações, a IA acertou 46").
- Quando a precisão de uma função cair abaixo de um limiar configurável, ela é desativada para o projeto com aviso.
- Essas métricas entram na declaração de uso de IA exportável para o manuscrito.

#### 7.15.5 Provedores e custo zero
- **Camada de provedores** (interface única: `complete`, `complete_structured`, `embed`) com adaptadores trocáveis por configuração. Primeiro adaptador: **API gratuita do Gemini**. Previstos: DeepSeek, OpenAI-compatível genérico e **modelo local via Ollama** (para quem tiver máquina).
- **Aviso obrigatório de uso de dados:** no plano gratuito do Gemini, o Google pode usar prompts e respostas para melhorar os próprios produtos. Por isso:
  - a IA fica **desligada por padrão** em todo projeto;
  - para ligar, o admin do projeto lê e aceita um aviso claro (em pt e en) dizendo o que é enviado e para quem; o aceite fica na auditoria;
  - anotações privadas, comentários e dados ainda não publicados **nunca** são enviados; só trechos de artigos já publicados e resultados que o usuário pediu para explicar.
- **Limites do plano gratuito:** todas as chamadas passam pela fila, com controle de taxa global; ao atingir a cota, o sistema avisa e a função fica indisponível até renovar, sem quebrar o resto.
- **Cota de IA por usuário/dia** (6) para dividir o plano gratuito entre os usuários.
- **Cache** de respostas por (trecho, tarefa, versão do prompt) para não gastar cota duas vezes.
- Prompts versionados em arquivos (`backend/app/integrations/ai/prompts/`), com versão registrada em cada sugestão.
- Termos de uso de cada provedor revisados antes de ativar (alguns exigem 18+ ou restringem regiões).

#### 7.15.6 Interface
- Ícone e cor próprios para tudo que veio da IA; botão "ver trecho no PDF" em toda sugestão.
- Botões "aceitar", "corrigir" e "rejeitar" (os três alimentam a métrica 7.15.4).
- Tutor disponível em todas as telas pelo Modo Aprendizado, respondendo no idioma da interface.
- Exportar **declaração de uso de IA** para o manuscrito (funções usadas, provedor, versão do prompt, taxa de acerto, confirmação humana).

---

## 8. Motor estatístico (serviço R)

### 8.1 Regras
- O backend Python **nunca** calcula estatística: envia dados ao serviço R e recebe resultados e gráficos.
- O serviço R usa **`metafor`** como referência principal (`escalc`, `rma`, `leave1out`, `regtest`, `funnel`, `forest`, `predict`, funções de conversão `conv.*`), **`robvis`** para gráficos de risco de viés, **`meta`** quando necessário e **`irr`** para kappa.
- Versões fixadas com `renv` (robvis por commit do GitHub, ver 7.6). Toda resposta inclui versão do R e dos pacotes, parâmetros usados e avisos.
- O serviço R é **stateless** e **sem acesso ao banco**.

### 8.2 Contrato entre Python e R
- JSON com schema definido nos dois lados (Pydantic no Python; validação explícita no `plumber.R`).
- Resposta padrão: `{ "ok": bool, "result": {...}, "warnings": [...], "errors": [...], "meta": { "r_version", "packages", "params" } }`.
- Timeouts e retry no `httpx`; se o R estiver fora do ar, a interface mostra mensagem clara e nada é salvo como resultado.
- Gráficos retornam como arquivo (SVG/PNG) que o Python grava no armazenamento.
- Testes de contrato nos dois lados.

### 8.3 Endpoints (sugestão)
| Método | Rota | Função |
|---|---|---|
| POST | `/effect-sizes` | Efeito e variância por estudo (`escalc`) |
| POST | `/meta-analysis` | Modelo (`rma`), estimativas, heterogeneidade, predição |
| POST | `/forest-plot` | PNG/SVG |
| POST | `/funnel-plot` e `/egger` | Viés de publicação |
| POST | `/leave-one-out` | Sensibilidade |
| POST | `/subgroup` | Subgrupos e teste de diferença |
| POST | `/meta-regression` | P2 |
| POST | `/convert` | Conversões (8.5) |
| POST | `/combine-groups` | Combina braços em um grupo |
| POST | `/rob-plots` | Semáforo e resumo (`robvis`) |
| POST | `/plausibility-checks` | Detector de EP no lugar de DP, recálculo de p/IC, valores fora da escala (7.5.1) |
| POST | `/influence` | Diagnóstico de influência e efeitos improváveis (7.5.1) |
| POST | `/forest-rob-plot` | Forest plot com semáforo ao lado (P1) |
| POST | `/kappa` | Concordância entre revisores |
| POST | `/r-script` | Script R reprodutível |
| GET | `/health` | Status + versões |

### 8.4 Referência das medidas e modelos (para documentação e conferência, não para reimplementar)
- Medidas (`escalc`): `MD`, `SMD` (g de Hedges, com correção para amostra pequena), `ROM` (opcional), `OR`, `RR`, `RD`.
- Efeito fixo: média ponderada pelo inverso da variância.
- Efeitos aleatórios: pesos `1/(vᵢ + τ²)`; estimadores de τ²: **REML (padrão)**, DerSimonian-Laird e Paule-Mandel.
- Heterogeneidade: Q de Cochran, I², H², τ².
- IC: Wald (padrão) ou **Hartung-Knapp** (`test="knha"`), recomendado com poucos estudos.
- Intervalo de predição: `predict()`.
- Células zero: correção de continuidade conforme padrão do `escalc`, documentada na saída.

### 8.5 Conversões de dados (sempre registrar método e valor original)
| Entrada | Saída | Método |
|---|---|---|
| EP da média | DP | DP = EP × √n |
| IC 95% da média | DP | Pela largura do IC, com distribuição t para amostras pequenas (Cochrane Handbook) |
| Mediana + IIQ e/ou mínimo/máximo | Média e DP | **Wan et al. (2014)** e **Luo et al. (2018)** (ver `conv.fivenum` do metafor); marcar como "estimado" |
| Estatística t ou valor p exato (dois grupos) | SMD | Fórmulas padrão de conversão; marcar como "derivado" |
| Vários braços → um grupo | n, média e DP combinados | Fórmula do Cochrane Handbook |
| Efeito + IC (ex.: OR ajustado) | yᵢ e vᵢ | Log da medida; EP pela largura do IC na escala log (ver `conv.wald`) |
| OR ↔ SMD | Para combinar contínuos e dicotômicos | P2, só com aprovação explícita e aviso |

---

## 9. Modelo de dados (rascunho — refinar e propor diagrama ER antes de implementar)

Toda tabela de negócio tem: `id` (UUID), `project_id` (quando aplicável), `created_at`, `updated_at`, `created_by`, `deleted_at` (soft delete) e `version` (**trava otimista**: duas pessoas editando o mesmo registro não sobrescrevem uma à outra).

```
user(id, name, email, password_hash, is_active)
project(id, title, question, pico_jsonb, prospero, deadline, analysis_plan_jsonb, locked_stages[])
project_member(project_id, user_id, roles[])
invitation(id, project_id, email, roles[], token_hash, expires_at, accepted_at)
protocol_amendment(id, project_id, description, reason, approved_by, date)
criterion(id, project_id, kind[inclusion|exclusion], text, order)
outcome(id, project_id, name, type[continuous|dichotomous], higher_is_better, primary, timepoints[])
comparison_group(id, project_id, label, rule_description)        -- ex.: "< 5 anos"

search(id, project_id, database, search_date, strategy)
reference(id, project_id, search_id, title, abstract, authors, year, doi, journal, duplicate_of)
screening_decision(id, reference_id, user_id, stage[title_abstract|full_text], decision, exclusion_reason)
conflict(id, project_id, entity, entity_id, status, resolved_by, resolution)

study(id, project_id, label, design)                                -- ex.: "Ballet 2025"
report(id, study_id, reference_id, is_primary)                      -- vários artigos → um estudo
pdf_file(id, reference_id, storage_key, sha256, uploaded_by)
pdf_annotation(id, pdf_id, user_id, page, coords_jsonb, text, color)
author_contact(id, study_id, requested, sent_at, answered_at, notes)

extraction_form(id, project_id, version, schema_jsonb)
extraction(id, study_id, form_id, user_id, data_jsonb, status, is_consensus)
study_arm(id, study_id, label, n, description, mapped_group_id)    -- braços originais do estudo
outcome_data(id, study_id, outcome_id, arm_id, timepoint, value_type[final|change],
             n, mean, sd, se, ci_low, ci_high, median, q1, q3, min, max, events, total,
             t_stat, p_value, effect_reported_jsonb, adjusted, adjusted_for,
             converted_jsonb, conversion_method, source[article|author|digitizer|ai],
             source_page, annotation_id, extracted_by, confirmed)

rob_tool(id, name, version, target_design, template_jsonb)
rob_assessment(id, study_id, outcome_id NULL, timepoint NULL, tool_id, user_id, status)
rob_answer(id, assessment_id, domain, question, answer, justification, annotation_id)
rob_judgement(id, assessment_id, domain NULL, suggested, final, justification)   -- domain NULL = geral
rob_consensus(id, study_id, outcome_id NULL, tool_id, domain NULL, judgement, decided_by, reason)

analysis(id, project_id, outcome_id, timepoint, measure, model, estimator, ci_method,
         filters_jsonb, included_study_ids[], input_snapshot_jsonb, result_jsonb,
         r_meta_jsonb, planned, created_by)
figure(id, project_id, analysis_id NULL, kind, format, storage_key)

grade_assessment(id, project_id, outcome_id, start_certainty, approach, adjustments_jsonb, final_certainty, justification)
prisma_count(project_id, key, value, manually_adjusted, justification)
prisma_checklist_item(project_id, item_code, status, location_in_manuscript)
comment(id, project_id, entity, entity_id, user_id, text)
notification(id, user_id, project_id, kind, payload_jsonb, read_at)
audit_log(id, project_id, entity, entity_id, field, old_value, new_value, user_id, created_at)

stored_file(id, sha256, size_bytes, mime, storage_key, ref_count)       -- deduplicação por hash (10.7)
upload_session(id, user_id, project_id, filename, size_bytes, parts_done, status, expires_at)
background_job(id, project_id, kind, status, progress, result_jsonb, error, created_by)
usage_quota(user_id, kind, period, used, limit)                         -- projetos, armazenamento, IA
ai_settings(project_id, enabled, provider, accepted_terms_by, accepted_at, functions_enabled[])
ai_suggestion(id, project_id, task[tutor|locate|extract|rob|search|draft], target_entity, target_id,
              payload_jsonb, quote, page, quote_verified, prompt_version, provider, model,
              status[suggested|accepted|corrected|rejected|discarded], decided_by, decided_at)
user_preference(user_id, ui_language[pt-BR|en], number_format)
```

---

## 10. Requisitos não funcionais

### 10.1 Segurança
- JWT de curta duração + refresh token rotativo; logout invalida o refresh.
- Senhas com bcrypt/argon2; política mínima de senha.
- Autorização por **papel e por projeto** em todo endpoint (dependência do FastAPI reutilizável).
- Upload: só PDF (checar tipo real, não só a extensão), limite de tamanho, hash SHA-256, nome de arquivo gerado pelo sistema (evita path traversal).
- CORS restrito ao domínio do frontend; rate limiting no login.
- Segredos só em `.env`; `.env.example` sem valores reais.
- Cabeçalhos de segurança (CSP, HSTS quando houver HTTPS próprio, X-Content-Type-Options, frame-ancestors).
- PDFs exibidos sem executar JavaScript embutido; arquivos servidos só por URL assinada de curta duração.
- Captcha (Turnstile) no cadastro e após falhas de login; verificação de e-mail obrigatória.
- Varredura de dependências no CI (Dependabot, `pip-audit`, `npm audit`) e de segredos (`gitleaks`).
- Chaves de API de IA só no servidor, nunca no frontend.
- 2FA opcional (P2).
- **Postgres, Redis e MinIO nunca expostos** para fora da rede do Docker.

### 10.2 Privacidade (LGPD)
- Os dados dos estudos são agregados e publicados, mas há dados de usuários: coletar o mínimo, permitir exclusão da conta e exportação do projeto.
- Termos de uso e aviso de privacidade simples antes de publicar.
- PDFs ficam no projeto e só membros acessam (URLs assinadas ou rota autenticada). **PDFs de artigos têm direito autoral: nunca ficam públicos**, nem por link compartilhável.
- Como o sistema é aberto ao público: **termos de uso e política de privacidade** (pt e en) aceitos no cadastro, com versão registrada; exclusão de conta e exportação de dados pelo próprio usuário; prazo de retenção de projetos inativos definido (10.8).
- Aviso claro sobre o envio de dados a provedores de IA (7.15.5).

### 10.3 Usabilidade e acessibilidade
- **Bilíngue: português do Brasil e inglês** em toda a interface, Modo Aprendizado, glossário, e-mails, mensagens de erro, termos de uso e exportações. Idioma escolhido por usuário e detectado do navegador no primeiro acesso.
- **Idioma das saídas separado do idioma da interface:** forest plot, gráficos de risco de viés, tabelas, PRISMA e SoF podem ser gerados em pt ou en, independentemente de como o usuário usa o sistema (ex.: usar em português e exportar o forest plot em inglês para o congresso). O serviço R recebe o idioma como parâmetro.
- Formato de número segue o idioma das saídas (vírgula em pt, ponto em en), configurável.
- Interface responsiva (triagem e consulta no celular; extração e risco de viés pensados para tela grande).
- **Números:** exibição com vírgula decimal; entrada aceita vírgula e ponto; armazenamento sempre numérico; casas decimais configuráveis (padrão 2 na tela, precisão total no banco).
- Contraste adequado, navegação por teclado, labels em todos os campos; cores do semáforo **sempre** acompanhadas de rótulo em texto.
- **Mesmas opções e mesma lógica em celular e computador** (lição L8): o layout muda, as escolhas não.

### 10.4 Desempenho e confiabilidade
- Triagem fluida com milhares de referências (paginação e carregamento sob demanda).
- Tarefas longas na fila com indicador de progresso.
- Backup diário do banco e dos arquivos; procedimento de restauração testado.
- Nenhuma exclusão definitiva de decisões (soft delete).

### 10.5 Observabilidade
- Logs estruturados (JSON) com id de requisição propagado do Python ao R.
- Healthcheck de todos os serviços; página de status para o admin.

### 10.6 Implantação por fases (custo zero agora, expansão depois)

**Princípio:** o mesmo Docker Compose roda em qualquer lugar. Mudar de fase é copiar a configuração, restaurar o backup e apontar o endereço, sem reescrever código.

| Fase | Onde roda | Endereço | Quando |
|---|---|---|---|
| **F0 — Testes com usuários (atual)** | Computador do desenvolvedor | **Cloudflare Tunnel**: primeiro o túnel rápido (`trycloudflare.com`, sem conta), depois um túnel nomeado com domínio próprio | Sessões de teste agendadas com a Larissa e o grupo |
| **F1 — Beta contínuo** | **Oracle Cloud Always Free** (ARM, 2 OCPU / 12 GB) **ou** servidor/VM da UFAPE | Domínio próprio, HTTPS pelo Caddy, Cloudflare gratuito na frente | Quando houver uso fora das sessões agendadas |
| **F2 — Produção** | VPS paga ou serviços gerenciados | Domínio próprio | Só se houver verba e uso que justifique |

**Fase F0 — regras e limitações conhecidas**
- O sistema só fica no ar com o computador ligado; os testes são agendados.
- Túnel rápido: endereço muda a cada reinício, limite de 200 requisições simultâneas e **sem suporte a SSE** → por isso o fallback de polling é obrigatório (3.1). O túnel nomeado não tem essas limitações; usar assim que houver domínio.
- No túnel, a aplicação recebe o host do túnel: configurar hosts permitidos e CORS por variável de ambiente.
- Perfil `lite` disponível se o computador não aguentar a pilha completa (meta: rodar com 6 a 8 GB de RAM livres).
- Upload de PDFs grandes limitado pela velocidade de upload da internet do desenvolvedor.
- Backup diário para fora da máquina (10.8), porque perder o computador seria perder os dados de teste.

**Fase F1 — cuidados com o Oracle Always Free (para quando chegar a hora)**
- Pede cartão só para verificação; cartões brasileiros às vezes são recusados → plano B: servidor da UFAPE.
- A região principal não pode ser trocada depois; regiões concorridas podem dar "sem capacidade" (tentar de novo com script).
- Criar a máquina já dentro da cota gratuita desde o primeiro dia (máquinas acima da cota são desativadas ao fim do teste).
- Instâncias com uso muito baixo por muito tempo podem ser recuperadas pela Oracle: manter backup diário e o script `setup-servidor.sh` que recria o servidor do zero.
- Imagem Ubuntu da Oracle tem firewall próprio além das regras do painel: liberar 80/443 nos dois.
- O plano gratuito da Cloudflare limita cada requisição a 100 MB: o upload em partes (10.7) já resolve.
- Orçamento de memória aproximado: Postgres ~2 GB, Redis ~256 MB, FastAPI ~500 MB, worker ~1 GB, R ~1 GB por processo (2 processos), MinIO ~512 MB, Caddy e sistema ~1 GB.

**Comum a todas as fases**
- HTTPS sempre que exposto à internet (túnel ou Caddy).
- Migrations do Alembic rodam no deploy; nunca alterar o banco à mão.
- Deploy com verificação de `/health` e volta automática para a versão anterior se falhar (F1+).
- CI no GitHub Actions só com lint e testes (repositório privado tem minutos limitados); imagens construídas no próprio servidor na F1.
- Monitoramento gratuito e **fora** do servidor: UptimeRobot ou Healthchecks.io (disponibilidade e backup do dia) + Sentry no plano gratuito (erros).
- E-mail transacional gratuito (Brevo ou similar) com SPF/DKIM configurados quando houver domínio; na F0, convites podem ser copiados como link.
- Passo a passo completo em `docs/deploy.md`, incluindo como migrar de fase.

### 10.7 Arquivos grandes
- **Upload direto ao armazenamento:** o backend gera URLs assinadas e o navegador envia o arquivo **em partes** (multipart, ~8 a 16 MB por parte) direto ao MinIO, sem passar o arquivo pelo FastAPI. Se a conexão cair, o envio **retoma** das partes que faltam (`upload_session`).
- Limite por PDF configurável (padrão **100 MB**); limite total por projeto e por usuário conforme as cotas (6).
- **Deduplicação por hash:** o mesmo PDF enviado duas vezes é guardado uma vez só (`stored_file` com `ref_count`).
- O banco guarda só metadados (nome, hash, tamanho, tipo), nunca o conteúdo.
- **Visualização progressiva:** PDF.js com requisições por faixa (HTTP Range); um PDF de 80 MB abre sem baixar tudo.
- **Processamento em segundo plano** (worker): extração de texto, contagem de páginas, verificação de tipo real e, na P2, OCR (`ocrmypdf`) de PDFs escaneados, com progresso na tela.
- **Importações grandes** (milhares de referências, planilhas grandes) lidas em fluxo e gravadas em lotes; relatório de erros por linha sem parar a importação inteira.
- **Exportações grandes** (ZIP do projeto, todos os PDFs) geradas pelo worker como arquivo e baixadas por URL assinada, nunca montadas na memória da requisição.
- Painel de uso de espaço por projeto e por usuário.
- Testes com arquivos grandes sintéticos (ex.: PDF de 100 MB, RIS com 20 mil registros) e com queda de conexão no meio do upload.

### 10.8 Backup, recuperação e retenção
- `pg_dump` diário + cópia incremental dos arquivos do MinIO, **criptografados** antes de sair da máquina.
- Destino gratuito **fora da hospedagem**: Google Drive do responsável via `rclone` (padrão) ou Backblaze B2.
- Retenção: 7 diários, 4 semanais, 3 mensais.
- Healthchecks.io avisa se o backup do dia não rodou.
- **Teste de restauração** documentado e executado antes de cada mudança de fase.
- Retenção de projetos: projetos sem acesso há muito tempo recebem aviso por e-mail e podem ser arquivados (prazo a definir, 17).

---

## 11. Validação e testes (critério de "pronto")

### 11.1 Testes de referência estatística (obrigatórios)
1. Em `stats-r/fixtures/`, um script roda o `metafor` com datasets públicos (`dat.bcg` para dicotômico e pelo menos um dataset contínuo do próprio pacote) e salva os resultados esperados em JSON: estimativa, EP, IC, τ², I², Q, intervalo de predição, para REML, DL, efeito fixo e com/sem Hartung-Knapp.
2. Testes `testthat` comparam a saída de cada endpoint com as fixtures (tolerância de 1e-6).
3. Teste de integração no Python: mesmos dados pela API → mesmo resultado da fixture.
4. Teste E2E: mesmos dados pela interface → mesmo resultado na tela.
5. O script R exportado, rodado em um R limpo, reproduz os mesmos números.
6. Conferência cruzada opcional com uma segunda implementação (ex.: `meta` ou `PyMARE`) para pegar erros de configuração.

### 11.2 Testes de domínio
- Algoritmos de julgamento RoB 2/ROBINS-I: tabela de casos (combinações de domínios → julgamento geral esperado).
- Regras configuráveis de JBI/NOS.
- Inversão de direção da escala.
- Conversões (8.5) e combinação de braços: casos com valores calculados no R.
- Bloqueios: estudo duplicado na análise; SMD com mistura de final e mudança; k < 2.
- Cegamento: revisor A não lê decisões do revisor B via API enquanto ativo.
- Isolamento: usuário de um projeto não acessa dados de outro (todo endpoint).
- Trava otimista: edição simultânea gera conflito, não sobrescrita.
- Importação/migração: arquivos com colunas faltando, vírgula decimal, linhas inválidas.
- **Proteções anti-erro (7.5.1)** com casos sintéticos: EP digitado como DP (deve gerar alerta); p reportado incompatível com média/DP/n (alerta); sinal invertido em escala "maior é pior"; soma dos braços maior que o total (bloqueio); dupla extração com diferença numérica real (divergência) e só de formatação (sem divergência); correção de um dado marca análises como desatualizadas.
- **Deduplicação:** "Parte 1" × "Parte 2", errata × artigo original e títulos que diferem só no fim **não** viram duplicata; mesmo DOI sempre vira.
- **robvis:** ROBINS-I com "Sem informação" e "Grave" no mesmo gráfico renderiza as duas categorias corretamente; muitos estudos e nomes longos sem sobreposição de rótulos.
- **Exportação sem consenso:** gera aviso e nunca arquivo em branco.
- **Triagem:** desfazer restaura a decisão anterior e registra na auditoria.
- **IA:** citação inexistente no PDF é descartada; número no texto da IA que não veio dos dados é sinalizado; resposta fora do schema é descartada; projeto com IA desligada nunca chama o provedor; cota esgotada não quebra o sistema; provedor falso (mock) usado em todos os testes, sem chamadas reais no CI.
- **Arquivos grandes:** upload retomado após queda; PDF duplicado ocupa espaço uma vez; arquivo com extensão .pdf mas outro tipo real é rejeitado; exportação grande não estoura a memória do backend.
- **i18n:** nenhuma chave faltando em pt-BR ou en (teste automático); gráficos gerados nos dois idiomas.
- **Cotas:** usuário que excede a cota recebe mensagem clara e não derruba o sistema.
- **Fallback de progresso:** com SSE indisponível, a tela de progresso funciona por polling.

### 11.3 Gerais
- Cobertura mínima de 80% no backend e no serviço R.
- E2E (Playwright) do fluxo mínimo: criar projeto → cadastrar 4 estudos → extrair → avaliar risco de viés com 2 revisores → resolver conflito → rodar meta-análise → exportar forest plot, gráficos de RoB e script R.
- E2E da migração: importar tabela consolidada de RoB existente → gráficos iguais aos do robvis web.
- CI (GitHub Actions) roda lint, tipos e todos os testes em cada push.

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

---

## 13. Roteiro de desenvolvimento (por etapas e critérios de saída)

> Cada etapa só começa quando a anterior cumpre o critério de saída. Se o prazo do congresso apertar, a **Etapa 3 pode vir antes da 2**, pois a meta-análise é a maior dificuldade da usuária.

**Etapa 0 — Fundação**
Docker Compose com todos os serviços (perfis padrão e `lite`), Caddy, FastAPI com autenticação (cadastro com verificação de e-mail e captcha), projetos, membros e convites, auditoria e soft delete, Angular com login, i18n pt/en e cliente da API gerado, serviço R com `/health`, MinIO com upload em partes, worker `arq` com progresso (SSE + polling), cotas básicas, `.claude/settings.json` e hook de commits, backup/restore, `make tunnel`, CI rodando testes.
*Saída:* `docker compose up` sobe tudo; login funciona nos dois idiomas; `/health` do R responde com versões; teste de isolamento por projeto passa; upload de um PDF de 100 MB retoma após queda; o sistema abre por um endereço do Cloudflare Tunnel em outro dispositivo; um commit de teste sai sem nenhuma menção a IA; backup e restauração testados.

**Etapa 1 — Estudos, PDFs e extração (P0)**
Cadastro e importação da lista final, upload e anotação de PDF, relatos agrupados, formulário padrão versionado com braços e desfechos por grupo, proteções anti-erro dos blocos A, C, D, F e G de 7.5.1, exportação XLSX/CSV com regra de consenso.
*Saída:* a usuária cadastra 4 estudos reais com dados dos dois grupos sem planilha paralela; os testes de casos sintéticos de 7.5.1 (blocos A, C, D, F e G) passam.

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
- ADR-004: Arquivos no MinIO com upload direto em partes e deduplicação por hash.
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

---

## 16. Fora do escopo (por enquanto)
- Meta-análise em rede (network meta-analysis).
- Meta-análise de acurácia diagnóstica (QUADAS-2, curvas SROC).
- Meta-análise de dados individuais de pacientes (IPD).
- Busca automática direta nas bases (PubMed API) — avaliar depois do MVP.
- Aplicativo mobile nativo.
- Planos pagos, cobrança e assinatura (só depois da fase F2, se fizer sentido).
- Idiomas além de português e inglês.

---

## 17. Perguntas em aberto (confirmar com o grupo antes das etapas indicadas)
1. Quem do grupo vai usar o sistema e com quais papéis? *(Etapa 0)*
2. Qual a data limite de submissão do resumo? *(define a ordem das Etapas 2 e 3)*
3. Quais instrumentos de risco de viés o grupo usa de fato (JBI, ROBINS-I, NOS)? Qual versão? Qual a regra de classificação no JBI/NOS? *(Etapa 2)*
4. O grupo tem permissão para usar o texto completo dos checklists dentro do sistema? *(Etapa 2)*
5. Em que formato estão hoje as avaliações e a tabela consolidada (colunas, valores usados)? *(Etapa 2, migração)*
6. Qual o desfecho cognitivo principal, quais escalas e em quais momentos? *(Etapa 3)*
7. Os estudos usam o mesmo corte de 5 anos? Se não, qual regra adotar? *(Etapa 3)*
8. Usar estimativas ajustadas ou não ajustadas? *(Etapa 3)*
9. A dupla extração dos dados numéricos será obrigatória? Quem confere? *(Etapa 1)*
10. A UFAPE tem servidor ou VM disponível para a fase F1? *(antes da F1)*
11. O cadastro no Oracle Always Free é aceito com o cartão disponível? Qual região? *(antes da F1)*
12. Domínio: o gratuito do Student Pack (1º ano) ou subdomínio gratuito? *(fim da Etapa 0)*
13. Prazo de retenção de projetos inativos? *(Etapa 6)*
14. Licença do código antes de um dia tornar o repositório público (ex.: AGPL × MIT)? *(antes de abrir o repositório)*

Decisões já tomadas (não perguntar de novo): custo zero; hospedagem por fases começando no computador do desenvolvedor com Cloudflare Tunnel; repositório privado; sistema aberto ao público com cadastro; interface e saídas em português e inglês; sem prazo, todas as funcionalidades na ordem das etapas; commits sem menção a IA; IA desligada por padrão e com Gemini gratuito como primeiro provedor.

---

## 18. Referências para consulta (verificar a versão atual)
- Cochrane Handbook for Systematic Reviews of Interventions (capítulos de extração, risco de viés, meta-análise e estudos não randomizados)
- PRISMA 2020 Statement, fluxograma, checklist e PRISMA for Abstracts
- RoB 2, ROBINS-I e ROBINS-E — riskofbias.info
- JBI Critical Appraisal Tools — jbi.global
- Newcastle-Ottawa Scale — Ottawa Hospital Research Institute
- Documentação do `metafor` (Viechtbauer), do `meta` (Schwarzer) e do `robvis` (McGuinness & Higgins)
- GRADE Handbook
- Wan et al. (2014) e Luo et al. (2018), para estimar média e DP a partir de mediana
- Gøtzsche et al. (2007), "Data extraction errors in meta-analyses that use standardized mean differences" (JAMA)
- Tendal et al. (2009), variação entre observadores ao extrair dados para SMD (BMJ)
- Kanellopoulou et al., erros estatísticos comuns em meta-análises (Cochrane Evidence Synthesis and Methods)
- Estudo sobre a confusão EP/DP em meta-análises de medicina esportiva (Sports Medicine) e o levantamento de erros comuns de Kadlec et al.
- Issues do repositório `mcguinlu/robvis` no GitHub (bugs conhecidos)
- Documentação do Cloudflare Tunnel (túnel rápido e nomeado, limitações)
- Documentação do Oracle Cloud Always Free (cotas atuais e política de instâncias ociosas)
- Preços e termos da API do Gemini (plano gratuito e uso de dados)
- Documentação do Claude Code sobre a configuração `attribution`
- ASReview (priorização de triagem com aprendizado ativo)
- Documentação do FastAPI, SQLAlchemy 2.0, Alembic e Angular
