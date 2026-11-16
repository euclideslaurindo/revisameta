# Generates fixtures/conversions.json, the expected values for /convert and
# /combine-groups. Run inside the stats-r container (scripts/generate-fixtures.sh).
#
# Values are never typed by hand (docs/validacao.md, 11.1):
# - SE -> SD, CI -> SD and the combination of groups: FICTITIOUS individual data are
#   simulated here, and the expected values are the mean and SD computed from those
#   raw data with mean() and sd(). The service formulas must recover them exactly.
# - Median -> mean/SD, effect + CI -> log scale, t or p -> SMD: metafor functions called
#   directly here (conv.fivenum, conv.wald, escalc), not through the service.

set.seed(20261116)
fictitious <- function(n, mean, sd) round(stats::rnorm(n, mean, sd), 1)

# FICTITIOUS groups (simulated scores)
g1 <- fictitious(23, 92, 14)
g2 <- fictitious(31, 85, 11)
g3 <- fictitious(17, 79, 16)

se_of <- function(x) sd(x) / sqrt(length(x))
ci_of <- function(x) {
  t <- stats::qt(0.975, df = length(x) - 1)
  c(mean(x) - t * se_of(x), mean(x) + t * se_of(x))
}

conversions <- list(
  list(
    name = "se_to_sd_fictitious",
    request = list(kind = "se_to_sd", se = se_of(g1), n = length(g1)),
    expected = list(sd = sd(g1))
  ),
  list(
    name = "ci_to_sd_fictitious",
    request = list(kind = "ci_to_sd", ci_lb = ci_of(g2)[1], ci_ub = ci_of(g2)[2], n = length(g2)),
    expected = list(sd = sd(g2))
  )
)

five <- list(min = 61, q1 = 78, median = 86, q3 = 95, max = 121, n = 40) # FICTITIOUS
ref <- metafor::conv.fivenum(min = five$min, q1 = five$q1, median = five$median, q3 = five$q3,
                             max = five$max, n = five$n, method = "luo/wan")
conversions[[length(conversions) + 1]] <- list(
  name = "median_iqr_range_fictitious",
  request = c(list(kind = "median_to_mean_sd"), five),
  expected = list(mean = ref$mean[1], sd = ref$sd[1])
)
ref <- metafor::conv.fivenum(min = NA, q1 = five$q1, median = five$median, q3 = five$q3, max = NA,
                             n = five$n, method = "luo/wan")
conversions[[length(conversions) + 1]] <- list(
  name = "median_iqr_only_fictitious",
  request = list(kind = "median_to_mean_sd", q1 = five$q1, median = five$median, q3 = five$q3, n = five$n),
  expected = list(mean = ref$mean[1], sd = ref$sd[1])
)
ref <- metafor::conv.fivenum(min = five$min, q1 = NA, median = five$median, q3 = NA, max = five$max,
                             n = five$n, method = "luo/wan")
conversions[[length(conversions) + 1]] <- list(
  name = "median_range_only_fictitious",
  request = list(kind = "median_to_mean_sd", min = five$min, median = five$median, max = five$max, n = five$n),
  expected = list(mean = ref$mean[1], sd = ref$sd[1])
)

wald <- metafor::conv.wald(out = 1.84, ci.lb = 1.21, ci.ub = 2.79, transf = log) # FICTITIOUS adjusted OR
conversions[[length(conversions) + 1]] <- list(
  name = "adjusted_or_ci_fictitious",
  request = list(kind = "effect_ci_to_log", estimate = 1.84, ci_lb = 1.21, ci_ub = 2.79),
  expected = list(yi = as.numeric(wald$yi[1]), vi = as.numeric(wald$vi[1]))
)

t_es <- metafor::escalc("SMD", ti = -2.37, n1i = 26, n2i = 29) # FICTITIOUS, favours group 2
conversions[[length(conversions) + 1]] <- list(
  name = "t_to_smd_fictitious",
  request = list(kind = "t_to_smd", t = 2.37, n1 = 26, n2 = 29, favours = "group2"),
  expected = list(yi = as.numeric(t_es$yi[1]), vi = as.numeric(t_es$vi[1]))
)
p_es <- metafor::escalc("SMD", pi = 0.013, n1i = 26, n2i = 29) # FICTITIOUS, favours group 1
conversions[[length(conversions) + 1]] <- list(
  name = "p_to_smd_fictitious",
  request = list(kind = "p_to_smd", p = 0.013, n1 = 26, n2 = 29, favours = "group1"),
  expected = list(yi = as.numeric(p_es$yi[1]), vi = as.numeric(p_es$vi[1]))
)

all_raw <- c(g1, g2, g3)
combine <- list(
  list(
    name = "combine_three_arms_fictitious",
    request = list(type = "continuous", groups = list(
      list(n = length(g1), mean = mean(g1), sd = sd(g1)),
      list(n = length(g2), mean = mean(g2), sd = sd(g2)),
      list(n = length(g3), mean = mean(g3), sd = sd(g3))
    )),
    expected = list(n = length(all_raw), mean = mean(all_raw), sd = sd(all_raw))
  ),
  list(
    name = "combine_dichotomous_fictitious",
    request = list(type = "dichotomous", groups = list(
      list(events = 7, total = 31), list(events = 4, total = 28)
    )),
    expected = list(events = 11, total = 59)
  )
)

out <- list(
  generated_by = "fixtures/scripts/generate-conversions.R",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  metafor_version = as.character(utils::packageVersion("metafor")),
  tolerance = 1e-6,
  conversions = conversions,
  combine = combine
)
jsonlite::write_json(out, "fixtures/conversions.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("Wrote fixtures/conversions.json\n")
