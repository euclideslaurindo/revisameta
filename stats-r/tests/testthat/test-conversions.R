fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "conversions.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("every conversion recovers the reference value within 1e-6", {
  out <- convert(list(conversions = lapply(fixtures$conversions, function(c) c$request)))
  expect_true(out$ok)
  for (i in seq_along(fixtures$conversions)) {
    case <- fixtures$conversions[[i]]
    got <- out$result$conversions[[i]]
    expect_true(got$ok, info = case$name)
    for (key in names(case$expected)) {
      expect_equal(got$output[[key]], case$expected[[key]], tolerance = tol, info = paste(case$name, key))
    }
    expect_true(nzchar(got$method), info = case$name)
  }
})

test_that("estimated and derived values are marked as such", {
  out <- convert(list(conversions = lapply(fixtures$conversions, function(c) c$request)))
  status <- vapply(out$result$conversions, function(c) c$status, character(1))
  kinds <- vapply(out$result$conversions, function(c) c$kind, character(1))
  expect_true(all(status[kinds == "median_to_mean_sd"] == "estimated"))
  expect_true(all(status[kinds %in% c("t_to_smd", "p_to_smd")] == "derived"))
  expect_true(all(status[kinds %in% c("se_to_sd", "ci_to_sd")] == "converted"))
})

test_that("combining arms gives the mean and SD of all participants together", {
  for (case in fixtures$combine) {
    out <- combine_groups(case$request)
    expect_true(out$ok, info = case$name)
    for (key in names(case$expected)) {
      expect_equal(out$result[[key]], case$expected[[key]], tolerance = tol, info = paste(case$name, key))
    }
  }
})

test_that("impossible inputs are refused item by item, never guessed", {
  out <- convert(list(conversions = list(
    list(kind = "se_to_sd", se = -1, n = 20),
    list(kind = "ci_to_sd", ci_lb = 10, ci_ub = 5, n = 20),
    list(kind = "effect_ci_to_log", estimate = 3, ci_lb = 1.2, ci_ub = 2.7),
    list(kind = "t_to_smd", t = 2, n1 = 10, n2 = 10),
    list(kind = "median_to_mean_sd", median = 5, n = 10),
    list(kind = "something_else")
  )))
  expect_true(out$ok)
  expect_false(any(vapply(out$result$conversions, function(c) c$ok, logical(1))))
  expect_false(combine_groups(list(groups = list(list(n = 3, mean = 1, sd = 1))))$ok)
  expect_false(combine_groups(list(type = "dichotomous", groups = list(
    list(events = 9, total = 5), list(events = 1, total = 5)
  )))$ok)
})
