fixture_path <- file.path(app_dir, "fixtures", "kappa.json")
fixtures <- jsonlite::fromJSON(fixture_path, simplifyVector = FALSE)

for (case in fixtures$cases) {
  test_that(paste("kappa matches the irr reference:", case$name), {
    body <- kappa_agreement(unlist(case$rater_a), unlist(case$rater_b))
    expect_true(body$ok)
    for (field in names(case$expected)) {
      expect_equal(body$result[[field]], case$expected[[field]], tolerance = 1e-6, info = field)
    }
  })
}

test_that("identical single code: agreement is 100% and kappa is not defined", {
  body <- kappa_agreement(c("sd", "sd", "sd"), c("sd", "sd", "sd"))
  expect_true(body$ok)
  expect_equal(body$result$agreement_percent, 100)
  expect_true(is.na(body$result$kappa))
  expect_equal(as.character(body$warnings), "kappa_undefined_single_code")
})

test_that("one item: percentage only, with a warning", {
  body <- kappa_agreement("sd", "se")
  expect_true(body$ok)
  expect_equal(body$result$agreement_percent, 0)
  expect_true(is.na(body$result$kappa))
  expect_true(is.na(body$result$z))
  expect_equal(as.character(body$warnings), "kappa_needs_two_items")
})

test_that("invalid input is rejected with a clear error", {
  expect_false(kappa_agreement(c("a", "b"), "a")$ok)
  expect_false(kappa_agreement(character(), character())$ok)
  expect_false(kappa_agreement(c("a", NA), c("a", "b"))$ok)
})

test_that("kappa is serialized with full precision", {
  case <- fixtures$cases[[1]]
  body <- kappa_agreement(unlist(case$rater_a), unlist(case$rater_b))
  json <- jsonlite::toJSON(body, auto_unbox = TRUE, digits = NA, null = "null")
  parsed <- jsonlite::fromJSON(json, simplifyVector = FALSE)
  expect_equal(parsed$result$kappa, case$expected$kappa, tolerance = 1e-12)
})

test_that("missing numbers are serialized as JSON null by the /kappa serializer", {
  # Same serializer and arguments as the @serializer annotation of the /kappa route.
  serialize <- plumber::serializer_unboxed_json(digits = NA, na = "null")
  res <- plumber:::PlumberResponse$new()
  out <- serialize(kappa_agreement("sd", "se"), list(), res, stop)
  parsed <- jsonlite::fromJSON(out$body, simplifyVector = FALSE)
  expect_null(parsed$result$kappa)
  expect_null(parsed$result$z)
  expect_equal(parsed$result$agreement_percent, 0)
  expect_equal(parsed$warnings[[1]], "kappa_needs_two_items")
})
