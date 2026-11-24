fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "meta-regression.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("meta-regression reproduces metafor within 1e-6", {
  for (case in fixtures$cases) {
    out <- meta_regression(case$request)
    expect_true(out$ok, info = case$name)
    e <- case$expected
    r <- out$result
    expect_equal(r$k, e$k, info = case$name)
    expect_equal(vapply(r$coefficients, function(c) c$term, character(1)), unlist(e$terms), info = case$name)
    for (key in c("estimate", "se", "ci_lb", "ci_ub", "p_value")) {
      got <- vapply(r$coefficients, function(c) c[[key]], numeric(1))
      expect_equal(got, unlist(e[[key]]), tolerance = tol, info = paste(case$name, key))
    }
    expect_equal(r$moderators$statistic, e$qm, tolerance = tol, info = case$name)
    expect_equal(r$moderators$p_value, e$qm_p, tolerance = tol, info = case$name)
    expect_equal(r$residual$tau2, e$tau2, tolerance = tol, info = case$name)
  }
})

test_that("ten studies per moderator: warning below, and no run with fewer than three", {
  one <- meta_regression(fixtures$cases[[1]]$request)  # 13 studies, 1 coefficient
  expect_false("fewer_than_ten_studies_per_moderator" %in% unlist(one$warnings))
  both <- meta_regression(fixtures$cases[[4]]$request)  # 13 studies, 3 coefficients
  expect_true("fewer_than_ten_studies_per_moderator" %in% unlist(both$warnings))
  req <- fixtures$cases[[1]]$request
  req$data$label <- req$data$label[1:2]
  req$data$yi <- req$data$yi[1:2]
  req$data$vi <- req$data$vi[1:2]
  req$data$mods$ablat <- req$data$mods$ablat[1:2]
  expect_false(meta_regression(req)$ok)
})

test_that("a study without the moderator is left out and listed", {
  req <- fixtures$cases[[1]]$request
  req$data$mods$ablat[1] <- list(NULL)
  out <- meta_regression(req)
  expect_true(out$ok)
  expect_equal(out$result$k, 12)
  expect_equal(length(out$result$left_out), 1)
})
