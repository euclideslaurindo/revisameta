# Forest plot (docs/modulos.md 7.7; metafor::forest).
#
# Studies with their effects and weights, the pooled effect (diamond) and the
# prediction interval, with the side each direction favours written under the axis.
# Studies whose data were converted or estimated are marked and explained in a note
# (7.7, "dados convertidos ou estimados: marca no grafico").
#
# Input: the same request as /meta-analysis (yi/vi per study, measure, method, test)
# plus `markers` (one per study: "", "converted", "estimated", "derived") and `texts`
# in the output language: study, effect, favours_left, favours_right, model, note_*.
# `decimal_mark` is "," for Portuguese outputs.

forest_input_errors <- function(spec) {
  errors <- meta_input_errors(spec)
  if (!all(c("yi", "vi") %in% names(spec$data))) errors <- c(errors, "forest plots take yi and vi per study")
  if (!isTRUE(spec$format %in% c("svg", "png"))) errors <- c(errors, "format must be svg or png")
  if (is.null(spec$texts)) errors <- c(errors, "texts are required")
  errors
}

#' Round values for the axis of ratio measures (0.1, 0.2, 0.5, 1, 2, 5...), on the log
#' scale, covering every confidence interval. Powers of e (0.37, 2.72) are hard to read.
ratio_ticks <- function(fit) {
  z <- stats::qnorm(0.975)
  lo <- min(fit$yi - z * sqrt(fit$vi), fit$ci.lb)
  hi <- max(fit$yi + z * sqrt(fit$vi), fit$ci.ub)
  nice <- c(0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100)
  inside <- nice[log(nice) >= lo & log(nice) <= hi]
  below <- utils::tail(nice[log(nice) < lo], 1)
  above <- utils::head(nice[log(nice) > hi], 1)
  log(sort(unique(c(below, inside, 1, above))))
}

forest_plot <- function(spec) {
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test)) "knha" else spec$test
  if (method == "FE") test <- "z"
  params <- list(measure = spec$measure, method = method, test = test, format = spec$format)
  errors <- forest_input_errors(spec)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  keep <- !is.na(yi) & !is.na(vi)
  if (sum(keep) < 2) {
    return(envelope(errors = "at least two studies with an effect are needed", params = params))
  }
  markers <- if (is.null(spec$markers)) rep("", length(yi)) else vapply(spec$markers, as.character, character(1))
  symbol <- c(converted = "†", estimated = "*", derived = "‡")
  shown <- ifelse(markers %in% names(symbol), paste0(labels, " ", symbol[markers]), labels)
  run <- with_metafor_warnings(metafor::rma(
    yi = yi[keep], vi = vi[keep], slab = shown[keep],
    method = if (method == "FE") "EE" else method, test = test, level = 95
  ))
  fit <- run$value
  texts <- spec$texts
  ratio <- spec$measure %in% RATIO
  k <- fit$k
  size <- list(width = 9.5, height = 2.6 + 0.32 * k)
  notes <- character()
  used <- unique(markers[keep & markers %in% names(symbol)])
  for (m in used) notes <- c(notes, paste(symbol[[m]], texts[[paste0("note_", m)]]))

  draw <- function() {
    old <- options(OutDec = if (identical(spec$decimal_mark, ",")) "," else ".")
    on.exit(options(old), add = TRUE)
    graphics::par(mar = c(3.6 + 1.2 * length(notes), 4, 1, 2))
    metafor::forest(
      fit,
      addpred = method != "FE",
      showweights = TRUE,
      header = c(texts$study, texts$effect),
      xlab = "",
      mlab = texts$model,
      atransf = if (ratio) exp else NULL,
      at = if (ratio) ratio_ticks(fit) else NULL,
      refline = 0,
      cex = 0.85
    )
    # In the margin under the plot region, below the axis numbers: never overlapping them.
    graphics::mtext(paste0("← ", texts$favours_left), side = 1, line = 2.2, at = 0, adj = 1.05, cex = 0.8)
    graphics::mtext(paste0(texts$favours_right, " →"), side = 1, line = 2.2, at = 0, adj = -0.05, cex = 0.8)
    if (length(notes) > 0) {
      for (i in seq_along(notes)) {
        graphics::mtext(notes[i], side = 1, line = 3.6 + 1.1 * (i - 1), adj = 0, cex = 0.7,
                        at = graphics::par("usr")[1])
      }
    }
  }
  path <- tempfile(fileext = paste0(".", spec$format))
  on.exit(unlink(path))
  if (spec$format == "svg") {
    grDevices::svg(path, width = size$width, height = size$height)
  } else {
    grDevices::png(path, width = size$width, height = size$height, units = "in", res = 300, type = "cairo")
  }
  draw()
  grDevices::dev.off()
  bytes <- readBin(path, "raw", file.info(path)$size)
  envelope(
    result = list(
      content_type = if (spec$format == "svg") "image/svg+xml" else "image/png",
      file_base64 = jsonlite::base64_enc(bytes),
      k = k,
      width_in = size$width,
      height_in = size$height
    ),
    warnings = run$warnings,
    params = params
  )
}
