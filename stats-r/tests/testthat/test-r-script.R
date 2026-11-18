# 11.1, item 5: the exported script, run in a clean R session, gives the same numbers.

fixtures <- jsonlite::read_json(file.path(app_dir, "fixtures", "meta-analysis.json"), simplifyVector = FALSE)

run_in_clean_r <- function(script) {
  dir <- tempfile("rscript-")
  dir.create(dir)
  path <- file.path(dir, "analysis.R")
  out <- file.path(dir, "out.json")
  writeLines(script, path)
  # A new R process: nothing from this session (functions, options, packages) leaks in.
  code <- sprintf(
    paste0(
      "setwd('%s'); source('%s'); p <- predict(res); ",
      "jsonlite::write_json(list(b = as.numeric(res$beta), ci_lb = res$ci.lb, ci_ub = res$ci.ub, ",
      "pval = res$pval, tau2 = res$tau2, i2 = res$I2, pi_lb = if (is.null(p$pi.lb)) NA else p$pi.lb), ",
      "'%s', digits = NA)"
    ),
    dir, path, out
  )
  status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", "-e", shQuote(code)),
                    stdout = FALSE, stderr = FALSE)
  expect_equal(status, 0)
  jsonlite::read_json(out, simplifyVector = TRUE)
}

for (name in c("dat.bcg_RR_REML_knha", "dat.normand1999_SMD_DL_z", "dat.bcg_OR_FE_z")) {
  test_that(paste("the exported script reproduces", name, "in a clean R session"), {
    case <- Filter(function(c) c$name == name, fixtures$cases)[[1]]
    req <- case$request
    spec <- list(
      measure = req$measure, method = req$method, test = req$test,
      data = list(label = req$data$label, yi = case$expected$yi, vi = case$expected$vi),
      info = list(project = "Teste \"aspas\"", outcome = "Desfecho", timepoint = "5 anos",
                  notes = list("Estudo X: SD = SE x sqrt(n)"))
    )
    out <- r_script(spec)
    expect_true(out$ok)
    script <- out$result$script
    expect_match(script, "library(metafor)", fixed = TRUE)
    got <- run_in_clean_r(script)
    e <- case$expected
    expect_equal(got$b, e$estimate, tolerance = 1e-6)
    expect_equal(got$ci_lb, e$ci_lb, tolerance = 1e-6)
    expect_equal(got$ci_ub, e$ci_ub, tolerance = 1e-6)
    expect_equal(got$pval, e$p_value, tolerance = 1e-6)
    expect_equal(got$tau2, e$tau2, tolerance = 1e-6)
    expect_equal(got$i2, e$i2, tolerance = 1e-6)
    if (req$method != "FE") expect_equal(got$pi_lb, e$pi_lb, tolerance = 1e-6)
  })
}

test_that("labels with quotes stay valid R and notes stay comments", {
  spec <- list(measure = "MD", method = "REML", test = "knha",
               data = list(label = list("O\"Brien 2020", "Silva\n2021"), yi = list(1, 2), vi = list(0.1, 0.2)),
               info = list(notes = list("linha 1\nlinha 2")))
  script <- r_script(spec)$result$script
  expect_silent(parse(text = script))
})
