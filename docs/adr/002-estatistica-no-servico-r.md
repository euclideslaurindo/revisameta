# ADR-002: Toda estatística no serviço R (metafor/robvis)

**Status:** Aceito · **Data:** 2026-11-13

## Contexto
Erros estatísticos silenciosos são o pior risco do produto. `metafor`, `meta` e `robvis` são a referência usada por revisores; reimplementar em Python (statsmodels, PyMARE) traria menos estimadores maduros e menos confiança.

## Decisão
Um serviço R separado (plumber), **stateless e sem acesso ao banco**, faz toda conta estatística e todo gráfico estatístico. Python e Angular nunca calculam estatística. Contrato JSON com schema nos dois lados e resposta padrão `{ok, result, warnings, errors, meta}`. Versões fixadas com `renv`; o `robvis` fica fixado em um commit do GitHub (a versão do CRAN falha com "Sem informação" no ROBINS-I). Dois processos R atrás do Caddy.

## Consequências
- Resultados idênticos ao metafor, verificados por fixtures geradas pelo próprio R (tolerância 1e-6).
- Script R exportável reproduz qualquer análise.
- Um serviço a mais para operar; mitigado com healthcheck, timeouts, retry e mensagem clara quando o R estiver fora.
- Alternativas rejeitadas: `rpy2` (acopla processos); webR (avaliar só na P2).
