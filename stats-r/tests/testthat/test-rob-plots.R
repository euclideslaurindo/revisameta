texts_pt <- list(
  overall = "Geral", x_title = "Domínios", y_title = "Estudo",
  judgement_title = "Julgamento", not_applicable = "Não se aplica",
  no_information = "Sem informação"
)

domains <- function(values) setNames(as.list(values), paste0("d", seq_along(values)))

robins_2016_spec <- function(kind = "traffic_light", format = "svg") {
  list(
    kind = kind, format = format, overall = TRUE, texts = texts_pt,
    columns = lapply(1:7, function(i) list(key = paste0("d", i), short = paste0("D", i), name = paste("Domínio", i))),
    levels = list(
      list(key = "low", label = "Baixo"), list(key = "moderate", label = "Moderado"),
      list(key = "serious", label = "Grave"), list(key = "critical", label = "Crítico"),
      list(key = "no_information", label = "Sem informação")
    ),
    studies = list(
      list(
        label = "Estudo A 2020", overall = "serious",
        values = domains(c("low", "serious", "no_information", "low", "moderate", "low", "low"))
      ),
      list(
        label = "Estudo B 2019", overall = "critical",
        values = domains(c("no_information", "low", "low", "critical", "low", "low", "low"))
      )
    )
  )
}

jbi_spec <- function(n_studies = 2, label = function(i) paste("Estudo", i)) {
  list(
    kind = "traffic_light", format = "svg", overall = TRUE, texts = texts_pt,
    columns = lapply(1:11, function(i) list(key = paste0("q", i), short = paste0("P", i), name = paste("Pergunta", i))),
    levels = list(
      list(key = "Y", label = "Sim"), list(key = "U", label = "Incerto"),
      list(key = "N", label = "Não"), list(key = "NA", label = "Não se aplica"),
      list(key = "low", label = "Baixo"), list(key = "high", label = "Alto")
    ),
    studies = lapply(seq_len(n_studies), function(i) {
      list(
        label = label(i),
        values = setNames(as.list(rep(c("Y", "N", "U", "NA"), length.out = 11)), paste0("q", 1:11)),
        overall = if (i %% 2 == 0) "high" else "low"
      )
    })
  )
}

legend_labels <- function(plot) {
  built <- ggplot2::ggplot_build(plot)
  scale <- built$plot$scales$get_scales("colour")
  if (is.null(scale)) scale <- built$plot$scales$get_scales("fill")
  scale$get_labels()
}

test_that("ROBINS-I 2016 uses robvis and shows 'Sem informação' and 'Grave' together", {
  built <- rob_plot_object(robins_2016_spec())
  expect_equal(built$engine, "robvis")
  labels <- legend_labels(built$plot)
  expect_true(all(c("Sem informação", "Grave", "Crítico", "Baixo", "Moderado") %in% labels))
  data <- built$plot$data
  expect_true(all(c("n", "h", "c", "l", "s") %in% as.character(data$judgement)))
})

test_that("levels reach robvis by key, so a label like 'No' never becomes 'No information'", {
  spec <- robins_2016_spec()
  spec$levels[[1]]$label <- "No" # the label of "low" starts with N; only the legend shows it
  built <- rob_plot_object(spec)
  judgements <- as.character(built$plot$data$judgement)
  expect_equal(sum(judgements == "l"), 9) # every "low" cell: 4 in study A, 5 in study B
  expect_equal(sum(judgements == "n"), 2) # only the two real "no information" cells
  expect_true("No" %in% legend_labels(built$plot))
})

test_that("JBI checklists use the ggplot2 plot with answers and the overall judgement", {
  built <- rob_plot_object(jbi_spec())
  expect_equal(built$engine, "ggplot2")
  labels <- legend_labels(built$plot)
  expect_true(all(c("Sim", "Não", "Incerto", "Não se aplica", "Baixo", "Alto") %in% labels))
  expect_equal(levels(built$plot$data$column), c(paste0("P", 1:11), "Geral"))
})

test_that("ROBINS-I V2 'low except confounding' keeps its own colour", {
  spec <- robins_2016_spec()
  extra <- list(key = "low_except_confounding", label = "Baixo (exceto confundimento)")
  spec$levels <- append(spec$levels, list(extra), 1)
  spec$studies[[1]]$values$d1 <- "low_except_confounding"
  built <- rob_plot_object(spec)
  expect_equal(built$engine, "ggplot2")
  expect_true("Baixo (exceto confundimento)" %in% legend_labels(built$plot))
})

test_that("Newcastle-Ottawa stars are coloured by the share of the maximum", {
  expect_equal(rob_level_style("stars_2_of_2")$colour, ROB_COCHRANE$low)
  expect_equal(rob_level_style("stars_1_of_2")$colour, ROB_COCHRANE$concerns)
  expect_equal(rob_level_style("stars_0_of_1")$colour, ROB_COCHRANE$high)
  expect_equal(rob_level_style("stars_1_of_2")$symbol, "1")
})

test_that("many studies with long names render, and the figure grows with them", {
  long_name <- function(i) paste("Estudo de coorte retrospectiva multicêntrica número", i, "(2021)")
  small <- jbi_spec(2)
  big <- jbi_spec(40, long_name)
  expect_gt(rob_plot_size(big)$height, rob_plot_size(small)$height)
  out <- rob_plot(big)
  expect_true(out$ok)
  svg <- rawToChar(jsonlite::base64_dec(out$result$file_base64))
  expect_match(svg, "<svg", fixed = TRUE)
  # Long names wrap instead of overlapping the plot.
  expect_true(all(grepl("\n", rob_wrap(long_name(1), 35))))
})

test_that("summary plots and PNG at 300 dpi render", {
  specs <- list(
    robins_2016_spec("summary", "png"),
    modifyList(jbi_spec(), list(kind = "summary", format = "png"))
  )
  for (spec in specs) {
    out <- rob_plot(spec)
    expect_true(out$ok)
    png <- jsonlite::base64_dec(out$result$file_base64)
    expect_equal(as.integer(png[2:4]), c(0x50, 0x4E, 0x47))
    expect_equal(out$result$content_type, "image/png")
  }
})

test_that("invalid input is refused with a clear error", {
  spec <- jbi_spec()
  spec$studies[[1]]$overall <- "terrible"
  out <- rob_plot(spec)
  expect_false(out$ok)
  expect_match(out$errors[[1]], "value not in levels")
  spec <- jbi_spec()
  spec$levels[[1]]$key <- "maybe"
  expect_match(rob_plot(spec)$errors[[1]], "unknown level")
})
