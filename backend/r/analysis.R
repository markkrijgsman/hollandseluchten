# Applies the validated Analyse-Together functions to hourly PM2.5 rows.
# stdin : JSON {analyse_together_dir, cutoff, rows:[{station, parameter, value, date}]}
#         reference rows use parameter "pm25", sensor rows "pm25_kal"
# stdout: JSON {rows:[... , sd], removed_outliers, functions}
suppressPackageStartupMessages({
  library(dplyr)
  library(jsonlite)
})

input <- fromJSON(file("stdin"), simplifyDataFrame = TRUE)
source(file.path(input$analyse_together_dir, "funs", "data_to_tool_fun.R"))

df <- as.data.frame(input$rows, stringsAsFactors = FALSE)
if (nrow(df) == 0) {
  cat(toJSON(list(rows = list(), removed_outliers = 0L, functions = character(0)), auto_unbox = TRUE))
  quit(status = 0)
}

# 1. reference stations: the raw value counts as calibrated value
df <- add_ref_kal(df) %>% dplyr::filter(parameter == "pm25_kal")

# 2. outlier cut-off, same rule as the tool (communication_module.R): value < cutoff
n_before <- nrow(df)
df <- df %>% dplyr::filter(value < input$cutoff)
removed <- n_before - nrow(df)

# 3. sensors: 20% of the value, minimum 5.3 ug/m3; reference stations get 0
df <- add_uncertainty_sensor_percent(df, uc_pm25 = 20, uc_min_pm25 = 5.3)

cat(toJSON(list(
  rows = df,
  removed_outliers = removed,
  functions = c("add_ref_kal", "outlier cut-off (value < cutoff)", "add_uncertainty_sensor_percent")
), auto_unbox = TRUE, digits = NA, na = "null"))
