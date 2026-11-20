# Publication bias: funnel plot and Egger's regression test (docs/modulos.md 7.7;
# metafor::funnel and metafor::regtest).
#
# With fewer than 10 studies both have little power and must not be read as a
# conclusion (CLAUDE.md 0.2): the answer always carries the warning
# "fewer_than_ten_studies" in that case, and Egger is refused below 3 studies.

pb_fit <- function(spec, min_k) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test) || method == "FE") "z" else spec$test
  params <- list(measure = spec$measure, method = method, test = test)
  errors <- meta_input_errors(spec)
  if (!all(c("yi", "vi") %in% names(spec$data))) errors <- c(errors, "publication bias takes yi and vi per study")
  if (length(errors) > 0) return(list(errors = errors, params = params))
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  keep <- !is.na(yi) & !is.na(vi)
  if (sum(keep) < min_k) {
    return(list(errors = sprintf("at least %d studies are needed", min_k), params = params))
  }
  run <- with_metafor_warnings(metafor::rma(
    yi = yi[keep], vi = vi[keep], slab = labels[keep],
    method = if (method == "FE") "EE" else method, test = test, level = 95
  ))
  warnings <- run$warnings
  if (run$value$k < 10) warnings <- c("fewer_than_ten_studies", warnings)
  list(fit = run$value, warnings = warnings, params = params)
}

egger_test <- function(spec) {
  base <- pb_fit(spec, 3)
  if (!is.null(base$errors)) return(envelope(errors = base$errors, params = base$params))
  run <- with_metafor_warnings(metafor::regtest(base$fit, model = "rma", predictor = "sei"))
  reg <- run$value
  envelope(
    result = list(
      k = base$fit$k,
      statistic = as.numeric(reg$zval),
      df = if (is.null(reg$dfs) || is.na(reg$dfs)) NULL else as.numeric(reg$dfs),
      p_value = as.numeric(reg$pval),
      limit_estimate = as.numeric(reg$est),
      limit_ci_lb = as.numeric(reg$ci.lb),
      limit_ci_ub = as.numeric(reg$ci.ub),
      test = if (base$params$test == "knha") "t" else "z"
    ),
    warnings = unique(c(base$warnings, run$warnings)),
    params = base$params
  )
}

funnel_plot <- function(spec) {
  base <- pb_fit(spec, 2)
  if (!is.null(base$errors)) return(envelope(errors = base$errors, params = base$params))
  if (!isTRUE(spec$format %in% c("svg", "png"))) {
    return(envelope(errors = "format must be svg or png", params = base$params))
  }
  texts <- if (is.null(spec$texts)) list() else spec$texts
  ratio <- spec$measure %in% RATIO
  path <- tempfile(fileext = paste0(".", spec$format))
  on.exit(unlink(path))
  if (spec$format == "svg") {
    grDevices::svg(path, width = 7, height = 6)
  } else {
    grDevices::png(path, width = 7, height = 6, units = "in", res = 300, type = "cairo")
  }
  old <- options(OutDec = if (identical(spec$decimal_mark, ",")) "," else ".")
  metafor::funnel(
    base$fit,
    xlab = if (is.null(texts$effect)) "" else texts$effect,
    ylab = if (is.null(texts$se)) "" else texts$se,
    atransf = if (ratio) exp else NULL,
    at = if (ratio) ratio_ticks(base$fit) else NULL
  )
  options(old)
  grDevices::dev.off()
  bytes <- readBin(path, "raw", file.info(path)$size)
  envelope(
    result = list(
      content_type = if (spec$format == "svg") "image/svg+xml" else "image/png",
      file_base64 = jsonlite::base64_enc(bytes),
      k = base$fit$k
    ),
    warnings = base$warnings,
    params = base$params
  )
}
