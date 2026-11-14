# Agreement between two raters on nominal codes (irr package).
#
# Used for double data extraction (docs/modulos.md 7.5.1, item 14) and later for
# screening and risk of bias. Each element of `rater_a` / `rater_b` is the code the
# rater gave to the same item; codes are compared as text.

agreement_input_errors <- function(rater_a, rater_b) {
  if (!is.atomic(rater_a) || !is.atomic(rater_b)) {
    return("rater_a and rater_b must be lists of codes")
  }
  if (length(rater_a) == 0) {
    return("at least one item is required")
  }
  if (length(rater_a) != length(rater_b)) {
    return("rater_a and rater_b must have the same length")
  }
  if (anyNA(rater_a) || anyNA(rater_b)) {
    return("codes cannot be missing; send an explicit code for absent values")
  }
  character()
}

#' Percentage of items with the same code and Cohen's kappa (unweighted).
#'
#' Kappa is reported only when it is defined: with fewer than two items, or when
#' both raters used one single code, chance agreement is total and kappa is not
#' computable. A warning explains why it is missing. Missing numbers are NA, which
#' the /kappa route serializes as JSON null.
kappa_agreement <- function(rater_a, rater_b) {
  errors <- agreement_input_errors(rater_a, rater_b)
  params <- list(method = "cohen_unweighted", items = length(rater_a))
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  ratings <- data.frame(a = as.character(rater_a), b = as.character(rater_b))
  percent <- irr::agree(ratings, tolerance = 0)$value
  warnings <- character()
  kappa <- NA_real_
  z <- NA_real_
  p_value <- NA_real_
  if (nrow(ratings) < 2) {
    warnings <- c(warnings, "kappa_needs_two_items")
  } else {
    fit <- suppressWarnings(irr::kappa2(ratings, weight = "unweighted"))
    if (is.finite(fit$value)) {
      kappa <- fit$value
      z <- if (is.finite(fit$statistic)) unname(fit$statistic) else NA_real_
      p_value <- if (is.finite(fit$p.value)) fit$p.value else NA_real_
    } else {
      warnings <- c(warnings, "kappa_undefined_single_code")
    }
  }
  envelope(
    result = list(
      items = nrow(ratings),
      agreeing_items = sum(ratings$a == ratings$b),
      agreement_percent = percent,
      kappa = kappa,
      z = z,
      p_value = p_value
    ),
    warnings = warnings,
    params = params
  )
}
