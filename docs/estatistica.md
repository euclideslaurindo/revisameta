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

### Montagem dos dados (passo 4)
- `POST /projects/{id}/analyses/preview` (`app/modules/analysis/assembly.py`): para um desfecho e um momento, diz quais estudos entram, com quais números, e por que os outros ficam de fora. Nada é salvo. É a base do passo 1 do assistente.
- **Divisão de tarefas:** o backend só escolhe e organiza os dados. Todas as contas são feitas pelo R:
  - conversões (EP, IC ou mediana → DP);
  - combinação de braços do mesmo grupo (fórmula do Cochrane);
  - efeito de cada estudo (`escalc`).
  
  Cada estudo termina como yᵢ/vᵢ na escala da análise, com o registro do que foi feito com os números.
- **De onde vêm os dados:** só do consenso enviado ou travado. Os braços entram pelo mapeamento para os grupos do plano (grupo 1 × grupo 2), e o corte do estudo é checado contra a regra do plano.
- **Direção por estudo:** cada estudo usa a direção da própria escala ("maior é melhor"). A inversão de sinal acontece no R, que agora aceita a direção por estudo (`data.higher_is_better`).
- **Conjuntos que nunca se misturam:**
  - "não ajustado": dados brutos dos grupos e efeitos informados não ajustados;
  - "ajustado": OR/RR ajustados com IC, convertidos para a escala log pelo R.
  
  O plano diz qual roda; com a política "separado", a pessoa escolhe.
- **Medida automática:**
  - dicotômico → RR;
  - contínuo com a mesma escala em todos os estudos → MD;
  - contínuo com escalas diferentes → SMD.
  
  Uma medida escolhida diferente da do plano é marcada como "não planejada", assim como um momento ou desfecho fora do plano.
- **Motivos para um estudo ficar de fora** (códigos traduzidos na tela):
  - `no_consensus`;
  - `cutoff_incompatible`, `cutoff_not_numeric`, `cutoff_missing`;
  - `no_data_for_result`, `no_comparison_in_plan`, `missing_group`, `missing_arm_data`;
  - `missing_n`, `missing_mean`, `missing_dispersion`, `missing_events`;
  - `mixed_value_type_in_study`;
  - `no_adjusted_effect`, `reported_measure_differs`, `reported_effect_without_ci`;
  - `conversion_failed`, `combination_failed`;
  - `no_effect_double_zero`.
- **Marcas de estudos que entram:** `converted`, `estimated` (mediana → média), `derived`, `arms_combined`, `reported_effect`, `adjusted`, `cutoff_tolerated` e `open_alerts` (alertas de extração ainda abertos).
- **Bloqueios da análise:** menos de 2 estudos (`fewer_than_two_studies`), SMD misturando valor final e mudança (`smd_mixed_final_change`) e estudo repetido (`duplicate_study`). Avisos: poucos estudos, dados estimados, alertas abertos, direção invertida, mistura de valor final e mudança na MD.
- **Testes:** usam o serviço R real. Os estudos de `dat.normand1999` e `dat.bcg` montados no banco precisam dar os mesmos yᵢ/vᵢ das fixtures do metafor.

### Assistente e forest plot (passo 5)
- `POST /analyses/run` roda o modelo no R com os dados montados no passo 4. É recusado com `analysis.blocked` enquanto houver bloqueio, e não salva nada (o histórico chega no passo 7). Modelo ou teste diferentes do plano entram em `not_planned`. A resposta traz as versões do R e dos pacotes (8.1).
- `POST /analyses/forest-plot`: `metafor::forest` com pesos, efeito combinado, intervalo de predição e o lado que cada direção favorece, escrito com o nome dos grupos do plano. O gráfico sai em SVG ou PNG a 300 dpi, no idioma escolhido (vírgula decimal em português). Estudos com dados estimados (*), convertidos (†) ou derivados (‡) são marcados, com nota explicando. Nas medidas de razão, o eixo usa valores redondos (0,1 / 0,2 / 0,5 / 1 / 2 / 5).
- **Lado favorecido:** em desfechos contínuos, depois da inversão por estudo feita no R, "maior" sempre significa "melhor", então efeito positivo favorece o grupo 1. Em desfechos dicotômicos, depende de o evento ser desejável (direção do desfecho).
- **Tela "Meta-análise"** (aba do projeto), em cinco passos:
  1. desfecho, momento e conjunto de dados, com cada estudo que entra ou fica de fora e o motivo;
  2. medida, com a recomendada e o porquê;
  3. direção da escala de cada estudo;
  4. modelo;
  5. resultado.
- **Resultado em linguagem simples:** frases traduzidas preenchidas só com os números do R. O resultado "favorece" um grupo só quando o IC 95% exclui o valor nulo. A leitura do I² usa as faixas do Cochrane Handbook (10.10.2), com cortes 40, 60 e 75. O painel "Como ler este gráfico" faz parte do Modo Aprendizado.
- **Teste de ponta a ponta pela API** (11.1, item 3): os estudos de `dat.normand1999` montados no banco dão o mesmo efeito combinado, IC, intervalo de predição, p e I² das fixtures do metafor, com REML+Hartung-Knapp, DerSimonian-Laird e efeito fixo.

