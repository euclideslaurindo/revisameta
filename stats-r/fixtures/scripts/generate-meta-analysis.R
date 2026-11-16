# Generates fixtures/meta-analysis.json, the expected values for /effect-sizes and
# /meta-analysis. Run inside the stats-r container (scripts/generate-fixtures.sh).
# Values come from metafor itself (escalc, rma, predict called directly here, not
# through the service functions), never typed by hand (docs/validacao.md, 11.1).
#
# Data: public datasets of metadat/metafor.
# - dat.bcg: BCG vaccine trials (dichotomous; tpos/tneg vaccinated, cpos/cneg controls).
# - dat.normand1999: stroke rehabilitation, length of stay (continuous).

data("dat.bcg", package = "metadat")
data("dat.normand1999", package = "metadat")

bcg <- list(
  label = paste(dat.bcg$author, dat.bcg$year),
  ai = dat.bcg$tpos, n1i = dat.bcg$tpos + dat.bcg$tneg,
  ci = dat.bcg$cpos, n2i = dat.bcg$cpos + dat.bcg$cneg
)
normand <- list(
  label = as.character(dat.normand1999$source),
  m1i = dat.normand1999$m1i, sd1i = dat.normand1999$sd1i, n1i = dat.normand1999$n1i,
  m2i = dat.normand1999$m2i, sd2i = dat.normand1999$sd2i, n2i = dat.normand1999$n2i
)

effects <- function(measure, data) {
  if (measure %in% c("OR", "RR", "RD")) {
    metafor::escalc(measure = measure, ai = data$ai, n1i = data$n1i, ci = data$ci, n2i = data$n2i,
                    drop00 = measure != "RD")
  } else {
    metafor::escalc(measure = measure, m1i = data$m1i, sd1i = data$sd1i, n1i = data$n1i,
                    m2i = data$m2i, sd2i = data$sd2i, n2i = data$n2i)
  }
}

case <- function(dataset, data, measure, method, test) {
  es <- effects(measure, data)
  fit <- metafor::rma(yi = es$yi, vi = es$vi, method = if (method == "FE") "EE" else method,
                      test = test, level = 95)
  pred <- predict(fit, level = 95)
  list(
    name = paste(dataset, measure, method, test, sep = "_"),
    dataset = dataset,
    request = list(measure = measure, method = method, test = test, data = data),
    expected = list(
      k = fit$k,
      estimate = as.numeric(fit$beta), se = fit$se, ci_lb = fit$ci.lb, ci_ub = fit$ci.ub,
      statistic = fit$zval, p_value = fit$pval,
      pi_lb = if (is.null(pred$pi.lb)) pred$ci.lb else pred$pi.lb,
      pi_ub = if (is.null(pred$pi.ub)) pred$ci.ub else pred$pi.ub,
      tau2 = if (method == "FE") 0 else fit$tau2,
      i2 = fit$I2, h2 = fit$H2, q = fit$QE, q_p = fit$QEp,
      yi = as.numeric(es$yi), vi = as.numeric(es$vi),
      weights = as.numeric(weights(fit)) / 100
    )
  )
}

cases <- list()
for (measure in c("OR", "RR")) {
  for (method in c("REML", "DL", "PM")) {
    for (test in c("knha", "z")) cases[[length(cases) + 1]] <- case("dat.bcg", bcg, measure, method, test)
  }
  cases[[length(cases) + 1]] <- case("dat.bcg", bcg, measure, "FE", "z")
}
for (measure in c("MD", "SMD")) {
  for (method in c("REML", "DL", "PM")) {
    for (test in c("knha", "z")) cases[[length(cases) + 1]] <- case("dat.normand1999", normand, measure, method, test)
  }
  cases[[length(cases) + 1]] <- case("dat.normand1999", normand, measure, "FE", "z")
}

out <- list(
  generated_by = "fixtures/scripts/generate-meta-analysis.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = cases
)
jsonlite::write_json(out, "fixtures/meta-analysis.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/meta-analysis.json with", length(cases), "cases\n")
