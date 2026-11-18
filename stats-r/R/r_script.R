# Reproducible R script of a saved analysis (docs/modulos.md 7.7 "Exportar script R").
#
# The script holds the effect of each study on the analysis scale (yi, vi), written
# with 17 significant digits so it reproduces the result exactly, and the same rma()
# call the service made. Conversions and sign inversions already applied to each study
# are listed in comments, so the reader knows where every number came from.

r_number <- function(x) {
  ifelse(is.na(x), "NA", sprintf("%.17g", x))
}

r_comment <- function(text) {
  paste0("# ", gsub("[\r\n]+", " ", as.character(text)))
}

r_script <- function(spec) {
  errors <- meta_input_errors(spec)
  if (!all(c("yi", "vi") %in% names(spec$data))) errors <- c(errors, "the script takes yi and vi per study")
  params <- list(measure = spec$measure, method = spec$method, test = spec$test)
  if (length(errors) > 0) {
    return(envelope(errors = errors, params = params))
  }
  method <- if (is.null(spec$method)) "REML" else spec$method
  test <- if (is.null(spec$test) || method == "FE") "z" else spec$test
  labels <- vapply(spec$data$label, as.character, character(1))
  yi <- num(spec$data$yi)
  vi <- num(spec$data$vi)
  info <- if (is.null(spec$info)) list() else spec$info
  field <- function(name) if (is.null(info[[name]])) "" else as.character(info[[name]])
  ratio <- spec$measure %in% RATIO

  header <- c(
    "# RevisaMeta: script reprodutivel da meta-analise / reproducible meta-analysis script",
    r_comment(paste("Projeto / project:", field("project"))),
    r_comment(paste("Desfecho / outcome:", field("outcome"), "|", field("timepoint"))),
    r_comment(paste("Grupo 1:", field("group1"), "| grupo 2:", field("group2"))),
    r_comment(paste("Medida / measure:", spec$measure, "| modelo / model:", method, "| teste / test:", test)),
    r_comment(paste("Conjunto de dados / data set:", field("data_set"))),
    r_comment(paste("Analise / analysis:", field("analysis_id"), "| salva em / saved at:", field("saved_at"))),
    r_comment(paste("Calculada com R", field("r_version"), "e metafor", field("metafor_version"))),
    "#",
    "# yi e vi: efeito de cada estudo na escala da analise (log para OR/RR), ja com as",
    "# conversoes e a direcao abaixo / effect of each study on the analysis scale (log for",
    "# OR/RR), with the conversions and direction listed below.",
    if (length(info$notes) > 0) {
      c("#", "# Notas por estudo / notes per study:", vapply(info$notes, r_comment, character(1)))
    },
    ""
  )
  data_block <- c(
    "library(metafor)",
    "",
    "dat <- data.frame(",
    paste0("  study = c(", paste(vapply(labels, encodeString, character(1), quote = "\""), collapse = ", "), "),"),
    paste0("  yi = c(", paste(r_number(yi), collapse = ", "), "),"),
    paste0("  vi = c(", paste(r_number(vi), collapse = ", "), ")"),
    ")",
    ""
  )
  model <- sprintf(
    'res <- rma(yi, vi, data = dat, slab = study, method = "%s", test = "%s", level = 95)',
    if (method == "FE") "EE" else method, test
  )
  outputs <- c(
    model,
    "print(res)",
    "# Efeito combinado e intervalo de predicao / pooled effect and prediction interval",
    if (ratio) "predict(res, transf = exp)" else "predict(res)",
    if (ratio) {
      "forest(res, addpred = TRUE, atransf = exp, showweights = TRUE)"
    } else {
      "forest(res, addpred = TRUE, showweights = TRUE)"
    }
  )
  script <- paste(c(header, data_block, outputs, ""), collapse = "\n")
  envelope(result = list(script = script), params = params)
}
