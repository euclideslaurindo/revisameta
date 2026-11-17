# Plausibility checks and influence (docs/modulos.md 7.5.1, blocks B and E).
#
# They only warn: nothing is blocked or corrected. Thresholds come from the project
# (approved defaults, 2026-11-17):
#   sd_ratio = 0.5      SD below half of the typical SD of the same scale...
#   se_closeness = 0.5  ...and SD x sqrt(n) within 50% of that typical SD: probably an SE
#   min_studies = 3     at least 3 studies with the same scale to know the "typical" SD
#   p_factor = 10, alpha = 0.05  reported p vs p recomputed from means, SDs and n
#   smd_limit = 2, ratio_low = 0.1, ratio_high = 10  improbable effects
# Influence uses metafor's own published criteria (influence()$is.infl; Viechtbauer &
# Cheung, 2010), with no threshold of ours.

CHECK_DEFAULTS <- list(
  sd_ratio = 0.5, se_closeness = 0.5, min_studies = 3, p_factor = 10, alpha = 0.05,
  smd_limit = 2, ratio_low = 0.1, ratio_high = 10
)

check_params <- function(given) {
  params <- CHECK_DEFAULTS
  for (name in intersect(names(given), names(params))) {
    params[[name]] <- as.numeric(given[[name]])
  }
  params
}

#' SD that looks like an SE: compared with the typical SD of the other studies that use
#' the same scale (median of their SDs).
se_as_sd_alerts <- function(groups, params) {
  alerts <- list()
  if (length(groups) == 0) {
    return(alerts)
  }
  df <- data.frame(
    study = vapply(groups, function(g) as.character(g$study_id), character(1)),
    arm = vapply(groups, function(g) as.character(g$arm), character(1)),
    scale = vapply(groups, function(g) tolower(trimws(as.character(g$scale))), character(1)),
    n = vapply(groups, function(g) as.numeric(g$n), numeric(1)),
    sd = vapply(groups, function(g) as.numeric(g$sd), numeric(1)),
    stringsAsFactors = FALSE
  )
  df <- df[is.finite(df$sd) & df$sd > 0 & is.finite(df$n) & df$n > 0 & nzchar(df$scale), ]
  for (scale in unique(df$scale)) {
    same <- df[df$scale == scale, ]
    if (length(unique(same$study)) < params$min_studies) next
    for (i in seq_len(nrow(same))) {
      others <- same$sd[same$study != same$study[i]]
      typical <- stats::median(others)
      as_sd <- same$sd[i] * sqrt(same$n[i])
      if (same$sd[i] < params$sd_ratio * typical &&
            abs(as_sd - typical) / typical < params$se_closeness) {
        alerts[[length(alerts) + 1]] <- list(
          study_id = same$study[i], arm = same$arm[i], code = "possible_se_as_sd",
          values = list(sd = same$sd[i], n = same$n[i], typical_sd = typical, sd_times_sqrt_n = as_sd)
        )
      }
    }
  }
  alerts
}

#' Reported p value against the p recomputed from means, SDs and n (two-sample t test,
#' pooled variance).
p_alerts <- function(comparisons, params) {
  alerts <- list()
  for (c in comparisons) {
    v <- lapply(c[c("n1", "m1", "sd1", "n2", "m2", "sd2", "p_reported")], as.numeric)
    if (any(vapply(v, function(x) length(x) != 1 || !is.finite(x), logical(1)))) next
    if (v$n1 < 2 || v$n2 < 2 || v$p_reported <= 0 || v$p_reported > 1) next
    df <- v$n1 + v$n2 - 2
    sp <- sqrt(((v$n1 - 1) * v$sd1^2 + (v$n2 - 1) * v$sd2^2) / df)
    t <- (v$m1 - v$m2) / (sp * sqrt(1 / v$n1 + 1 / v$n2))
    p <- 2 * stats::pt(-abs(t), df)
    sides_differ <- (p < params$alpha) != (v$p_reported < params$alpha)
    ratio <- max(p, v$p_reported) / max(min(p, v$p_reported), .Machine$double.xmin)
    if (sides_differ || ratio > params$p_factor) {
      alerts[[length(alerts) + 1]] <- list(
        study_id = as.character(c$study_id), arm = NA_character_, code = "p_inconsistent",
        values = list(p_reported = v$p_reported, p_recomputed = p, t = t, df = df)
      )
    }
  }
  alerts
}

plausibility_checks <- function(spec) {
  params <- check_params(spec$params)
  alerts <- c(se_as_sd_alerts(spec$groups, params), p_alerts(spec$comparisons, params))
  envelope(result = list(alerts = alerts), params = params)
}

#' Influence diagnostics (metafor::influence) and improbable effects of a fitted model.
influence_checks <- function(spec) {
  params <- check_params(spec$params)
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test)) "knha" else spec$test
  if (method == "FE") test <- "z"
  errors <- meta_input_errors(spec)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  keep <- !is.na(yi) & !is.na(vi)
  if (sum(keep) < 3) {
    # Leaving one study out needs at least two remaining ones.
    return(envelope(result = list(studies = list()), warnings = "influence_needs_three_studies",
                    params = params))
  }
  run <- with_metafor_warnings({
    fit <- metafor::rma(yi = yi[keep], vi = vi[keep], slab = labels[keep],
                        method = if (method == "FE") "EE" else method, test = test, level = 95)
    stats::influence(fit)
  })
  inf <- run$value
  infl <- as.data.frame(inf$inf)
  is_infl <- inf$is.infl
  value <- function(v) if (spec$measure %in% RATIO) exp(v) else v
  studies <- lapply(seq_len(sum(keep)), function(i) {
    y <- yi[keep][i]
    improbable <- if (spec$measure == "SMD") {
      abs(y) > params$smd_limit
    } else if (spec$measure %in% RATIO) {
      value(y) < params$ratio_low || value(y) > params$ratio_high
    } else {
      FALSE
    }
    list(
      label = labels[keep][i],
      influential = isTRUE(is_infl[i]),
      improbable = isTRUE(improbable),
      rstudent = infl$rstudent[i],
      cook_d = infl$cook.d[i],
      hat = infl$hat[i]
    )
  })
  envelope(result = list(studies = studies), warnings = run$warnings,
           params = c(params, list(method = method, test = test)))
}
