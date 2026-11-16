# Data conversions and combination of groups (docs/estatistica.md 8.5; 7.5).
#
# Every conversion returns the original values, the converted ones, the method and
# whether the result is "estimated" (e.g. mean from a median) or "derived" (e.g. an
# SMD from a t statistic), so the screen and the analysis can always show them.
#
# - se_to_sd:          SD = SE x sqrt(n)
# - ci_to_sd:          SD from the 95% CI of a mean, with the t distribution (n - 1 df),
#                      as in the Cochrane Handbook (6.5.2.2); for large n it is the same
#                      as the normal value
# - median_to_mean_sd: Wan et al. (2014) and Luo et al. (2018), metafor::conv.fivenum
#                      (method "luo/wan"); with min/max, q1/q3 or both
# - effect_ci_to_log:  ratio effect (OR, RR, HR) with its 95% CI -> yi = log(effect),
#                      vi from the width of the CI on the log scale (metafor::conv.wald)
# - t_to_smd, p_to_smd: Hedges' g from a two-group t statistic or an exact two-sided p
#                      value (metafor::escalc with ti or pi), sign given by the side
#                      the study favours
# combine_groups: several arms into one group, Cochrane Handbook formula (table 6.5.a)
#                 for continuous data; events and totals are added for dichotomous data.

pos <- function(x) !is.null(x) && is.numeric(x) && length(x) == 1 && is.finite(x) && x > 0
fin <- function(x) !is.null(x) && is.numeric(x) && length(x) == 1 && is.finite(x)

convert_one <- function(item) {
  kind <- item$kind
  out <- function(values, method, status, warnings = character()) {
    list(ok = TRUE, kind = kind, input = item, output = values, method = method,
         status = status, warnings = I(warnings), errors = I(character()))
  }
  fail <- function(message) {
    list(ok = FALSE, kind = kind, input = item, output = NULL, method = NULL,
         status = NULL, warnings = I(character()), errors = I(message))
  }
  if (identical(kind, "se_to_sd")) {
    if (!pos(item$se) || !pos(item$n)) return(fail("se and n must be positive numbers"))
    return(out(list(sd = item$se * sqrt(item$n)), "SD = SE x sqrt(n)", "converted"))
  }
  if (identical(kind, "ci_to_sd")) {
    if (!fin(item$ci_lb) || !fin(item$ci_ub) || !pos(item$n) || item$n < 2) {
      return(fail("ci_lb, ci_ub and n (at least 2) are required"))
    }
    if (item$ci_lb >= item$ci_ub) return(fail("ci_lb must be smaller than ci_ub"))
    t <- stats::qt(0.975, df = item$n - 1)
    sd <- sqrt(item$n) * (item$ci_ub - item$ci_lb) / (2 * t)
    return(out(list(sd = sd), "SD = sqrt(n) x (upper - lower) / (2 x t(0.975, n - 1))", "converted"))
  }
  if (identical(kind, "median_to_mean_sd")) {
    if (!fin(item$median) || !pos(item$n)) return(fail("median and n are required"))
    has_range <- fin(item$min) && fin(item$max)
    has_iqr <- fin(item$q1) && fin(item$q3)
    if (!has_range && !has_iqr) return(fail("min and max, or q1 and q3, are required"))
    na <- function(x) if (fin(x)) x else NA_real_
    caught <- character()
    res <- withCallingHandlers(
      metafor::conv.fivenum(
        min = na(item$min), q1 = na(item$q1), median = item$median, q3 = na(item$q3),
        max = na(item$max), n = item$n, method = "luo/wan"
      ),
      warning = function(w) {
        caught <<- c(caught, paste("metafor:", conditionMessage(w)))
        invokeRestart("muffleWarning")
      }
    )
    warnings <- caught
    skew <- attr(res, "tests")
    if (!is.null(skew) && any(skew$pval < 0.05, na.rm = TRUE)) {
      warnings <- c(warnings, "skewness_detected")
    }
    if (is.na(res$mean[1]) || is.na(res$sd[1])) return(fail("conversion not possible with these values"))
    return(out(
      list(mean = res$mean[1], sd = res$sd[1]),
      "Wan et al. (2014) / Luo et al. (2018), metafor::conv.fivenum(method = 'luo/wan')",
      "estimated", warnings
    ))
  }
  if (identical(kind, "effect_ci_to_log")) {
    if (!pos(item$estimate) || !pos(item$ci_lb) || !pos(item$ci_ub)) {
      return(fail("estimate, ci_lb and ci_ub must be positive (ratio measures)"))
    }
    if (!(item$ci_lb < item$estimate && item$estimate < item$ci_ub)) {
      return(fail("the estimate must lie inside its confidence interval"))
    }
    caught <- character()
    res <- withCallingHandlers(
      metafor::conv.wald(out = item$estimate, ci.lb = item$ci_lb, ci.ub = item$ci_ub, transf = log),
      warning = function(w) {
        caught <<- c(caught, paste("metafor:", conditionMessage(w)))
        invokeRestart("muffleWarning")
      }
    )
    return(out(
      list(yi = as.numeric(res$yi[1]), vi = as.numeric(res$vi[1])),
      "yi = log(effect); SE from the width of the 95% CI on the log scale (metafor::conv.wald)",
      "converted", caught
    ))
  }
  if (identical(kind, "t_to_smd") || identical(kind, "p_to_smd")) {
    if (!pos(item$n1) || !pos(item$n2)) return(fail("n1 and n2 are required"))
    if (!isTRUE(item$favours %in% c("group1", "group2"))) return(fail("favours must be group1 or group2"))
    sign <- if (item$favours == "group1") 1 else -1
    if (kind == "t_to_smd") {
      if (!fin(item$t)) return(fail("t is required"))
      es <- metafor::escalc("SMD", ti = sign * abs(item$t), n1i = item$n1, n2i = item$n2)
      method <- "Hedges' g from the t statistic (metafor::escalc, ti)"
    } else {
      if (!pos(item$p) || item$p >= 1) return(fail("p must be between 0 and 1"))
      es <- metafor::escalc("SMD", pi = sign * item$p, n1i = item$n1, n2i = item$n2)
      method <- "Hedges' g from the exact two-sided p value (metafor::escalc, pi)"
    }
    return(out(list(yi = as.numeric(es$yi[1]), vi = as.numeric(es$vi[1])), method, "derived"))
  }
  fail("unknown conversion kind")
}

