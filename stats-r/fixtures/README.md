# Fixtures de referência estatística

Valores esperados gerados **rodando o metafor** com datasets públicos (ex.: `dat.bcg`), salvos em JSON junto com o script que os gerou (docs/validacao.md, 11.1). Nunca escrever valores esperados à mão.

| Arquivo | Gerado por | Dados |
|---|---|---|
| `kappa.json` | `scripts/generate-kappa.R` | `irr::diagnoses` (avaliadores 1 e 2) e um caso fictício de extração |
| `meta-analysis.json` | `scripts/generate-meta-analysis.R` | `dat.bcg` (OR e RR) e `dat.normand1999` (MD e SMD), com REML, DL, Paule-Mandel (com e sem Hartung-Knapp) e efeito fixo: 28 casos, tolerância 1e-6 |

Para regerar: `scripts/generate-fixtures.sh` (na raiz do repositório). O script chama o `metafor` diretamente (não as funções do serviço), para que os testes confiram o serviço contra o pacote. As mesmas fixtures são usadas no R (`tests/testthat/test-meta-analysis.R`) e no Python, pelo cliente do backend contra o serviço R real (`backend/tests/test_stats_reference.py`).
