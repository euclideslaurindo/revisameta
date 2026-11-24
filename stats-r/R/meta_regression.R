# Meta-regression (docs/modulos.md 7.7, P2; stage 8 step 1).
#
# metafor::rma with moderators: numeric moderators enter as they are, text moderators
# as categories (the first category is the reference). Approved rule (docs/roteiro.md,
# stage 8): fewer than 3 studies does not run; fewer than 10 studies per coefficient
# (moderator) runs with a strong warning, as the Cochrane Handbook advises.

MIN_STUDIES_PER_MODERATOR <- 10

moderator_frame <- function(mods, n) {
  frame <- list()
  for (name in names(mods)) {
    values <- mods[[name]]
    if (length(values) != n) {
      return(NULL)
    }
    is_num <- all(vapply(values, function(v) is.null(v) || is.numeric(v), logical(1)))
    frame[[name]] <- if (is_num) {
      num(values)
    } else {
      factor(vapply(values, function(v) if (is.null(v)) NA_character_ else as.character(v), character(1)))
    }
  }
  as.data.frame(frame, check.names = FALSE, stringsAsFactors = FALSE)
}

meta_regression <- function(spec) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test) || method == "FE") "z" else spec$test
  params <- list(measure = spec$measure, method = method, test = test)
  mods <- spec$data$mods
  plain <- spec
  plain$data$mods <- NULL
  errors <- meta_input_errors(plain)
  if (is.null(mods) || length(mods) == 0) {
    errors <- c(errors, "meta-regression needs at least one moderator in data$mods")
  }
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  frame <- moderator_frame(mods, length(yi))
  if (is.null(frame)) {
    return(envelope(errors = "every moderator needs one value per study", params = params))
  }
  keep <- !is.na(yi) & !is.na(vi) & stats::complete.cases(frame)
  if (sum(keep) < 3) {
    return(envelope(errors = "meta-regression needs at least 3 studies with every moderator", params = params))
  }
  data <- frame[keep, , drop = FALSE]
  formula <- stats::as.formula(paste("~", paste(sprintf("`%s`", names(frame)), collapse = " + ")))
  run <- with_metafor_warnings(metafor::rma(
    yi = yi[keep], vi = vi[keep], mods = formula, data = data,
    method = if (method == "FE") "EE" else method, test = test, level = 95
  ))
  fit <- run$value
  k <- sum(keep)
  coefficients <- length(fit$beta) - 1
  warnings <- run$warnings
  if (k < MIN_STUDIES_PER_MODERATOR * coefficients) {
    warnings <- c(warnings, "fewer_than_ten_studies_per_moderator")
  }
  ratio <- spec$measure %in% RATIO
  rows <- lapply(seq_along(fit$beta), function(i) {
    row <- list(
      term = rownames(fit$beta)[i],
      estimate = as.numeric(fit$beta[i]),
      se = fit$se[i],
      statistic = fit$zval[i],
      p_value = fit$pval[i],
      ci_lb = fit$ci.lb[i],
      ci_ub = fit$ci.ub[i]
    )
    if (ratio) {
      row$exp <- list(estimate = exp(row$estimate), ci_lb = exp(row$ci_lb), ci_ub = exp(row$ci_ub))
    }
    row
  })
  envelope(
    result = list(
      k = k,
      coefficients = rows,
      moderators = list(
        statistic = fit$QM, df = fit$QMdf[1], df2 = if (test == "knha") fit$QMdf[2] else NA_real_,
        p_value = fit$QMp, statistic_kind = if (test == "knha") "F" else "chi2"
      ),
      residual = list(
        tau2 = if (method == "FE") 0 else fit$tau2,
        i2 = fit$I2,
        q = fit$QE, q_df = fit$k - fit$p, q_p = fit$QEp,
        r2 = if (method == "FE" || is.null(fit$R2)) NA_real_ else fit$R2
      ),
      left_out = labels[!keep]
    ),
    warnings = unique(warnings),
    params = params
  )
}
