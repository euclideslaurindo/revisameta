# Regenerates renv.lock with the packages the service needs.
# Run from the repository root (Git Bash):  scripts/stats-r-lock.sh
#
# robvis is pinned to a GitHub commit: the CRAN release fails with
# "No information" in ROBINS-I (see docs/modulos.md, 7.6, lesson L16).

robvis_ref <- "mcguinlu/robvis@0c59cf1725ca3e18016d28903d4e01fd0a37bcf9"

cran_packages <- c(
  "plumber",   # HTTP routes
  "jsonlite",  # JSON (de)serialization
  "metafor",   # meta-analysis engine (reference)
  "meta",      # complementary meta-analysis functions
  "irr",       # inter-rater agreement (kappa)
  "testthat",  # tests
  "lintr"      # lint
)

renv::install(c(cran_packages, robvis_ref), prompt = FALSE)
renv::snapshot(
  lockfile = "renv.lock",
  packages = c(cran_packages, "robvis"),
  prompt = FALSE
)
