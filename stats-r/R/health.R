# Health check: confirms the statistical packages load and reports their versions.

REQUIRED_PACKAGES <- c("metafor", "meta", "robvis", "irr")

health_status <- function(required = REQUIRED_PACKAGES) {
  missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
  errors <- if (length(missing) > 0) {
    paste0("Package not available: ", missing)
  } else {
    character()
  }
  envelope(
    result = list(status = if (length(missing) == 0) "ok" else "degraded"),
    errors = errors
  )
}