convert <- function(spec) {
  items <- spec$conversions
  if (is.null(items) || length(items) == 0) {
    return(envelope(errors = "conversions is required"))
  }
  results <- lapply(items, convert_one)
  envelope(result = list(conversions = results), params = list(items = length(results)))
}

#' Several arms into one group (Cochrane Handbook, table 6.5.a).
combine_groups <- function(spec) {
  groups <- spec$groups
  type <- if (is.null(spec$type)) "continuous" else spec$type
  params <- list(type = type, groups = length(groups))
  if (length(groups) < 2) {
    return(envelope(errors = "at least two groups are needed", params = params))
  }
  if (type == "dichotomous") {
    events <- vapply(groups, function(g) as.numeric(g$events), numeric(1))
    total <- vapply(groups, function(g) as.numeric(g$total), numeric(1))
    if (any(!is.finite(events)) || any(!is.finite(total)) || any(events > total) || any(total <= 0)) {
      return(envelope(errors = "events and total must be valid for every group", params = params))
    }
    return(envelope(
      result = list(events = sum(events), total = sum(total), method = "events and totals added"),
      params = params
    ))
  }
  n <- vapply(groups, function(g) as.numeric(g$n), numeric(1))
  m <- vapply(groups, function(g) as.numeric(g$mean), numeric(1))
  s <- vapply(groups, function(g) as.numeric(g$sd), numeric(1))
  if (any(!is.finite(c(n, m, s))) || any(n <= 0) || any(s < 0)) {
    return(envelope(errors = "n, mean and sd must be valid for every group", params = params))
  }
  # Applied pairwise, which is exact for any number of groups.
  N <- n[1]
  M <- m[1]
  S <- s[1]
  for (i in seq_along(n)[-1]) {
    pooled_ss <- (N - 1) * S^2 + (n[i] - 1) * s[i]^2 + N * n[i] / (N + n[i]) * (M - m[i])^2
    S <- sqrt(pooled_ss / (N + n[i] - 1))
    M <- (N * M + n[i] * m[i]) / (N + n[i])
    N <- N + n[i]
  }
  envelope(
    result = list(n = N, mean = M, sd = S, method = "Cochrane Handbook, table 6.5.a"),
    params = params
  )
}
