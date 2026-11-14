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
