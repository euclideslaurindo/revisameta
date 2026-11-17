fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "meta-analysis.json"), simplifyVector = FALSE)

texts <- list(
  study = "Estudo", effect = "RR [IC 95%]", favours_left = "Favorece a vacina",
  favours_right = "Favorece o controle", model = "Efeitos aleatórios (REML, Hartung-Knapp)",
  note_converted = "dados convertidos", note_estimated = "média e DP estimados a partir da mediana",
  note_derived = "efeito derivado de t ou p"
)

bcg_spec <- function(format = "svg") {
  case <- Filter(function(c) c$name == "dat.bcg_RR_REML_knha", fixtures$cases)[[1]]
  k <- length(case$request$data$label)
  list(
    measure = "RR", method = "REML", test = "knha", format = format, texts = texts, decimal_mark = ",",
    data = list(label = case$request$data$label, yi = case$expected$yi, vi = case$expected$vi),
    markers = as.list(c("estimated", "converted", rep("", k - 2)))
  )
}

test_that("the forest plot of dat.bcg renders as SVG and PNG", {
  out <- forest_plot(bcg_spec("svg"))
  expect_true(out$ok)
  expect_equal(out$result$k, 13)
  expect_match(rawToChar(jsonlite::base64_dec(out$result$file_base64)), "<svg", fixed = TRUE)
  png <- forest_plot(bcg_spec("png"))
  expect_equal(as.integer(jsonlite::base64_dec(png$result$file_base64)[2:4]), c(0x50, 0x4E, 0x47))
})

test_that("the figure grows with the number of studies", {
  small <- bcg_spec()
  small$data <- lapply(small$data, function(col) col[1:3])
  small$markers <- small$markers[1:3]
  expect_lt(forest_plot(small)$result$height_in, forest_plot(bcg_spec())$result$height_in)
})

test_that("forest plots need yi and vi for at least two studies", {
  spec <- bcg_spec()
  spec$data <- lapply(spec$data, function(col) col[1])
  spec$markers <- spec$markers[1]
  expect_false(forest_plot(spec)$ok)
  spec <- bcg_spec()
  spec$format <- "pdf"
  expect_false(forest_plot(spec)$ok)
})
