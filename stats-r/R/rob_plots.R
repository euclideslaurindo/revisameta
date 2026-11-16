# Risk-of-bias plots: traffic light and summary (docs/modulos.md 7.6, ADR-013).
#
# The backend sends a normalized table: columns (domains, or questions for checklists),
# the levels that may appear (key + translated label, best first) and one row per
# study. Colours and symbols are chosen here from the level keys, always with a text
# label in the legend (10.3).
#
# Engine:
# - robvis "Generic" template (pinned commit) when every level maps to its own robvis
#   category (RoB 2, ROBINS-I 2016). Levels are passed as the English words robvis
#   reduces to its letters, never as the labels people read: robvis classifies by
#   first letter, so "No"/"Não" would otherwise turn into "No information".
# - Otherwise a ggplot2 plot with the same look (ROBINS-I V2 and ROBINS-E, whose
#   "low except for confounding" has no robvis category; JBI, Newcastle-Ottawa and
#   generic checklists, whose columns hold answers, not judgements).

.data <- ggplot2::.data

ROB_COCHRANE <- list(
  low = "#02C100", concerns = "#E2DF07", high = "#BF0000",
  critical = "#820000", ni = "#4EA1F7", na = "#CCCCCC", low_conf = "#8FD98A",
  probably_low = "#8FD98A", probably_high = "#F08C00"
)

# key -> robvis letter (only for levels that robvis can show).
ROBVIS_CODES <- c(
  low = "l", some_concerns = "s", moderate = "s", high = "h", serious = "h",
  critical = "c", very_high = "c", no_information = "n", not_applicable = "x"
)

#' Colour and symbol of a level key. Unknown keys are refused, never guessed.
rob_level_style <- function(key) {
  stars <- regmatches(key, regexec("^stars_(\\d+)_of_(\\d+)$", key))[[1]]
  if (length(stars) == 3) {
    n <- as.integer(stars[2])
    max <- as.integer(stars[3])
    colour <- if (n >= max) ROB_COCHRANE$low else if (n == 0) ROB_COCHRANE$high else ROB_COCHRANE$concerns
    return(list(colour = colour, symbol = as.character(n)))
  }
  styles <- list(
    low = list(ROB_COCHRANE$low, "+"),
    good = list(ROB_COCHRANE$low, "+"),
    Y = list(ROB_COCHRANE$low, "+"),
    SY = list(ROB_COCHRANE$low, "+"),
    PY = list(ROB_COCHRANE$probably_low, "+"),
    WY = list(ROB_COCHRANE$probably_low, "+"),
    low_except_confounding = list(ROB_COCHRANE$low_conf, "+"),
    some_concerns = list(ROB_COCHRANE$concerns, "-"),
    moderate = list(ROB_COCHRANE$concerns, "-"),
    fair = list(ROB_COCHRANE$concerns, "-"),
    U = list(ROB_COCHRANE$concerns, "?"),
    PN = list(ROB_COCHRANE$probably_high, "-"),
    WN = list(ROB_COCHRANE$probably_high, "-"),
    high = list(ROB_COCHRANE$high, "x"),
    serious = list(ROB_COCHRANE$high, "x"),
    poor = list(ROB_COCHRANE$high, "x"),
    N = list(ROB_COCHRANE$high, "x"),
    SN = list(ROB_COCHRANE$high, "x"),
    critical = list(ROB_COCHRANE$critical, "!"),
    very_high = list(ROB_COCHRANE$critical, "!"),
    no_information = list(ROB_COCHRANE$ni, "?"),
    NI = list(ROB_COCHRANE$ni, "?"),
    not_applicable = list(ROB_COCHRANE$na, ""),
    `NA` = list(ROB_COCHRANE$na, "")
  )
  style <- styles[[key]]
  if (is.null(style)) {
    return(NULL)
  }
  list(colour = style[[1]], symbol = style[[2]])
}

rob_plot_input_errors <- function(spec) {
  errors <- character()
  if (!spec$kind %in% c("traffic_light", "summary")) errors <- c(errors, "kind must be traffic_light or summary")
  if (!spec$format %in% c("svg", "png")) errors <- c(errors, "format must be svg or png")
  if (length(spec$columns) == 0) errors <- c(errors, "at least one column is required")
  if (length(spec$studies) == 0) errors <- c(errors, "at least one study is required")
  if (length(spec$levels) == 0) errors <- c(errors, "levels are required")
  keys <- vapply(spec$levels, function(l) l$key, character(1))
  unknown <- keys[vapply(keys, function(k) is.null(rob_level_style(k)), logical(1))]
  if (length(unknown) > 0) errors <- c(errors, paste("unknown level:", unknown))
  used <- unlist(lapply(spec$studies, function(s) c(unlist(s$values), s$overall)))
  stray <- setdiff(unique(used[!is.na(used)]), keys)
  if (length(stray) > 0) errors <- c(errors, paste("value not in levels:", stray))
  errors
}

