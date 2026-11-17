# Effect sizes and meta-analysis (docs/estatistica.md 8.3 and 8.4; docs/modulos.md 7.7).
#
# Pure functions around metafor: the backend sends the data of each study and the
# chosen model; R computes everything and says what it did. Nothing is computed in
# Python or in the browser.
#
# Input (`spec`), columns as arrays of the same length, one element per study:
#   measure: MD | SMD | ROM (continuous) or OR | RR | RD (dichotomous)
#   data:    label, and m1i sd1i n1i m2i sd2i n2i (continuous)
#            or ai n1i ci n2i (events and totals per group, dichotomous)
#            or yi vi (effects already on the analysis scale, e.g. log OR)
#   method:  REML | DL | PM | FE        (FE = common/fixed effect)
#   test:    knha | z                   (Hartung-Knapp or Wald)
#   higher_is_better: for MD/SMD/ROM, when FALSE the sign is inverted here, the only
#            place where it happens (7.5.1 item 10)
#
# Group 1 is the experimental/exposed group (e.g. surgery before 5 years), group 2
# the comparison group.

CONTINUOUS <- c("MD", "SMD", "ROM")
DICHOTOMOUS <- c("OR", "RR", "RD")
RATIO <- c("OR", "RR", "ROM")
METHODS <- c("REML", "DL", "PM", "FE")
TESTS <- c("knha", "z")

num <- function(x) {
  if (is.null(x)) {
    return(NULL)
  }
  vapply(x, function(v) if (is.null(v)) NA_real_ else as.numeric(v), numeric(1))
}

meta_input_errors <- function(spec) {
  errors <- character()
  if (!isTRUE(spec$measure %in% c(CONTINUOUS, DICHOTOMOUS))) {
    errors <- c(errors, "measure must be one of MD, SMD, ROM, OR, RR, RD")
  }
  if (!is.null(spec$method) && !isTRUE(spec$method %in% METHODS)) {
    errors <- c(errors, "method must be one of REML, DL, PM, FE")
  }
  if (!is.null(spec$test) && !isTRUE(spec$test %in% TESTS)) {
    errors <- c(errors, "test must be knha or z")
  }
  data <- spec$data
  if (is.null(data) || length(data$label) == 0) {
    return(c(errors, "data with at least one study is required"))
  }
  k <- length(data$label)
  given <- names(data)
  for (column in setdiff(given, "label")) {
    if (length(data[[column]]) != k) errors <- c(errors, paste("column", column, "must have one value per study"))
  }
  has <- function(cols) all(cols %in% given)
  if (!has(c("yi", "vi"))) {
    if (isTRUE(spec$measure %in% CONTINUOUS) && !has(c("m1i", "sd1i", "n1i", "m2i", "sd2i", "n2i"))) {
      errors <- c(errors, "continuous measures need m1i, sd1i, n1i, m2i, sd2i, n2i (or yi, vi)")
    }
    if (isTRUE(spec$measure %in% DICHOTOMOUS) && !has(c("ai", "n1i", "ci", "n2i"))) {
      errors <- c(errors, "dichotomous measures need ai, n1i, ci, n2i (or yi, vi)")
    }
  }
  errors
}

#' Runs a metafor call keeping its warnings as codes for the response, never lost.
with_metafor_warnings <- function(expr) {
  caught <- character()
  value <- withCallingHandlers(expr, warning = function(w) {
    message <- conditionMessage(w)
    code <- if (grepl("unusually large", message, fixed = TRUE)) {
      "smd_unusually_large"
    } else {
      paste("metafor:", gsub("[[:space:]]+", " ", message))
    }
    caught <<- c(caught, code)
    invokeRestart("muffleWarning")
  })
  list(value = value, warnings = caught)
}

#' Effect and variance of each study (escalc), on the analysis scale.
#'
#' Studies whose effect cannot be computed (e.g. zero events in both groups for OR/RR)
#' get NA and a warning; they are left out of the meta-analysis, never hidden.
effect_sizes <- function(spec) {
  data <- spec$data
  labels <- vapply(data$label, as.character, character(1))
  warnings <- character()
  if (all(c("yi", "vi") %in% names(data))) {
    es <- metafor::escalc(measure = "GEN", yi = num(data$yi), vi = num(data$vi), slab = labels)
  } else if (spec$measure %in% CONTINUOUS) {
    run <- with_metafor_warnings(metafor::escalc(
      measure = spec$measure,
      m1i = num(data$m1i), sd1i = num(data$sd1i), n1i = num(data$n1i),
      m2i = num(data$m2i), sd2i = num(data$sd2i), n2i = num(data$n2i),
      slab = labels
    ))
    es <- run$value
    warnings <- c(warnings, run$warnings)
  } else {
    ai <- num(data$ai)
    ci <- num(data$ci)
    n1i <- num(data$n1i)
    n2i <- num(data$n2i)
    double_zero <- (ai == 0 & ci == 0) | (ai == n1i & ci == n2i)
    if (any(double_zero, na.rm = TRUE)) {
      warnings <- c(warnings, "double_zero_excluded")
    }
    if (spec$measure != "RD" && any((ai == 0 | ci == 0 | ai == n1i | ci == n2i) & !double_zero, na.rm = TRUE)) {
      warnings <- c(warnings, "continuity_correction_applied")
    }
    es <- metafor::escalc(
      measure = spec$measure, ai = ai, n1i = n1i, ci = ci, n2i = n2i,
      drop00 = spec$measure != "RD", slab = labels
    )
  }
  yi <- as.numeric(es$yi)
  vi <- as.numeric(es$vi)
  # MD, SMD and log ratio of means: "higher is worse" flips the sign of the effect.
  # Either for every study (spec$higher_is_better) or per study, when each study used
  # its own scale (data$higher_is_better). This is the only place where it happens.
  flip <- rep(FALSE, length(yi))
  if (spec$measure %in% CONTINUOUS) {
    if (!is.null(data$higher_is_better)) {
      flip <- vapply(data$higher_is_better, function(v) isFALSE(as.logical(v)), logical(1))
    } else if (isFALSE(spec$higher_is_better)) {
      flip <- rep(TRUE, length(yi))
    }
  }
  inverted <- any(flip)
  if (inverted) {
    yi[flip] <- -yi[flip]
    warnings <- c(warnings, "direction_inverted")
  }
  if (anyNA(yi)) {
    warnings <- c(warnings, "studies_without_effect")
  }
  list(labels = labels, yi = yi, vi = vi, warnings = unique(warnings), inverted = inverted, flip = flip)
}

