prisma_spec <- function(format = "svg") {
  list(
    format = format,
    title = "PRISMA 2020",
    phases = list("Identificação", "Triagem", "Incluídos"),
    boxes = list(
      identified = "Registros identificados:\n  PubMed (n = 120)\n  LILACS (n = 40)",
      removed = "Removidos antes da triagem:\n  Duplicatas (n = 30)",
      screened = "Registros triados\n(n = 130)",
      screened_excluded = "Registros excluídos\n(n = 100)",
      sought = "Relatos buscados para leitura\n(n = 30)",
      not_retrieved = "Relatos não obtidos\n(n = 2)",
      assessed = "Relatos avaliados quanto à elegibilidade\n(n = 28)",
      assessed_excluded = paste0("Relatos excluídos:\n", paste0("  Motivo ", 1:8, " (n = ", 1:8, ")", collapse = "\n")),
      included = "Estudos incluídos na revisão\n(n = 6)\nRelatos dos estudos incluídos\n(n = 7)"
    )
  )
}

test_that("the PRISMA flow diagram renders as SVG and PNG and grows with long boxes", {
  svg <- prisma_flow(prisma_spec("svg"))
  expect_true(svg$ok)
  expect_match(rawToChar(jsonlite::base64_dec(svg$result$file_base64)), "<svg", fixed = TRUE)
  png <- prisma_flow(prisma_spec("png"))
  expect_equal(as.integer(jsonlite::base64_dec(png$result$file_base64)[2:4]), c(0x50, 0x4E, 0x47))
  short <- prisma_spec()
  short$boxes$assessed_excluded <- "Relatos excluídos\n(n = 0)"
  expect_lt(prisma_flow(short)$result$height_in, svg$result$height_in)
})

test_that("missing boxes and bad formats are refused", {
  spec <- prisma_spec()
  spec$boxes$included <- NULL
  expect_false(prisma_flow(spec)$ok)
  spec <- prisma_spec("pdf")
  expect_false(prisma_flow(spec)$ok)
})