#' Long table: one row per study and column (overall last), NA where empty.
rob_long <- function(spec) {
  col_keys <- vapply(spec$columns, function(c) c$key, character(1))
  shorts <- vapply(spec$columns, function(c) c$short, character(1))
  rows <- list()
  for (s in spec$studies) {
    for (i in seq_along(col_keys)) {
      v <- s$values[[col_keys[i]]]
      rows[[length(rows) + 1]] <- data.frame(
        study = s$label, column = shorts[i],
        level = if (is.null(v)) NA_character_ else v
      )
    }
    if (isTRUE(spec$overall)) {
      v <- s$overall
      rows[[length(rows) + 1]] <- data.frame(
        study = s$label, column = spec$texts$overall,
        level = if (is.null(v)) NA_character_ else v
      )
    }
  }
  long <- do.call(rbind, rows)
  columns <- c(shorts, if (isTRUE(spec$overall)) spec$texts$overall)
  long$column <- factor(long$column, levels = columns)
  long$study <- factor(long$study, levels = rev(unique(vapply(spec$studies, function(s) s$label, character(1)))))
  long
}

rob_caption <- function(spec) {
  paste(vapply(spec$columns, function(c) paste0(c$short, ": ", c$name), character(1)), collapse = "\n")
}

#' robvis can show the levels only when each has its own robvis category.
rob_use_robvis <- function(spec) {
  keys <- vapply(spec$levels, function(l) l$key, character(1))
  codes <- ROBVIS_CODES[keys]
  !anyNA(codes) && !anyDuplicated(codes)
}

rob_wrap <- function(text, width = 40) {
  vapply(text, function(t) paste(strwrap(t, width), collapse = "\n"), character(1), USE.NAMES = FALSE)
}

rob_plot_robvis <- function(spec) {
  keys <- vapply(spec$levels, function(l) l$key, character(1))
  labels <- vapply(spec$levels, function(l) l$label, character(1))
  code_of <- ROBVIS_CODES[keys]
  names(code_of) <- keys
  # robvis reduces each word to its initial; these words give exactly its letters.
  word_of <- c(l = "Low", s = "Some concerns", h = "High", c = "Critical", n = "No information")
  as_word <- function(v) if (is.null(v)) NA_character_ else unname(word_of[code_of[[v]]])
  data <- data.frame(Study = vapply(spec$studies, function(s) s$label, character(1)))
  for (c in spec$columns) {
    data[[c$name]] <- vapply(spec$studies, function(s) {
      as_word(s$values[[c$key]])
    }, character(1))
  }
  if (isTRUE(spec$overall)) {
    data[[spec$texts$overall]] <- vapply(spec$studies, function(s) {
      as_word(s$overall)
    }, character(1))
  }
  data$Weight <- 1
  # robvis wants one label per category, in its own order.
  by_code <- setNames(labels, code_of)
  slot <- function(code, fallback) {
    if (!is.na(by_code[code])) unname(by_code[code]) else fallback
  }
  shorts <- vapply(spec$columns, function(c) c$short, character(1))
  if (spec$kind == "traffic_light") {
    plot <- robvis::rob_traffic_light(
      data,
      tool = "Generic", overall = isTRUE(spec$overall), psize = 10,
      domain_shortcodes = shorts,
      x_title = spec$texts$x_title, y_title = spec$texts$y_title,
      judgement_title = spec$texts$judgement_title,
      judgement_labels = c(
        slot("c", "Critical"), slot("h", "High"), slot("s", "Some concerns"),
        slot("l", "Low"), slot("n", "No information"), spec$texts$not_applicable
      )
    )
  } else {
    plot <- robvis::rob_summary(
      data,
      tool = "Generic", overall = isTRUE(spec$overall), weighted = FALSE,
      judgement_labels = c(
        slot("l", "Low"), slot("s", "Some concerns"), slot("h", "High"),
        slot("c", "Critical"), slot("n", "No information")
      )
    )
    plot <- plot + ggplot2::labs(fill = spec$texts$judgement_title)
  }
  plot
}

