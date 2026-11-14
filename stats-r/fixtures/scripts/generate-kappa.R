# Generates fixtures/kappa.json, the expected values for the /kappa endpoint.
# Run inside the stats-r container (scripts/generate-fixtures.sh). Values come from
# irr itself, never typed by hand (docs/validacao.md, 11.1).
#
# Data: the public `diagnoses` dataset of irr (psychiatric diagnoses of 30 patients;
# raters 1 and 2) and a small fictitious extraction example, marked as such.

data("diagnoses", package = "irr")

case <- function(name, description, rater_a, rater_b) {
  ratings <- data.frame(a = as.character(rater_a), b = as.character(rater_b))
  fit <- irr::kappa2(ratings, weight = "unweighted")
  list(
    name = name,
    description = description,
    rater_a = as.character(rater_a),
    rater_b = as.character(rater_b),
    expected = list(
      items = nrow(ratings),
      agreeing_items = sum(ratings$a == ratings$b),
      agreement_percent = irr::agree(ratings, tolerance = 0)$value,
      kappa = fit$value,
      z = unname(fit$statistic),
      p_value = fit$p.value
    )
  )
}

cases <- list(
  case(
    "irr_diagnoses_raters_1_2",
    "irr::diagnoses, raters 1 and 2 (public dataset)",
    diagnoses[, 1],
    diagnoses[, 2]
  ),
  case(
    "fictitious_extraction_categories",
    "FICTITIOUS: dispersion type and value type codes of two extractors",
    c("sd", "sd", "se", "ci95", "sd", "final", "final", "change", "true", "true"),
    c("sd", "se", "se", "ci95", "sd", "final", "change", "change", "true", "false")
  )
)

out <- list(
  generated_by = "fixtures/scripts/generate-kappa.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  irr_version = as.character(utils::packageVersion("irr")),
  cases = cases
)
jsonlite::write_json(out, "fixtures/kappa.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/kappa.json\n")
