# Generates fixtures/multilevel.json, the expected values for /multilevel.
# Run inside the stats-r container (scripts/generate-fixtures.sh). metafor::rma.mv is
# called directly here, never typed by hand (docs/validacao.md 11.1).
#
# Data: public dataset dat.konstantopoulos2011 (metadat), the classic multilevel example:
# 56 effects (schools) nested in 11 clusters (districts).

data("dat.konstantopoulos2011", package = "metadat")
d <- dat.konstantopoulos2011
labels <- paste("district", d$district, "school", d$school)
study <- as.character(d$district)

case <- function(method, test) {
  data <- data.frame(yi = d$yi, vi = d$vi, study = study, effect = seq_len(nrow(d)))
  fit <- metafor::rma.mv(yi, vi, random = ~ 1 | study / effect, data = data,
                         method = method, test = test, level = 95)
  pred <- stats::predict(fit, level = 95)
  list(
    name = paste("dat.konstantopoulos2011_SMD", method, test, sep = "_"),
    request = list(measure = "SMD", method = method, test = if (test == "t") "knha" else "z",
                   data = list(label = labels, study = study, yi = as.numeric(d$yi), vi = as.numeric(d$vi))),
    expected = list(
      k = fit$k, studies = length(unique(study)),
      estimate = as.numeric(fit$beta), se = fit$se, ci_lb = fit$ci.lb, ci_ub = fit$ci.ub,
      p_value = fit$pval, pi_lb = as.numeric(pred$pi.lb), pi_ub = as.numeric(pred$pi.ub),
      sigma2 = as.numeric(fit$sigma2), q = fit$QE, q_p = fit$QEp
    )
  )
}

out <- list(
  generated_by = "fixtures/scripts/generate-multilevel.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = list(case("REML", "z"), case("REML", "t"), case("ML", "z"))
)
jsonlite::write_json(out, "fixtures/multilevel.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/multilevel.json\n")
