fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "subgroup.json"), simplifyVector = FALSE)
tol <- fixtures$tolerance

test_that("subgroups and the test of differences reproduce metafor within 1e-6", {
  for (case in fixtures$cases) {
    out <- subgroup_analysis(case$request)
    expect_true(out$ok, info = case$name)
    e <- case$expected
    rows <- out$result$subgroups
    expect_equal(vapply(rows, function(r) r$group, character(1)), unlist(e$groups), info = case$name)
    for (key in c("estimate", "ci_lb", "ci_ub", "tau2")) {
      expect_equal(vapply(rows, function(r) r[[key]], numeric(1)), unlist(e[[key]]),
                   tolerance = tol, info = paste(case$name, key))
    }
    expect_equal(out$result$test$q, e$q, tolerance = tol, info = case$name)
    expect_equal(out$result$test$df, e$df, info = case$name)
    expect_equal(out$result$test$p_value, e$p_value, tolerance = tol, info = case$name)
  }
})

test_that("studies without a group are left out and listed; one subgroup is refused", {
  request <- fixtures$cases[[1]]$request
  request$data$group[[1]] <- NULL
  request$data$group <- append(request$data$group, list(NULL), 0)
  out <- subgroup_analysis(request)
  expect_true(out$ok)
  expect_equal(out$result$left_out, request$data$label[[1]])
  one <- fixtures$cases[[1]]$request
  one$data$group <- as.list(rep("x", length(one$data$label)))
  expect_false(subgroup_analysis(one)$ok)
})

test_that("a subgroup with a single study shows that study and warns", {
  request <- list(
    measure = "MD", method = "REML", test = "knha",
    data = list(label = list("A", "B", "C", "D"), yi = list(1, 2, 1.5, 4), vi = list(0.2, 0.3, 0.25, 0.4),
                group = list("x", "x", "x", "y"))
  )
  out <- subgroup_analysis(request)
  expect_true("subgroup_with_one_study" %in% out$warnings)
  y <- Filter(function(r) r$group == "y", out$result$subgroups)[[1]]
  expect_equal(y$estimate, 4)
  expect_equal(y$k, 1L)
})