study_table <- function(es, weights = NULL) {
  sei <- sqrt(es$vi)
  z <- stats::qnorm(0.975)
  out <- lapply(seq_along(es$labels), function(i) {
    list(
      label = es$labels[i],
      yi = es$yi[i],
      vi = es$vi[i],
      sei = sei[i],
      ci_lb = es$yi[i] - z * sei[i],
      ci_ub = es$yi[i] + z * sei[i],
      included = !is.na(es$yi[i]),
      inverted = if (is.null(es$flip)) FALSE else es$flip[i],
      weight = if (is.null(weights) || is.na(es$yi[i])) NA_real_ else unname(weights[es$labels[i]])
    )
  })
  out
}

effect_sizes_result <- function(spec) {
  errors <- meta_input_errors(spec)
  params <- list(measure = spec$measure)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  es <- effect_sizes(spec)
  envelope(result = list(studies = study_table(es)), warnings = es$warnings, params = params)
}

#' Fits the model (rma) and returns estimates, heterogeneity and prediction interval.
meta_analysis <- function(spec) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test)) "knha" else spec$test
  params <- list(measure = spec$measure, method = method, test = test, level = 95)
  errors <- meta_input_errors(spec)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  es <- effect_sizes(spec)
  warnings <- es$warnings
  keep <- !is.na(es$yi) & !is.na(es$vi)
  k <- sum(keep)
  if (k < 2) {
    return(envelope(errors = "at least two studies with an effect are needed", warnings = warnings, params = params))
  }
  if (method == "FE" && test == "knha") {
    test <- "z"
    params$test <- test
    warnings <- c(warnings, "knha_not_for_fixed_effect")
  }
  if (k < 5 && method != "FE") {
    warnings <- c(warnings, "few_studies_heterogeneity_unstable")
  }
  run <- with_metafor_warnings(metafor::rma(
    yi = es$yi[keep], vi = es$vi[keep], slab = es$labels[keep],
    method = if (method == "FE") "EE" else method,
    test = test, level = 95
  ))
  fit <- run$value
  warnings <- c(warnings, run$warnings)
  pred <- stats::predict(fit, level = 95)
  pi_lb <- if (is.null(pred$pi.lb)) pred$ci.lb else pred$pi.lb
  pi_ub <- if (is.null(pred$pi.ub)) pred$ci.ub else pred$pi.ub
  weights <- stats::weights(fit) / 100
  names(weights) <- es$labels[keep]
  pooled <- list(
    estimate = as.numeric(fit$beta),
    se = fit$se,
    ci_lb = fit$ci.lb,
    ci_ub = fit$ci.ub,
    statistic = fit$zval,
    statistic_kind = if (test == "knha") "t" else "z",
    df = if (test == "knha") fit$k - 1 else NA_real_,
    p_value = fit$pval,
    pi_lb = pi_lb,
    pi_ub = pi_ub
  )
  if (spec$measure %in% RATIO) {
    pooled$exp <- list(
      estimate = exp(pooled$estimate), ci_lb = exp(fit$ci.lb), ci_ub = exp(fit$ci.ub),
      pi_lb = exp(pi_lb), pi_ub = exp(pi_ub)
    )
  }
  heterogeneity <- list(
    tau2 = if (method == "FE") 0 else fit$tau2,
    se_tau2 = if (method == "FE") NA_real_ else fit$se.tau2,
    tau = if (method == "FE") 0 else sqrt(fit$tau2),
    i2 = fit$I2,
    h2 = fit$H2,
    q = fit$QE,
    q_df = fit$k - 1,
    q_p = fit$QEp
  )
  envelope(
    result = list(
      k = fit$k,
      pooled = pooled,
      heterogeneity = heterogeneity,
      studies = study_table(es, weights),
      direction_inverted = es$inverted
    ),
    warnings = unique(warnings),
    params = params
  )
}
