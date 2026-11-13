app_dir <- normalizePath(file.path(testthat::test_path(), "..", ".."))
for (file in list.files(file.path(app_dir, "R"), pattern = "\\.R$", full.names = TRUE)) {
  source(file)
}
