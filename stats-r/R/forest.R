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
#
# Optional `rob` (ADR-014): the risk-of-bias traffic light drawn beside each study, one
# column per domain (or checklist question) plus the overall judgement, with the same
# colours and symbols as /rob-plots and a text legend (10.3). Shape:
# { columns: [{short, name}], levels: [{key, label}],
#   studies: [{values: [level or null per column], overall}] }  (same order as data)
# A study without a final assessment gets empty cells and a note; it is never hidden.

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

rob_input_errors <- function(rob, n) {
  if (is.null(rob)) return(character())
  if (length(rob$studies) != n) return("rob needs one entry per study")
  keys <- unlist(lapply(rob$studies, function(st) c(unlist(st$values), st$overall)))
  known <- vapply(unique(keys), function(k) !is.null(rob_level_style(k)), logical(1))
  unknown <- unique(keys)[!known]
  if (length(unknown) > 0) return(paste("unknown risk-of-bias level:", paste(unknown, collapse = ", ")))
  character()
}

#' Draws the traffic light columns to the left of the effects, at the study rows.
draw_rob_columns <- function(rob, rows, xpos, header_y, texts) {
  heads <- c(vapply(rob$columns, function(c) as.character(c$short), character(1)), texts$rob_overall)
  graphics::text(xpos, header_y, heads, font = 2, cex = 0.75)
  for (i in seq_along(rob$studies)) {
    st <- rob$studies[[i]]
    cells <- c(lapply(st$values, function(v) v), list(st$overall))
    for (j in seq_along(cells)) {
      key <- cells[[j]]
      if (is.null(key)) next
      style <- rob_level_style(key)
      graphics::points(xpos[j], rows[i], pch = 21, bg = style$colour, col = "#000000", cex = 2.1)
      graphics::text(xpos[j], rows[i], style$symbol, cex = 0.7, font = 2)
    }
  }
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
  rob_errors <- rob_input_errors(spec$rob, length(yi))
  if (length(rob_errors) > 0) {
    return(envelope(errors = rob_errors, params = params))
  }
  rob <- spec$rob
  if (!is.null(rob)) rob$studies <- rob$studies[keep]
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
  n_rob <- 0
  if (!is.null(rob)) {
    n_rob <- length(rob$columns) + 1
    size$width <- size$width + 0.45 * n_rob
    names_line <- paste(vapply(rob$columns, function(c) paste0(c$short, ": ", c$name), character(1)),
                        collapse = "; ")
    shown_levels <- Filter(function(l) !is.null(rob_level_style(l$key)), rob$levels)
    legend_line <- paste(vapply(shown_levels, function(l) {
      paste0("(", rob_level_style(l$key)$symbol, ") ", l$label)
    }, character(1)), collapse = "   ")
    notes <- c(notes, paste0(texts$rob_title, " — ", names_line), legend_line)
    missing <- vapply(rob$studies, function(st) is.null(st$overall), logical(1))
    if (any(missing)) notes <- c(notes, texts$rob_missing)
  }

  draw <- function() {
    old <- options(OutDec = if (identical(spec$decimal_mark, ",")) "," else ".")
    on.exit(options(old), add = TRUE)
    graphics::par(mar = c(3.6 + 1.2 * length(notes), 4, 1, 2))
    z <- stats::qnorm(0.975)
    lo <- min(fit$yi - z * sqrt(fit$vi), fit$ci.lb)
    hi <- max(fit$yi + z * sqrt(fit$vi), fit$ci.ub)
    width <- hi - lo
    xlim <- if (n_rob > 0) c(lo - width * (1.6 + 0.28 * n_rob), hi + width * 1.3) else NULL
    args <- list(
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
    if (!is.null(xlim)) args$xlim <- xlim
    drawn <- do.call(metafor::forest, args)
    if (n_rob > 0) {
      step <- width * 0.28
      xpos <- lo - width * 0.25 - step * rev(seq_len(n_rob) - 1)
      draw_rob_columns(rob, drawn$rows, xpos, max(drawn$rows) + 2, texts)
    }
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
