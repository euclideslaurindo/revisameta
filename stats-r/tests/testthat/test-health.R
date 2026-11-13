test_that("envelope follows the Python <-> R contract", {
  body <- envelope(result = list(x = 1), warnings = "w1")
  expect_named(body, c("ok", "result", "warnings", "errors", "meta"))
  expect_true(body$ok)
  expect_equal(as.character(body$warnings), "w1")
  expect_named(body$meta, c("r_version", "packages", "robvis_commit", "params"))
})

test_that("envelope is not ok when there are errors", {
  body <- envelope(errors = "boom")
  expect_false(body$ok)
})

test_that("health reports ok and the versions of every statistical package", {
  body <- health_status()
  expect_true(body$ok)
  expect_equal(body$result$status, "ok")
  for (pkg in c("metafor", "meta", "robvis", "irr", "plumber")) {
    expect_false(is.na(body$meta$packages[[pkg]]), info = pkg)
  }
  expect_match(body$meta$r_version, "^[0-9]+\\.[0-9]+\\.[0-9]+$")
})

test_that("robvis is the pinned GitHub build, not the CRAN release", {
  expect_equal(robvis_commit(), "0c59cf1725ca3e18016d28903d4e01fd0a37bcf9")
})

test_that("health is degraded when a required package is missing", {
  body <- health_status(required = c("metafor", "pacote.inexistente"))
  expect_false(body$ok)
  expect_equal(body$result$status, "degraded")
  expect_match(body$errors[[1]], "pacote.inexistente")
})

test_that("health is serialized as the JSON the backend expects", {
  json <- jsonlite::toJSON(health_status(), auto_unbox = TRUE)
  parsed <- jsonlite::fromJSON(json, simplifyVector = FALSE)
  expect_true(parsed$ok)
  expect_type(parsed$warnings, "list")
  expect_type(parsed$meta$packages, "list")
})
