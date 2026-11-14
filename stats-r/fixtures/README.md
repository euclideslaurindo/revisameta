# Fixtures de referência estatística

Valores esperados gerados **rodando o metafor** com datasets públicos (ex.: `dat.bcg`), salvos em JSON junto com o script que os gerou (docs/validacao.md, 11.1). Nunca escrever valores esperados à mão.

| Arquivo | Gerado por | Dados |
|---|---|---|
| `kappa.json` | `scripts/generate-kappa.R` | `irr::diagnoses` (avaliadores 1 e 2) e um caso fictício de extração |

Para regerar: `scripts/generate-fixtures.sh` (na raiz do repositório). As fixtures do metafor chegam na Etapa 3.
