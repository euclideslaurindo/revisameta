# Generates fixtures/subgroup.json, the expected values for /subgroup.
# Run inside the stats-r container (scripts/generate-fixtures.sh). metafor is called
# directly here (rma per subgroup, then a fixed-effect rma across the subgroup
# estimates for the test of differences), never typed by hand (docs/validacao.md 11.1).
#
# Data: public dataset dat.bcg (RR), subgroups by the type of allocation (alloc:
# random, alternate, systematic).

data("dat.bcg", package = "metadat")
es <- metafor::escalc(measure = "RR", ai = dat.bcg$tpos, n1i = dat.bcg$tpos + dat.bcg$tneg,
                      ci = dat.bcg$cpos, n2i = dat.bcg$cpos + dat.bcg$cneg)
labels <- paste(dat.bcg$author, dat.bcg$year)
group <- as.character(dat.bcg$alloc)

case <- function(method, test) {
  groups <- unique(group)
  fits <- lapply(groups, function(g) {
    idx <- group == g
    metafor::rma(yi = es$yi[idx], vi = es$vi[idx], method = if (method == "FE") "EE" else method,
                 test = test, level = 95)
  })
  between <- metafor::rma(yi = vapply(fits, function(f) as.numeric(f$beta), numeric(1)),
                          sei = vapply(fits, function(f) f$se, numeric(1)), method = "EE")
  list(
    name = paste("dat.bcg_RR_alloc", method, test, sep = "_"),
    request = list(measure = "RR", method = method, test = test,
                   data = list(label = labels, yi = as.numeric(es$yi), vi = as.numeric(es$vi), group = group)),
    expected = list(
      groups = groups,
      k = vapply(groups, function(g) sum(group == g), numeric(1), USE.NAMES = FALSE),
      estimate = vapply(fits, function(f) as.numeric(f$beta), numeric(1)),
      ci_lb = vapply(fits, function(f) f$ci.lb, numeric(1)),
      ci_ub = vapply(fits, function(f) f$ci.ub, numeric(1)),
      tau2 = vapply(fits, function(f) if (method == "FE") 0 else f$tau2, numeric(1)),
      q = between$QE, df = length(groups) - 1, p_value = between$QEp
    )
  )
}

out <- list(
  generated_by = "fixtures/scripts/generate-subgroup.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  cases = list(case("REML", "knha"), case("DL", "z"), case("FE", "z"))
)
jsonlite::write_json(out, "fixtures/subgroup.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/subgroup.json\n")
