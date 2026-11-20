# Generates fixtures/egger.json, the expected values for /egger.
# Run inside the stats-r container (scripts/generate-fixtures.sh). metafor::regtest is
# called directly here, never typed by hand (docs/validacao.md 11.1).
#
# Data: public datasets dat.bcg (RR, 13 studies) and dat.normand1999 (MD, 9 studies:
# fewer than 10, so the answer must carry the warning).

data("dat.bcg", package = "metadat")
data("dat.normand1999", package = "metadat")
bcg <- metafor::escalc(measure = "RR", ai = dat.bcg$tpos, n1i = dat.bcg$tpos + dat.bcg$tneg,
                       ci = dat.bcg$cpos, n2i = dat.bcg$cpos + dat.bcg$cneg)
nor <- metafor::escalc(measure = "MD", m1i = dat.normand1999$m1i, sd1i = dat.normand1999$sd1i,
                       n1i = dat.normand1999$n1i, m2i = dat.normand1999$m2i,
                       sd2i = dat.normand1999$sd2i, n2i = dat.normand1999$n2i)

case <- function(name, measure, es, labels, method, test) {
  fit <- metafor::rma(yi = es$yi, vi = es$vi, method = if (method == "FE") "EE" else method,
                      test = test, level = 95)
  reg <- metafor::regtest(fit, model = "rma", predictor = "sei")
  list(
    name = paste(name, method, test, sep = "_"),
    request = list(measure = measure, method = method, test = test,
                   data = list(label = labels, yi = as.numeric(es$yi), vi = as.numeric(es$vi))),
    expected = list(k = fit$k, statistic = as.numeric(reg$zval), p_value = as.numeric(reg$pval),
                    limit_estimate = as.numeric(reg$est), few_studies = fit$k < 10)
  )
}

bcg_labels <- paste(dat.bcg$author, dat.bcg$year)
nor_labels <- as.character(dat.normand1999$source)
out <- list(
  generated_by = "fixtures/scripts/generate-egger.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = list(
    case("dat.bcg_RR", "RR", bcg, bcg_labels, "REML", "knha"),
    case("dat.bcg_RR", "RR", bcg, bcg_labels, "DL", "z"),
    case("dat.bcg_RR", "RR", bcg, bcg_labels, "FE", "z"),
    case("dat.normand1999_MD", "MD", nor, nor_labels, "REML", "knha")
  )
)
jsonlite::write_json(out, "fixtures/egger.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/egger.json\n")
