# Generates fixtures/leave-one-out.json, the expected values for /leave-one-out.
# Run inside the stats-r container (scripts/generate-fixtures.sh). Values come from
# metafor::leave1out called directly here, never typed by hand (docs/validacao.md 11.1).
#
# Data: public datasets dat.bcg (RR) and dat.normand1999 (MD).

data("dat.bcg", package = "metadat")
data("dat.normand1999", package = "metadat")

bcg <- metafor::escalc(measure = "RR", ai = dat.bcg$tpos, n1i = dat.bcg$tpos + dat.bcg$tneg,
                       ci = dat.bcg$cpos, n2i = dat.bcg$cpos + dat.bcg$cneg)
bcg_labels <- paste(dat.bcg$author, dat.bcg$year)
normand <- metafor::escalc(measure = "MD", m1i = dat.normand1999$m1i, sd1i = dat.normand1999$sd1i,
                           n1i = dat.normand1999$n1i, m2i = dat.normand1999$m2i,
                           sd2i = dat.normand1999$sd2i, n2i = dat.normand1999$n2i)
normand_labels <- as.character(dat.normand1999$source)

case <- function(dataset, measure, es, labels, method, test) {
  fit <- metafor::rma(yi = es$yi, vi = es$vi, method = if (method == "FE") "EE" else method,
                      test = test, level = 95)
  l1o <- as.data.frame(metafor::leave1out(fit))
  list(
    name = paste(dataset, measure, method, test, sep = "_"),
    request = list(measure = measure, method = method, test = test,
                   data = list(label = labels, yi = as.numeric(es$yi), vi = as.numeric(es$vi))),
    expected = list(
      estimate = l1o$estimate, ci_lb = l1o$ci.lb, ci_ub = l1o$ci.ub, p_value = l1o$pval,
      tau2 = if (is.null(l1o$tau2)) rep(0, nrow(l1o)) else l1o$tau2,
      i2 = if (is.null(l1o$I2)) rep(NA, nrow(l1o)) else l1o$I2
    )
  )
}

cases <- list(
  case("dat.bcg", "RR", bcg, bcg_labels, "REML", "knha"),
  case("dat.bcg", "RR", bcg, bcg_labels, "DL", "z"),
  case("dat.normand1999", "MD", normand, normand_labels, "REML", "knha"),
  case("dat.normand1999", "MD", normand, normand_labels, "FE", "z")
)

out <- list(
  generated_by = "fixtures/scripts/generate-leave-one-out.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = cases
)
jsonlite::write_json(out, "fixtures/leave-one-out.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/leave-one-out.json\n")
