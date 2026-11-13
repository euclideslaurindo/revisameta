# Standard response envelope shared by every endpoint (docs/estatistica.md, 8.2):
# { ok, result, warnings, errors, meta: { r_version, packages, params } }

TRACKED_PACKAGES <- c("plumber", "metafor", "meta", "robvis", "irr", "jsonlite")

package_versions <- function(packages = TRACKED_PACKAGES) {
  versions <- lapply(packages, function(pkg) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      return(NA_character_)
    }
    as.character(utils::packageVersion(pkg))
  })
  names(versions) <- packages
  versions
}

robvis_commit <- function() {
  if (!requireNamespace("robvis", quietly = TRUE)) {
    return(NA_character_)
  }
  sha <- utils::packageDescription("robvis")$RemoteSha
  if (is.null(sha)) NA_character_ else sha
}

response_meta <- function(params = list()) {
  list(
    r_version = paste(R.version$major, R.version$minor, sep = "."),
    packages = package_versions(),
    robvis_commit = robvis_commit(),
    params = params
  )
}

envelope <- function(result = list(), warnings = character(), errors = character(), params = list()) {
  list(
    ok = length(errors) == 0,
    result = result,
    warnings = I(as.character(warnings)),
    errors = I(as.character(errors)),
    meta = response_meta(params)
  )
}
