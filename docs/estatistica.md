# Motor estatístico (serviço R)

> Parte da especificação do RevisaMeta. Índice e regras gerais em [CLAUDE.md](../CLAUDE.md).

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

#### `/kappa` (implementado na Etapa 1)
- Entrada: `{ "rater_a": [...], "rater_b": [...] }`, um código (texto) por item, mesmo tamanho nas duas listas e sem valores ausentes (o backend manda `<empty>` para campo vazio).
- Saída (`result`): `items`, `agreeing_items`, `agreement_percent` (`irr::agree`, tolerância 0) e `kappa`, `z`, `p_value` (`irr::kappa2`, sem pesos). Números que não existem saem como `null`, com aviso: `kappa_needs_two_items` (menos de 2 itens) ou `kappa_undefined_single_code` (os dois avaliadores usaram um único código).
- Uso na dupla extração (bloco D de 7.5.1, decidido com o responsável em 2026-11-14): a **% de concordância** usa todos os números e categorias comparados; o **kappa de Cohen** usa só os campos de categoria (tipo de dispersão, valor final ou mudança, maior é melhor, ajustado, grupo/linha registrado), porque o kappa foi feito para respostas em categorias. São duas chamadas a `/kappa`.
- Valores de referência: `stats-r/fixtures/kappa.json`, gerado por `stats-r/fixtures/scripts/generate-kappa.R` (dataset público `irr::diagnoses` e um caso fictício marcado como tal). Regerar com `scripts/generate-fixtures.sh`.

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

## Decisões da Etapa 3 (2026-11-16)
- **Plano aprovado em 7 passos:**
  1. Base estatística com fixtures.
  2. Conversões e combinação de braços.
  3. Plano de análise e regras no protocolo.
  4. Montagem dos dados e bloqueios.
  5. Assistente.
  6. Blocos B e E de 7.5.1.
  7. Histórico e script R.
- **Hartung-Knapp sempre ligado por padrão** nos efeitos aleatórios (REML + `test = "knha"`), em qualquer número de estudos, sempre trocável e registrado na análise. Evita um corte arbitrário de "poucos estudos". No efeito fixo ele não se aplica: o serviço usa Wald e avisa (`knha_not_for_fixed_effect`).
- **Efeito fixo:** `method = "EE"` do metafor (chamado de "FE" na API).
- **Zero eventos nos dois grupos** (OR/RR): estudo fora do pooling (`drop00`), com o aviso `double_zero_excluded`. A correção de continuidade padrão do `escalc` (0,5 só nos estudos com célula zero) é avisada com `continuity_correction_applied`.
- **Direção:** em MD, SMD e ROM, "maior é pior" inverte o sinal só no serviço R (`higher_is_better = false`), com o aviso `direction_inverted`.
- **Avisos do metafor** nunca escapam como avisos soltos do R: viram códigos na resposta. O aviso do metafor sobre SMD muito grande aparece só uma vez por processo, então o detector de EP no lugar de DP (passo 6) não depende dele.
- **Grupo 1** é o grupo experimental/exposto (ex.: cirurgia antes dos 5 anos) e o **grupo 2** é o de comparação.

### Endpoints do passo 1
- `POST /effect-sizes`: `yi`, `vi`, EP e IC 95% de cada estudo (`escalc`).
- `POST /meta-analysis`: efeito combinado, EP, IC, estatística (t com Hartung-Knapp, z sem ele), valor p, intervalo de predição, τ², I², H², Q (gl e p), peso de cada estudo e, nas medidas de razão, os valores na escala original (exp). Com k < 2 não roda; com k < 5 avisa que a heterogeneidade é instável.

### Endpoints do passo 2 (conversões e combinação de braços)
- `POST /convert`: recebe uma lista de conversões e responde item a item. Cada item traz o valor original, o convertido, o método e a situação: `converted`, `estimated` (mediana→média) ou `derived` (t/p→SMD). Uma entrada impossível é recusada só naquele item, nunca adivinhada.
  - `se_to_sd`: DP = EP × √n.
  - `ci_to_sd`: DP a partir do IC 95% da média, com a distribuição t (n − 1 graus de liberdade), que para n grande coincide com o valor da normal (Cochrane Handbook 6.5.2.2).
  - `median_to_mean_sd`: Wan et al. (2014) / Luo et al. (2018) via `metafor::conv.fivenum(method = "luo/wan")`, com mínimo/máximo, IIQ ou os dois. Avisa se o teste de assimetria do metafor indicar distribuição assimétrica (`skewness_detected`).
  - `effect_ci_to_log`: OR, RR ou HR com IC 95% → yᵢ = log(efeito) e vᵢ pela largura do IC na escala log (`metafor::conv.wald`). Recusa se o efeito estiver fora do próprio IC.
  - `t_to_smd` e `p_to_smd`: g de Hedges a partir da estatística t ou do valor p bicaudal exato (`escalc` com `ti` ou `pi`). O sinal vem do lado que o estudo favorece (`favours`: `group1` ou `group2`).
- `POST /combine-groups`: junta vários braços num grupo. Para dados contínuos usa a fórmula do Cochrane Handbook (tabela 6.5.a), aplicada par a par, o que é exato para qualquer número de grupos. Para dados dicotômicos soma eventos e totais.

### Plano de análise (passo 3)
- `GET/PUT /projects/{id}/analysis-plan` (salvar: só admin, com trava otimista pela versão do projeto). O plano fica em `projects.analysis_plan`, validado no backend (`app/modules/protocol/analysis_plan.py`), e cada mudança fica na auditoria. Na tela, ele é editado na página Protocolo.
- **Comparação:** qual grupo do protocolo é o grupo 1 (exposto) e qual é o grupo 2. O efeito é sempre grupo 1 em relação ao grupo 2.
- **Ponto de corte:** valor e unidade da pergunta, com a regra para estudos com outro corte:
  - **estrita:** só o mesmo corte;
  - **tolerante:** uma faixa aceita, com subgrupo e sensibilidade por corte.
- **Corte de cada estudo:** vem do campo "ponto de corte usado pelo estudo" da extração e só é aceito como número puro ("5", "5,5"). Um texto como "< 5 anos" nunca é interpretado: o estudo aparece com o motivo "corte não informado como número" (`cutoff_status`). No formulário padrão de projetos novos, o campo passou a ser numérico.
- **Estimativas ajustadas:** `separate` (padrão; ajustadas e não ajustadas nunca entram juntas), `adjusted_only` ou `unadjusted_only`.
- **Desfechos:** medida (`auto`, MD, SMD; ou OR, RR, RD nos dicotômicos), conferida contra o tipo do desfecho, e momento da análise principal.
- **Modelo:** REML + Hartung-Knapp por padrão. No efeito fixo, o Hartung-Knapp é desligado automaticamente.
- **Sensibilidades e subgrupos planejados.** O que for rodado fora do plano será marcado como "não planejada" (passos 4 e 5).