rob_plot_own <- function(spec) {
  long <- rob_long(spec)
  keys <- vapply(spec$levels, function(l) l$key, character(1))
  labels <- vapply(spec$levels, function(l) l$label, character(1))
  colours <- vapply(keys, function(k) rob_level_style(k)$colour, character(1))
  symbols <- vapply(keys, function(k) rob_level_style(k)$symbol, character(1))
  names(colours) <- keys
  names(labels) <- keys
  present <- keys[keys %in% long$level]
  if (spec$kind == "traffic_light") {
    filled <- long[!is.na(long$level), ]
    filled$symbol <- symbols[filled$level]
    filled$level <- factor(filled$level, levels = keys)
    plot <- ggplot2::ggplot(filled, ggplot2::aes(x = .data[["column"]], y = .data[["study"]])) +
      ggplot2::geom_tile(data = long, fill = "#FFFFFF", colour = "#DDDDDD") +
      ggplot2::geom_point(ggplot2::aes(fill = .data[["level"]]), shape = 21, colour = "#000000", size = 9) +
      ggplot2::geom_text(ggplot2::aes(label = .data[["symbol"]]), colour = "#000000", size = 5, vjust = 0.4) +
      ggplot2::scale_fill_manual(
        values = colours, breaks = present, labels = unname(labels[present]), drop = TRUE
      ) +
      ggplot2::scale_x_discrete(position = "top", drop = FALSE) +
      ggplot2::scale_y_discrete(labels = function(x) rob_wrap(x, 35)) +
      ggplot2::labs(
        x = spec$texts$x_title, y = spec$texts$y_title, fill = spec$texts$judgement_title,
        caption = rob_caption(spec)
      ) +
      ggplot2::theme_minimal(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        legend.position = "bottom",
        legend.direction = "vertical",
        plot.caption = ggplot2::element_text(hjust = 0, size = 9),
        axis.text.x.top = ggplot2::element_text(face = "bold")
      ) +
      ggplot2::guides(fill = ggplot2::guide_legend(
        override.aes = list(size = 5), ncol = 2
      ))
  } else {
    counted <- long
    counted$level[is.na(counted$level)] <- "no_information"
    counted <- counted[counted$level %in% keys | counted$level == "no_information", ]
    counted$level <- factor(counted$level, levels = rev(unique(c(keys, "no_information"))))
    if (!"no_information" %in% keys) {
      colours <- c(colours, no_information = ROB_COCHRANE$ni)
      labels <- c(labels, no_information = spec$texts$no_information)
    }
    counted$column <- factor(counted$column, levels = rev(levels(long$column)))
    shown <- intersect(c(keys, "no_information"), unique(as.character(counted$level)))
    plot <- ggplot2::ggplot(counted, ggplot2::aes(y = .data[["column"]], fill = .data[["level"]])) +
      ggplot2::geom_bar(position = "fill", width = 0.7, colour = "#000000", linewidth = 0.3) +
      ggplot2::scale_x_continuous(
        labels = function(x) paste0(round(x * 100), "%"),
        expand = ggplot2::expansion(mult = c(0, 0.03))
      ) +
      ggplot2::scale_fill_manual(
        values = colours, breaks = shown, labels = unname(labels[shown])
      ) +
      ggplot2::labs(x = NULL, y = NULL, fill = spec$texts$judgement_title, caption = rob_caption(spec)) +
      ggplot2::theme_minimal(base_size = 12) +
      ggplot2::theme(
        legend.position = "bottom",
        legend.direction = "vertical",
        panel.grid = ggplot2::element_blank(),
        plot.caption = ggplot2::element_text(hjust = 0, size = 9)
      ) +
      ggplot2::guides(fill = ggplot2::guide_legend(ncol = 2))
  }
  plot
}

#' Size of the figure in inches: grows with the number of studies and columns.
rob_plot_size <- function(spec) {
  n_studies <- length(spec$studies)
  n_columns <- length(spec$columns) + if (isTRUE(spec$overall)) 1 else 0
  longest <- max(nchar(vapply(spec$studies, function(s) s$label, character(1))))
  if (spec$kind == "traffic_light") {
    width <- 3 + min(longest, 35) * 0.09 + n_columns * 0.65
    height <- 3 + n_studies * 0.5 + length(spec$columns) * 0.18
  } else {
    width <- 10
    height <- 2.5 + n_columns * 0.45 + length(spec$columns) * 0.18
  }
  list(width = max(width, 6), height = height)
}

rob_render <- function(plot, format, size) {
  path <- tempfile(fileext = paste0(".", format))
  on.exit(unlink(path))
  if (format == "svg") {
    grDevices::svg(path, width = size$width, height = size$height)
  } else {
    grDevices::png(path, width = size$width, height = size$height, units = "in", res = 300, type = "cairo")
  }
  print(plot)
  grDevices::dev.off()
  readBin(path, "raw", file.info(path)$size)
}

#' Builds the plot (without rendering it): used by the route and by the tests.
rob_plot_object <- function(spec) {
  if (rob_use_robvis(spec)) {
    list(engine = "robvis", plot = rob_plot_robvis(spec))
  } else {
    list(engine = "ggplot2", plot = rob_plot_own(spec))
  }
}

rob_plot <- function(spec) {
  params <- list(kind = spec$kind, format = spec$format, studies = length(spec$studies))
  errors <- rob_plot_input_errors(spec)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  built <- rob_plot_object(spec)
  size <- rob_plot_size(spec)
  bytes <- rob_render(built$plot, spec$format, size)
  params$engine <- built$engine
  envelope(
    result = list(
      content_type = if (spec$format == "svg") "image/svg+xml" else "image/png",
      file_base64 = jsonlite::base64_enc(bytes),
      engine = built$engine,
      width_in = size$width,
      height_in = size$height
    ),
    params = params
  )
}