### Projeto de demonstração
- `make seed-demo EMAIL=...` (ou `scripts/seed-demo.sh <e-mail>`) cria, para um usuário existente, um projeto marcado como demonstração com os 9 estudos de `dat.normand1999`: tempo de internação após AVC, unidade especializada × cuidado habitual. Os números são lidos da fixture do metafor, nunca digitados. Como tempo de internação é "maior é pior", a demonstração também mostra a inversão de sinal.

### Alertas de plausibilidade e influência (passo 6; 7.5.1 blocos B e E)
- **Limiares aprovados pelo responsável em 2026-11-17.** São configuráveis por projeto no plano de análise (`checks`) e só avisam: nada é bloqueado nem corrigido sozinho.
  - **EP no lugar de DP** (`possible_se_as_sd`): entre estudos do mesmo desfecho e da mesma escala (pelo menos 3), compara cada DP com o DP típico, que é a mediana dos DPs dos outros estudos. O alerta aparece quando o DP é menor que 50% do típico **e** DP×√n fica a menos de 50% do típico (a assinatura de um EP). Só entram DPs digitados como DP; valores convertidos de EP ou IC já são DPs calculados pelo R.
  - **Valor p que não confere** (`p_inconsistent`): o p do artigo é comparado com o p recalculado no R a partir de média, DP e n (teste t com variância combinada). O alerta aparece se os dois ficarem em lados opostos de 0,05 ou diferirem mais de 10 vezes.
  - **Estudo influente** (`influential`): critério publicado do próprio metafor (`influence()$is.infl`; Viechtbauer & Cheung, 2010), sem limiar nosso. Precisa de pelo menos 3 estudos.
  - **Efeito improvável** (`improbable_effect`): |SMD| > 2 (o mesmo corte do aviso do metafor) ou OR/RR fora de 0,1–10.
- **Endpoints do R:** `/plausibility-checks` (bloco B, rodado na montagem dos dados) e `/influence` (bloco E, depois do modelo). Os alertas aparecem no estudo, no passo 1 do assistente, com os números usados, e como aviso no resultado.
- **Testes:** casos sintéticos fictícios no R e no backend (EP digitado como DP é acusado; um DP pequeno que não é EP, outra escala ou menos de 3 estudos não geram alerta; p errado é acusado). A influência é conferida contra o `influence()` do metafor no `dat.bcg`.
- **Observado com dados reais (`dat.normand1999`, projeto de demonstração):** o detector marcou 3 de 9 estudos (Montreal-Home, Montreal-Transfer, Orpington-Mild), cujos DPs são verdadeiros. O tempo de internação varia cerca de 10 vezes entre os serviços (DP 4 a 64), e um DP genuinamente pequeno parece o EP de um DP típico. É um limite do método quando a mesma escala mede populações muito diferentes. Ajustar a tolerância não resolve (Montreal-Home fica a 4% do típico), e comparar só com o outro grupo do mesmo estudo deixaria passar o erro mais comum (EP nos dois grupos pela mesma nota de rodapé). A regra aprovada foi mantida, e a revisão dos limiares com os dados reais do grupo fica pendente (riscos, "alertas demais").

### Histórico e script R (passo 7)
- `POST /analyses` roda e salva a análise (só admin ou estatístico). Guarda os dados exatos que entraram (yᵢ/vᵢ e o registro de cada estudo), os parâmetros, o resultado, as versões do R e dos pacotes, a data, o autor e uma observação opcional.
- `GET /analyses` lista o histórico e `GET /analyses/{id}` abre uma análise. `DELETE` só tira do histórico (soft delete; nada é apagado de verdade).
- **"Desatualizada":** cada análise guarda a versão dos dados do consenso de cada estudo (`sources`). Se um número for corrigido (`data_version` sobe), o motivo é `data_changed`. Se um estudo ganhar ou perder o consenso, é `studies_changed`. A análise nunca é recalculada em silêncio: a pessoa roda de novo.
- **Script R** (`GET /analyses/{id}/r-script`, gerado pelo `/r-script` do R): traz os yᵢ/vᵢ com 17 dígitos significativos, a mesma chamada `rma()` (método, teste, nível) e `predict`/`forest`. No cabeçalho, comentários registram projeto, desfecho, grupos, modelo, versões e, por estudo, as conversões e inversões já aplicadas.

## Decisões da Etapa 4 (2026-11-19)
- **Plano em 5 passos:**
  1. Sensibilidade (um estudo de fora por vez, sem alto risco de viés, sem dados estimados, outro modelo ou estimador).
  2. Subgrupos com teste de diferença.
  3. Funnel plot e Egger, com aviso forte se k < 10.
  4. Síntese narrativa.
  5. Forest plot com o semáforo do risco de viés.
