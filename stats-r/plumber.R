# Routing and validation only. Statistics live in pure functions under R/.

#* Log every request as a JSON line, propagating the caller's request id.
#* @filter request_log
function(req, res) {
  request_id <- req$HTTP_X_REQUEST_ID
  if (is.null(request_id) || !nzchar(request_id)) {
    request_id <- paste(sample(c(letters, 0:9), 16, replace = TRUE), collapse = "")
  }
  res$setHeader("X-Request-ID", request_id)
  cat(
    jsonlite::toJSON(
      list(
        ts = format(Sys.time(), "%Y-%m-%dT%H:%M:%OS3Z", tz = "UTC"),
        level = "info",
        service = "stats-r",
        request_id = request_id,
        method = req$REQUEST_METHOD,
        path = req$PATH_INFO
      ),
      auto_unbox = TRUE
    ),
    "\n",
    sep = ""
  )
  plumber::forward()
}

#* Service status and versions of R and statistical packages.
#* @get /health
#* @serializer unboxedJSON
function(res) {
  body <- health_status()
  if (!isTRUE(body$ok)) {
    res$status <- 503
  }
  body
}

#* Agreement between two raters: % of equal codes and Cohen's kappa.
#* Body: { "rater_a": [...], "rater_b": [...] } with one code per item.
#* @post /kappa
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  body <- req$body
  if (is.null(body$rater_a) || is.null(body$rater_b)) {
    res$status <- 422
    return(envelope(errors = "rater_a and rater_b are required"))
  }
  out <- kappa_agreement(unlist(body$rater_a), unlist(body$rater_b))
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}

#* Risk-of-bias traffic light or summary plot (robvis, or ggplot2 with the same look).
#* Body: { kind, format, overall, columns: [{key, short, name}], levels: [{key, label}],
#*        studies: [{label, values: {column: level}, overall}], texts: {...} }
#* @post /rob-plots
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  spec <- tryCatch(
    jsonlite::fromJSON(req$postBody, simplifyVector = FALSE),
    error = function(e) NULL
  )
  if (is.null(spec)) {
    res$status <- 422
    return(envelope(errors = "body must be JSON"))
  }
  out <- rob_plot(spec)
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}

#* Effect and variance of each study (metafor::escalc), on the analysis scale.
#* Body: { measure, data: {label, m1i... | ai, n1i, ci, n2i | yi, vi}, higher_is_better }
#* @post /effect-sizes
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  spec <- tryCatch(jsonlite::fromJSON(req$postBody, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(spec)) {
    res$status <- 422
    return(envelope(errors = "body must be JSON"))
  }
  out <- effect_sizes_result(spec)
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}

#* Meta-analysis (metafor::rma + predict): pooled effect, heterogeneity, prediction interval.
#* Body: { measure, method: REML|DL|PM|FE, test: knha|z, data, higher_is_better }
#* @post /meta-analysis
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  spec <- tryCatch(jsonlite::fromJSON(req$postBody, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(spec)) {
    res$status <- 422
    return(envelope(errors = "body must be JSON"))
  }
  out <- meta_analysis(spec)
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}

#* Data conversions (8.5): SE or CI to SD, median to mean/SD, ratio effect + CI to the
#* log scale, t or p to SMD. Each item says the method and whether it is estimated.
#* Body: { conversions: [{ kind, ... }] }
#* @post /convert
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  spec <- tryCatch(jsonlite::fromJSON(req$postBody, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(spec)) {
    res$status <- 422
    return(envelope(errors = "body must be JSON"))
  }
  out <- convert(spec)
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}

#* Several arms into one group (Cochrane Handbook formula).
#* Body: { type: continuous|dichotomous, groups: [{n, mean, sd} | {events, total}] }
#* @post /combine-groups
#* @serializer unboxedJSON list(digits = NA, na = "null")
function(req, res) {
  spec <- tryCatch(jsonlite::fromJSON(req$postBody, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(spec)) {
    res$status <- 422
    return(envelope(errors = "body must be JSON"))
  }
  out <- combine_groups(spec)
  if (!isTRUE(out$ok)) {
    res$status <- 422
  }
  out
}
