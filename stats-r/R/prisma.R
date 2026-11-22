# PRISMA 2020 flow diagram (docs/modulos.md 7.9; stage 5 step 6).
#
# Drawn with grid (part of base R, no new package). The backend sends the text of every
# box already written in the output language, with the counts in it; this function only
# lays out the boxes and arrows of the PRISMA 2020 template for new reviews: on the
# left, from top to bottom, identified, screened, sought, assessed and included; on the
# right of each of the first four, what left the flow at that step. Three bands name
# the phases (identification; screening; included).
#
# Body: { format: svg|png, phases: [identification, screening, included], title,
#         boxes: { identified, removed, screened, screened_excluded, sought,
#                  not_retrieved, assessed, assessed_excluded, included } }

PRISMA_BOXES <- c(
  "identified", "removed", "screened", "screened_excluded", "sought",
  "not_retrieved", "assessed", "assessed_excluded", "included"
)

prisma_input_errors <- function(spec) {
  errors <- character()
  if (!isTRUE(spec$format %in% c("svg", "png"))) errors <- c(errors, "format must be svg or png")
  missing <- setdiff(PRISMA_BOXES, names(spec$boxes))
  if (length(missing) > 0) errors <- c(errors, paste("missing boxes:", paste(missing, collapse = ", ")))
  if (length(spec$phases) != 3) errors <- c(errors, "phases needs three labels")
  errors
}

prisma_lines <- function(text) {
  length(strsplit(as.character(text), "\n", fixed = TRUE)[[1]])
}

prisma_flow <- function(spec) {
  params <- list(format = spec$format)
  errors <- prisma_input_errors(spec)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  boxes <- lapply(spec$boxes, as.character)
  # Row heights follow the longest text of each row, so long lists of reasons fit.
  rows <- list(
    c("identified", "removed"), c("screened", "screened_excluded"),
    c("sought", "not_retrieved"), c("assessed", "assessed_excluded"), c("included")
  )
  line_in <- 0.19
  heights <- vapply(rows, function(r) max(vapply(boxes[r], prisma_lines, numeric(1))) * line_in + 0.35, numeric(1))
  gap <- 0.35
  width <- 9
  height <- sum(heights) + gap * (length(rows) - 1) + 0.9
  path <- tempfile(fileext = paste0(".", spec$format))
  on.exit(unlink(path))
  if (spec$format == "svg") {
    grDevices::svg(path, width = width, height = height)
  } else {
    grDevices::png(path, width = width, height = height, units = "in", res = 300, type = "cairo")
  }
  grid::grid.newpage()
  inch <- function(v) grid::unit(v, "inches")
  top <- height - 0.6
  if (!is.null(spec$title)) {
    grid::grid.text(spec$title, x = inch(width / 2), y = inch(height - 0.3),
                    gp = grid::gpar(fontsize = 12, fontface = "bold"))
  }
  left_x <- 1.0
  left_w <- 4.0
  right_x <- 5.5
  right_w <- 3.3
  centres <- list()
  y <- top
  for (i in seq_along(rows)) {
    h <- heights[i]
    cy <- y - h / 2
    draw_box <- function(key, x, w) {
      grid::grid.rect(x = inch(x + w / 2), y = inch(cy), width = inch(w), height = inch(h),
                      gp = grid::gpar(fill = "#FFFFFF", col = "#000000", lwd = 1))
      grid::grid.text(boxes[[key]], x = inch(x + 0.12), y = inch(cy), just = "left",
                      gp = grid::gpar(fontsize = 8.5, lineheight = 1.05))
    }
    draw_box(rows[[i]][1], left_x, left_w)
    centres[[i]] <- c(cy, h)
    if (length(rows[[i]]) > 1) {
      draw_box(rows[[i]][2], right_x, right_w)
      grid::grid.lines(x = inch(c(left_x + left_w, right_x)), y = inch(c(cy, cy)),
                       arrow = grid::arrow(length = grid::unit(0.08, "inches"), type = "closed"),
                       gp = grid::gpar(fill = "#000000"))
    }
    if (i > 1) {
      prev <- centres[[i - 1]]
      grid::grid.lines(x = inch(c(left_x + left_w / 2, left_x + left_w / 2)),
                       y = inch(c(prev[1] - prev[2] / 2, cy + h / 2)),
                       arrow = grid::arrow(length = grid::unit(0.08, "inches"), type = "closed"),
                       gp = grid::gpar(fill = "#000000"))
    }
    y <- y - h - gap
  }
  # Phase bands on the left: identification (row 1), screening (rows 2-4), included (row 5).
  band <- function(label, first, last) {
    y_top <- centres[[first]][1] + centres[[first]][2] / 2
    y_bottom <- centres[[last]][1] - centres[[last]][2] / 2
    grid::grid.rect(x = inch(0.45), y = inch((y_top + y_bottom) / 2), width = inch(0.35),
                    height = inch(y_top - y_bottom), gp = grid::gpar(fill = "#C6DBEF", col = "#6A9ACB"))
    grid::grid.text(label, x = inch(0.45), y = inch((y_top + y_bottom) / 2), rot = 90,
                    gp = grid::gpar(fontsize = 9, fontface = "bold"))
  }
  band(spec$phases[[1]], 1, 1)
  band(spec$phases[[2]], 2, 4)
  band(spec$phases[[3]], 5, 5)
  grDevices::dev.off()
  bytes <- readBin(path, "raw", file.info(path)$size)
  envelope(
    result = list(
      content_type = if (spec$format == "svg") "image/svg+xml" else "image/png",
      file_base64 = jsonlite::base64_enc(bytes),
      width_in = width,
      height_in = height
    ),
    params = params
  )
}
