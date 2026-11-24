# Multilevel model for dependent effects (docs/modulos.md 7.7, P2; stage 8 step 2).
#
# Several effects from the same study (e.g. the same outcome at different time points)
# must not count as independent studies. metafor::rma.mv with random effects for the
# study and for the effect within the study (random = ~ 1 | study/effect). REML or ML;
# Wald (z) or t-based test. Fewer than 5 studies keeps the usual warning that the
# variance components are unstable.

multilevel_analysis <- function(spec) {
  method <- if (is.null(spec$method) || spec$method %in% c("DL", "PM", "FE")) "REML" else spec$method
  test <- if (identical(spec$test, "knha") || identical(spec$test, "t")) "t" else "z"
  params <- list(measure = spec$measure, method = method, test = test)
  plain <- spec
  plain$data$study <- NULL
  plain$method <- NULL  # rma.mv takes REML or ML, checked above
  errors <- meta_input_errors(plain)
  if (is.null(spec$data$study) || length(spec$data$study) != length(spec$data$label)) {
    errors <- c(errors, "multilevel needs one study (cluster) per effect")
  }
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  study <- vapply(spec$data$study, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  keep <- !is.na(yi) & !is.na(vi)
  clusters <- length(unique(study[keep]))
  if (clusters < 2) {
    return(envelope(errors = "multilevel needs effects from at least two studies", params = params))
  }
  data <- data.frame(yi = yi[keep], vi = vi[keep], study = study[keep], effect = seq_len(sum(keep)))
  run <- with_metafor_warnings(metafor::rma.mv(
    yi = data$yi, V = data$vi, random = ~ 1 | study / effect, data = data, method = method, test = test, level = 95
  ))
  fit <- run$value
  warnings <- run$warnings
  if (clusters < 5) warnings <- c(warnings, "fewer_than_five_studies")
  pred <- stats::predict(fit, level = 95)
  pooled <- list(
    estimate = as.numeric(fit$beta), se = as.numeric(fit$se), ci_lb = fit$ci.lb, ci_ub = fit$ci.ub,
    statistic = fit$zval, statistic_kind = test, p_value = fit$pval,
    pi_lb = as.numeric(pred$pi.lb), pi_ub = as.numeric(pred$pi.ub)
  )
  if (spec$measure %in% RATIO) {
    pooled$exp <- list(estimate = exp(pooled$estimate), ci_lb = exp(fit$ci.lb), ci_ub = exp(fit$ci.ub),
                       pi_lb = exp(as.numeric(pred$pi.lb)), pi_ub = exp(as.numeric(pred$pi.ub)))
  }
  envelope(
    result = list(
      k = sum(keep),
      studies = clusters,
      pooled = pooled,
      variance = list(between_studies = fit$sigma2[1], within_studies = fit$sigma2[2]),
      heterogeneity = list(q = fit$QE, q_df = fit$k - fit$p, q_p = fit$QEp),
      effects = lapply(seq_len(sum(keep)), function(i) {
        list(label = labels[keep][i], study = study[keep][i], yi = yi[keep][i], vi = vi[keep][i])
      })
    ),
    warnings = unique(warnings),
    params = params
  )
}
