# Generates fixtures/meta-regression.json, the expected values for /meta-regression.
# Run inside the stats-r container (scripts/generate-fixtures.sh). metafor::rma with
# moderators is called directly here, never typed by hand (docs/validacao.md 11.1).
#
# Data: public dataset dat.bcg (RR). Moderators: absolute latitude (numeric, the classic
# metafor example) and the type of allocation (categorical).

data("dat.bcg", package = "metadat")
es <- metafor::escalc(measure = "RR", ai = dat.bcg$tpos, n1i = dat.bcg$tpos + dat.bcg$tneg,
                      ci = dat.bcg$cpos, n2i = dat.bcg$cpos + dat.bcg$cneg)
labels <- paste(dat.bcg$author, dat.bcg$year)

case <- function(name, mods, method, test) {
  frame <- as.data.frame(mods, stringsAsFactors = FALSE)
  for (n in names(frame)) if (is.character(frame[[n]])) frame[[n]] <- factor(frame[[n]])
  formula <- stats::as.formula(paste("~", paste(sprintf("`%s`", names(frame)), collapse = " + ")))
  fit <- metafor::rma(yi = es$yi, vi = es$vi, mods = formula, data = frame,
                      method = if (method == "FE") "EE" else method, test = test, level = 95)
  list(
    name = paste("dat.bcg_RR", name, method, test, sep = "_"),
    request = list(measure = "RR", method = method, test = test,
                   data = list(label = labels, yi = as.numeric(es$yi), vi = as.numeric(es$vi), mods = mods)),
    expected = list(
      k = fit$k,
      terms = rownames(fit$beta),
      estimate = as.numeric(fit$beta),
      se = as.numeric(fit$se),
      ci_lb = as.numeric(fit$ci.lb),
      ci_ub = as.numeric(fit$ci.ub),
      p_value = as.numeric(fit$pval),
      qm = fit$QM, qm_p = fit$QMp,
      tau2 = if (method == "FE") 0 else fit$tau2,
      r2 = if (method == "FE" || is.null(fit$R2)) NULL else fit$R2
    )
  )
}

ablat <- list(ablat = as.numeric(dat.bcg$ablat))
both <- list(ablat = as.numeric(dat.bcg$ablat), alloc = as.character(dat.bcg$alloc))
out <- list(
  generated_by = "fixtures/scripts/generate-meta-regression.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = list(
    case("ablat", ablat, "REML", "z"),
    case("ablat", ablat, "REML", "knha"),
    case("ablat", ablat, "DL", "z"),
    case("ablat_alloc", both, "REML", "z")
  )
)
jsonlite::write_json(out, "fixtures/meta-regression.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/meta-regression.json\n")
