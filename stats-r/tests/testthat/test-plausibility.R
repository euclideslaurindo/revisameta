# Synthetic cases (docs/validacao.md 11.2): FICTITIOUS numbers, built so that the
# expected answer follows from the rule itself (an SE typed in place of an SD).

group <- function(study, sd, n = 40, scale = "QI", arm = "g1") {
  list(study_id = study, arm = arm, scale = scale, n = n, sd = sd)
}

test_that("an SE typed in place of the SD is caught", {
  # Four studies of the same scale with SD around 15; study D typed SE = 15 / sqrt(40).
  groups <- list(group("A", 15), group("B", 14), group("C", 16), group("D", 15 / sqrt(40)))
  out <- plausibility_checks(list(groups = groups))
  alerts <- out$result$alerts
  expect_length(alerts, 1)
  expect_equal(alerts[[1]]$study_id, "D")
  expect_equal(alerts[[1]]$code, "possible_se_as_sd")
  expect_equal(alerts[[1]]$values$typical_sd, 15)
})

test_that("a small SD that is not an SE, other scales and too few studies are left alone", {
  # D has a small SD, but SD x sqrt(n) is far from the typical SD: not an SE.
  groups <- list(group("A", 15), group("B", 14), group("C", 16), group("D", 6, n = 40))
  expect_length(plausibility_checks(list(groups = groups))$result$alerts, 0)
  # Different scales are never compared with each other.
  groups <- list(group("A", 15), group("B", 14), group("C", 16), group("D", 15 / sqrt(40), scale = "Bayley"))
  expect_length(plausibility_checks(list(groups = groups))$result$alerts, 0)
  # With only two studies there is no "typical" SD.
  groups <- list(group("A", 15), group("D", 15 / sqrt(40)))
  expect_length(plausibility_checks(list(groups = groups))$result$alerts, 0)
})

test_that("thresholds come from the project", {
  groups <- list(group("A", 15), group("B", 14), group("C", 16), group("D", 15 / sqrt(40)))
  out <- plausibility_checks(list(groups = groups, params = list(sd_ratio = 0.1)))
  expect_length(out$result$alerts, 0)
  expect_equal(out$meta$params$sd_ratio, 0.1)
})

test_that("a reported p value that does not match the data is flagged", {
  comparison <- function(p) {
    list(study_id = "E", n1 = 30, m1 = 92, sd1 = 12, n2 = 30, m2 = 85, sd2 = 12, p_reported = p)
  }
  # Recomputed here with the same formula the rule describes (pooled-variance t test).
  sp <- 12
  t <- (92 - 85) / (sp * sqrt(1 / 30 + 1 / 30))
  p <- 2 * stats::pt(-abs(t), 58)
  expect_length(plausibility_checks(list(comparisons = list(comparison(p))))$result$alerts, 0)
  out <- plausibility_checks(list(comparisons = list(comparison(0.4))))
  expect_equal(out$result$alerts[[1]]$code, "p_inconsistent")
  expect_equal(out$result$alerts[[1]]$values$p_recomputed, p, tolerance = 1e-12)
})

fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "meta-analysis.json"), simplifyVector = FALSE)

test_that("influential studies follow metafor's own criteria", {
  case <- Filter(function(c) c$name == "dat.bcg_RR_REML_knha", fixtures$cases)[[1]]
  spec <- list(measure = "RR", method = "REML", test = "knha",
               data = list(label = case$request$data$label, yi = case$expected$yi, vi = case$expected$vi))
  out <- influence_checks(spec)
  expect_true(out$ok)
  fit <- metafor::rma(yi = unlist(case$expected$yi), vi = unlist(case$expected$vi),
                      method = "REML", test = "knha")
  expected <- stats::influence(fit)$is.infl
  got <- vapply(out$result$studies, function(s) s$influential, logical(1))
  expect_equal(got, unname(expected))
})

test_that("improbable effects are flagged with the project limits", {
  spec <- list(
    measure = "SMD", method = "REML", test = "knha",
    data = list(label = list("A", "B", "C", "D"), yi = list(0.3, 0.5, 0.4, 2.6), vi = list(0.04, 0.05, 0.04, 0.06))
  )
  flags <- vapply(influence_checks(spec)$result$studies, function(s) s$improbable, logical(1))
  expect_equal(flags, c(FALSE, FALSE, FALSE, TRUE))
  spec$params <- list(smd_limit = 3)
  flags <- vapply(influence_checks(spec)$result$studies, function(s) s$improbable, logical(1))
  expect_false(any(flags))
  spec$data <- lapply(spec$data, function(col) col[1:2])
  expect_true("influence_needs_three_studies" %in% influence_checks(spec)$warnings)
})