- **Subgrupos:** τ² **separado** em cada subgrupo (uma meta-análise por subgrupo) e o teste Q entre subgrupos. É o padrão do RevMan e do Cochrane Handbook.
- **"Alto risco de viés"** na sensibilidade é o **pior nível de cada instrumento**:
  - RoB 2: alto;
  - ROBINS-I (2016 e V2): grave e crítico;
  - ROBINS-E: alto e muito alto;
  - JBI, NOS e genérico: o pior nível da regra do grupo.
  
  Estudos sem avaliação final de risco de viés ficam de fora dessa análise, com aviso.
- **Síntese narrativa:** a direção do efeito dos estudos que não entram na meta-análise é **registrada pelo revisor** (favorece o grupo 1, favorece o grupo 2, sem diferença ou incerto), com justificativa e trecho do artigo. O sistema não deduz direção de dados incompletos.
- **Forest plot com o semáforo:** `metafor::forest` com colunas próprias para os domínios e o julgamento geral (ADR-014).

### Sensibilidade (Etapa 4, passo 1)
- `POST /analyses/sensitivity` refaz a análise principal mudando uma coisa. Todos os números vêm do R.
  - `leave_one_out`: o modelo sem cada estudo, um de cada vez (`metafor::leave1out`, endpoint `/leave-one-out`). Precisa de pelo menos 3 estudos.
  - `exclude_high_risk_of_bias`: sem os estudos no pior nível do instrumento (regra da Etapa 4), lido da avaliação final (consenso ou importação) para o mesmo resultado. Estudos sem avaliação final ficam de fora com aviso, e a lista deles aparece na tela.
  - `exclude_estimated_data`: sem estudos com números estimados (média a partir da mediana) ou derivados (de t ou p).
  - `fixed_vs_random`: efeito fixo se o modelo principal for aleatório, e REML caso contrário.
  - `other_estimator`: os outros estimadores (REML, DL, Paule-Mandel).
- Um cenário que fica com menos de 2 estudos não é calculado e diz isso (`not_enough_studies`). Um cenário fora da lista do plano é marcado como "não planejada".
- **Fixtures:** `stats-r/fixtures/leave-one-out.json` (gerada pelo `leave1out` do metafor, com `dat.bcg` e `dat.normand1999`). Pela API, os estudos de `dat.normand1999` montados no banco dão os mesmos valores do `leave1out` e das fixtures de efeito fixo e DerSimonian-Laird.

### Subgrupos (Etapa 4, passo 2)
- `POST /analyses/subgroups`: o subgrupo de cada estudo vem de:
  - um campo de texto ou de seleção do formulário de extração (consenso);
  - o julgamento geral final de risco de viés para o resultado;
  - o ponto de corte do estudo.
  
  Estudos sem valor ficam de fora e são listados.
- **No R** (`/subgroup`): uma meta-análise por subgrupo, cada uma com seu τ² (decisão da Etapa 4). O teste de diferença é o Q de Cochran entre as estimativas dos subgrupos, combinadas com efeito fixo (gl = número de subgrupos − 1). Um subgrupo com um único estudo mostra o efeito desse estudo e gera aviso; um subgrupo com menos de 3 estudos também avisa.
- O subgrupo conta como "planejado" quando o nome dele está na lista de subgrupos do plano de análise.
- **Fixtures:** `stats-r/fixtures/subgroup.json` (metafor chamado direto: `dat.bcg` por tipo de alocação, com REML+Hartung-Knapp, DL e efeito fixo). Pela API, os 13 estudos montados no banco com a alocação como característica dão os mesmos valores.
- **Correção no cliente do R:** quando o R responde um erro de validação, ele manda o `result` vazio como `[]`. O cliente tratava isso como "serviço fora do ar" (503). Agora o erro chega com a mensagem certa (teste em `test_stats_reference.py`).

### Viés de publicação: funnel plot e teste de Egger (Etapa 4, passo 3)
- `POST /analyses/egger` e `POST /analyses/funnel-plot`: os mesmos estudos, modelo e teste da análise principal.
- **No R:**
  - `/egger` usa `metafor::regtest(fit, model = "rma", predictor = "sei")`. Devolve a estatística (t com Hartung-Knapp, z sem ele), o p e a estimativa-limite. Recusa com menos de 3 estudos.
  - `/funnel-plot` usa `metafor::funnel` e devolve SVG, ou PNG a 300 dpi.
- **Menos de 10 estudos** (regra 0.2): as duas respostas trazem o aviso `fewer_than_ten_studies`. O backend devolve `few_studies`, e a tela mostra um aviso forte dizendo que o resultado não serve como conclusão.
- **Fixtures:** `stats-r/fixtures/egger.json`, gerado chamando o metafor direto:
  - `dat.bcg` (13 estudos) com REML+Hartung-Knapp, DL e efeito fixo;
  - `dat.normand1999` (9 estudos), caso que precisa trazer o aviso.
