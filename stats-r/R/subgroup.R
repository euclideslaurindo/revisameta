# Subgroup analysis (docs/modulos.md 7.7; stage 4 decision).
#
# One meta-analysis per subgroup, each with its own tau^2 (as RevMan and the Cochrane
# Handbook do by default), and the test for subgroup differences: Cochran's Q across the
# subgroup estimates, combined with a fixed-effect model (df = number of subgroups - 1).
# A subgroup with a single study shows that study's effect and has no tau^2.

subgroup_analysis <- function(spec) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test) || method == "FE") "z" else spec$test
  params <- list(measure = spec$measure, method = method, test = test)
  errors <- meta_input_errors(spec)
  if (!all(c("yi", "vi", "group") %in% names(spec$data))) {
    errors <- c(errors, "subgroups take yi, vi and group per study")
  }
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  group <- vapply(spec$data$group, function(g) if (is.null(g)) NA_character_ else as.character(g), character(1))
  keep <- !is.na(yi) & !is.na(vi) & !is.na(group)
  groups <- unique(group[keep])
  if (length(groups) < 2) {
    return(envelope(errors = "at least two subgroups with studies are needed", params = params))
  }
  ratio <- spec$measure %in% RATIO
  warnings <- character()
  rows <- list()
  est <- numeric()
  se <- numeric()
  for (g in groups) {
    idx <- keep & group == g
    k <- sum(idx)
    if (k == 1) {
      row <- list(group = g, k = 1L, estimate = yi[idx], se = sqrt(vi[idx]),
                  ci_lb = yi[idx] - stats::qnorm(0.975) * sqrt(vi[idx]),
                  ci_ub = yi[idx] + stats::qnorm(0.975) * sqrt(vi[idx]),
                  p_value = NA_real_, tau2 = NA_real_, i2 = NA_real_, studies = labels[idx])
      warnings <- c(warnings, "subgroup_with_one_study")
    } else {
      run <- with_metafor_warnings(metafor::rma(
        yi = yi[idx], vi = vi[idx], method = if (method == "FE") "EE" else method, test = test, level = 95
      ))
      fit <- run$value
      warnings <- c(warnings, run$warnings)
      row <- list(group = g, k = k, estimate = as.numeric(fit$beta), se = fit$se,
                  ci_lb = fit$ci.lb, ci_ub = fit$ci.ub, p_value = fit$pval,
                  tau2 = if (method == "FE") 0 else fit$tau2, i2 = fit$I2, studies = labels[idx])
      if (k < 3) warnings <- c(warnings, "subgroup_with_few_studies")
    }
    if (ratio) {
      row$exp <- list(estimate = exp(row$estimate), ci_lb = exp(row$ci_lb), ci_ub = exp(row$ci_ub))
    }
    rows[[length(rows) + 1]] <- row
    est <- c(est, row$estimate)
    se <- c(se, row$se)
  }
  between <- metafor::rma(yi = est, sei = se, method = "EE")
  envelope(
    result = list(
      subgroups = rows,
      test = list(q = between$QE, df = length(groups) - 1, p_value = between$QEp),
      left_out = labels[!keep & !is.na(yi)]
    ),
    warnings = unique(warnings),
    params = params
  )
}
