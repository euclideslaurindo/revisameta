fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "multilevel.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("the multilevel model reproduces metafor::rma.mv within 1e-6", {
  for (case in fixtures$cases) {
    out <- multilevel_analysis(case$request)
    expect_true(out$ok, info = case$name)
    e <- case$expected
    r <- out$result
    expect_equal(r$k, e$k, info = case$name)
    expect_equal(r$studies, e$studies, info = case$name)
    for (key in c("estimate", "se", "ci_lb", "ci_ub", "p_value", "pi_lb", "pi_ub")) {
      expect_equal(r$pooled[[key]], e[[key]], tolerance = tol, info = paste(case$name, key))
    }
    expect_equal(c(r$variance$between_studies, r$variance$within_studies), unlist(e$sigma2),
                 tolerance = tol, info = case$name)
    expect_equal(r$heterogeneity$q, e$q, tolerance = tol, info = case$name)
  }
})

test_that("needs a study per effect and at least two studies; warns below five", {
  req <- fixtures$cases[[1]]$request
  bad <- req
  bad$data$study <- NULL
  expect_false(multilevel_analysis(bad)$ok)
  few <- req
  keep <- which(unlist(req$data$study) %in% c("11", "12", "18"))
  few$data <- lapply(req$data, function(v) v[keep])
  out <- multilevel_analysis(few)
  expect_true(out$ok)
  expect_true("fewer_than_five_studies" %in% unlist(out$warnings))
  one <- req
  keep1 <- which(unlist(req$data$study) == "11")
  one$data <- lapply(req$data, function(v) v[keep1])
  expect_false(multilevel_analysis(one)$ok)
})
