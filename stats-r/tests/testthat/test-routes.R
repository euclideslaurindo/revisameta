test_that("plumber.R parses: every route and serializer annotation is valid", {
  router <- plumber::pr(file.path(app_dir, "plumber.R"))
  paths <- vapply(router$endpoints[[1]], function(e) e$path, character(1))
  expected <- c(
    "/health", "/kappa", "/rob-plots", "/effect-sizes", "/meta-analysis", "/convert", "/combine-groups",
    "/forest-plot"
  )
  expect_true(all(expected %in% paths))
})

test_that("/kappa keeps full precision and writes missing numbers as null", {
  lines <- readLines(file.path(app_dir, "plumber.R"))
  expect_true(any(grepl('@serializer unboxedJSON list(digits = NA, na = "null")', lines, fixed = TRUE)))
})
