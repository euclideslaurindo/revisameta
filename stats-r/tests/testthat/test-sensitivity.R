fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "leave-one-out.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("leave-one-out reproduces metafor::leave1out within 1e-6", {
  for (case in fixtures$cases) {
    out <- leave_one_out(case$request)
    expect_true(out$ok, info = case$name)
    rows <- out$result$rows
    expect_equal(length(rows), length(case$request$data$label), info = case$name)
    for (key in c("estimate", "ci_lb", "ci_ub", "p_value", "tau2")) {
      got <- vapply(rows, function(r) r[[key]], numeric(1))
      expect_equal(got, unlist(case$expected[[key]]), tolerance = tol, info = paste(case$name, key))
    }
    expect_equal(rows[[1]]$omitted, case$request$data$label[[1]])
  }
})

test_that("ratio measures are also back-transformed, and too few studies are refused", {
  case <- fixtures$cases[[1]]
  rows <- leave_one_out(case$request)$result$rows
  expect_equal(rows[[1]]$exp$estimate, exp(case$expected$estimate[[1]]), tolerance = tol)
  request <- case$request
  request$data <- lapply(request$data, function(col) col[1:2])
  expect_false(leave_one_out(request)$ok)
})
