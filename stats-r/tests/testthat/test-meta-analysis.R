fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "meta-analysis.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

# The JSON request, as the backend sends it (lists, not vectors).
as_request <- function(case) case$request

test_that("every metafor reference case is reproduced within 1e-6", {
  expect_gte(length(fixtures$cases), 28)
  for (case in fixtures$cases) {
    out <- meta_analysis(as_request(case))
    expect_true(out$ok, info = case$name)
    e <- case$expected
    r <- out$result
    p <- r$pooled
    h <- r$heterogeneity
    for (pair in list(
      c(p$estimate, e$estimate), c(p$se, e$se), c(p$ci_lb, e$ci_lb), c(p$ci_ub, e$ci_ub),
      c(p$statistic, e$statistic), c(p$p_value, e$p_value),
      c(p$pi_lb, e$pi_lb), c(p$pi_ub, e$pi_ub),
      c(h$tau2, e$tau2), c(h$i2, e$i2), c(h$h2, e$h2), c(h$q, e$q), c(h$q_p, e$q_p)
    )) {
      expect_equal(pair[1], pair[2], tolerance = tol, info = case$name)
    }
    expect_equal(r$k, e$k, info = case$name)
    expect_equal(vapply(r$studies, function(s) s$yi, numeric(1)), unlist(e$yi), tolerance = tol, info = case$name)
    expect_equal(vapply(r$studies, function(s) s$vi, numeric(1)), unlist(e$vi), tolerance = tol, info = case$name)
    expect_equal(vapply(r$studies, function(s) s$weight, numeric(1)), unlist(e$weights), tolerance = tol,
                 info = case$name)
  }
})

test_that("metafor warnings never escape as loose R warnings", {
  # metafor warns about large SMDs only once per R process, so the SE-as-SD detector
  # (/plausibility-checks, stage 3 step 6) does not rely on it.
  case <- Filter(function(c) c$name == "dat.normand1999_SMD_REML_knha", fixtures$cases)[[1]]
  expect_silent(meta_analysis(as_request(case)))
  run <- with_metafor_warnings({
    warning("One or more SMD values are unusually large (i.e., abs(yi) > 2).")
    1
  })
  expect_equal(run$warnings, "smd_unusually_large")
})

test_that("ratio measures are also reported back-transformed", {
  case <- Filter(function(c) c$name == "dat.bcg_RR_REML_knha", fixtures$cases)[[1]]
  out <- meta_analysis(as_request(case))
  expect_equal(out$result$pooled$exp$estimate, exp(case$expected$estimate), tolerance = tol)
  expect_equal(out$result$pooled$exp$pi_ub, exp(case$expected$pi_ub), tolerance = tol)
})

test_that("'higher is worse' inverts the sign here, and only here", {
  case <- Filter(function(c) c$name == "dat.normand1999_MD_REML_knha", fixtures$cases)[[1]]
  request <- as_request(case)
  request$higher_is_better <- FALSE
  out <- meta_analysis(request)
  expect_equal(out$result$pooled$estimate, -case$expected$estimate, tolerance = tol)
  expect_true(out$result$direction_inverted)
  expect_true("direction_inverted" %in% out$warnings)
})

test_that("each study can say its own scale direction", {
  case <- Filter(function(c) c$name == "dat.normand1999_MD_REML_knha", fixtures$cases)[[1]]
  request <- list(measure = "MD", data = case$request$data)
  k <- length(request$data$label)
  request$data$higher_is_better <- as.list(c(FALSE, rep(TRUE, k - 1)))
  out <- effect_sizes_result(request)
  yi <- vapply(out$result$studies, function(s) s$yi, numeric(1))
  expect_equal(yi[1], -case$expected$yi[[1]], tolerance = tol)
  expect_equal(yi[-1], unlist(case$expected$yi)[-1], tolerance = tol)
  expect_true(out$result$studies[[1]]$inverted)
  expect_false(out$result$studies[[2]]$inverted)
})

test_that("zero events in both groups leaves the study out of OR/RR, with a warning", {
  request <- list(
    measure = "OR", method = "REML", test = "knha",
    data = list(
      label = list("FICTITIOUS A", "FICTITIOUS B", "FICTITIOUS C"),
      ai = list(0, 4, 6), n1i = list(20, 30, 40), ci = list(0, 9, 12), n2i = list(20, 31, 38)
    )
  )
  out <- meta_analysis(request)
  expect_true(out$ok)
  expect_equal(out$result$k, 2)
  expect_false(out$result$studies[[1]]$included)
  expect_true("double_zero_excluded" %in% out$warnings)
  expect_true("few_studies_heterogeneity_unstable" %in% out$warnings)
})

test_that("k < 2 does not run, and fixed effect never uses Hartung-Knapp", {
  case <- fixtures$cases[[1]]
  request <- as_request(case)
  request$data <- lapply(request$data, function(col) col[1])
  out <- meta_analysis(request)
  expect_false(out$ok)
  request <- as_request(case)
  request$method <- "FE"
  request$test <- "knha"
  out <- meta_analysis(request)
  expect_equal(out$meta$params$test, "z")
  expect_true("knha_not_for_fixed_effect" %in% out$warnings)
})

test_that("invalid requests are refused with a clear error", {
  expect_match(meta_analysis(list(measure = "HR", data = list(label = list("x"))))$errors[[1]], "measure")
  out <- effect_sizes_result(list(measure = "MD", data = list(label = list("x"), m1i = list(1))))
  expect_false(out$ok)
})
