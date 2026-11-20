# Leave-one-out sensitivity analysis (docs/modulos.md 7.7; metafor::leave1out).
#
# The model is refitted without each study in turn, so the user sees whether one study
# alone drives the result. Same model, estimator and test as the main analysis.

leave_one_out <- function(spec) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test) || method == "FE") "z" else spec$test
  params <- list(measure = spec$measure, method = method, test = test)
  errors <- meta_input_errors(spec)
  if (!all(c("yi", "vi") %in% names(spec$data))) errors <- c(errors, "leave-one-out takes yi and vi per study")
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  keep <- !is.na(yi) & !is.na(vi)
  if (sum(keep) < 3) {
    return(envelope(errors = "leave-one-out needs at least three studies", params = params))
  }
  run <- with_metafor_warnings({
    fit <- metafor::rma(yi = yi[keep], vi = vi[keep], slab = labels[keep],
                        method = if (method == "FE") "EE" else method, test = test, level = 95)
    metafor::leave1out(fit)
  })
  l1o <- as.data.frame(run$value)
  ratio <- spec$measure %in% RATIO
  rows <- lapply(seq_len(nrow(l1o)), function(i) {
    row <- list(
      omitted = labels[keep][i],
      estimate = l1o$estimate[i],
      se = l1o$se[i],
      ci_lb = l1o$ci.lb[i],
      ci_ub = l1o$ci.ub[i],
      p_value = l1o$pval[i],
      tau2 = if (is.null(l1o$tau2)) 0 else l1o$tau2[i],
      i2 = if (is.null(l1o$I2)) NA_real_ else l1o$I2[i]
    )
    if (ratio) {
      row$exp <- list(estimate = exp(row$estimate), ci_lb = exp(row$ci_lb), ci_ub = exp(row$ci_ub))
    }
    row
  })
  envelope(result = list(rows = rows), warnings = run$warnings, params = params)
}
