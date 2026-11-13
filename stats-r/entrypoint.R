for (file in list.files("R", pattern = "\\.R$", full.names = TRUE)) {
  source(file)
}

port <- as.integer(Sys.getenv("PORT", "8000"))
router <- plumber::pr("plumber.R")
plumber::pr_run(router, host = "0.0.0.0", port = port, docs = FALSE)
