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
