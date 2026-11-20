fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "egger.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("Egger's test reproduces metafor::regtest within 1e-6", {
  for (case in fixtures$cases) {
    out <- egger_test(case$request)
    expect_true(out$ok, info = case$name)
    for (key in c("statistic", "p_value", "limit_estimate")) {
      expect_equal(out$result[[key]], case$expected[[key]], tolerance = tol, info = paste(case$name, key))
    }
    expect_equal(out$result$k, case$expected$k)
    expect_equal("fewer_than_ten_studies" %in% out$warnings, isTRUE(case$expected$few_studies), info = case$name)
  }
})

test_that("Egger needs three studies and the funnel plot renders", {
  case <- fixtures$cases[[1]]
  request <- case$request
  request$data <- lapply(request$data, function(col) col[1:2])
  expect_false(egger_test(request)$ok)
  spec <- c(case$request, list(format = "svg", texts = list(effect = "RR", se = "Erro-padrão"), decimal_mark = ","))
  out <- funnel_plot(spec)
  expect_true(out$ok)
  expect_match(rawToChar(jsonlite::base64_dec(out$result$file_base64)), "<svg", fixed = TRUE)
  spec$format <- "pdf"
  expect_false(funnel_plot(spec)$ok)
})
