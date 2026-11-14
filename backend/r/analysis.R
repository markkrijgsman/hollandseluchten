# Applies the validated Analyse-Together functions to hourly PM2.5 rows.
# stdin : JSON {analyse_together_dir, cutoff, rows:{station:[], parameter:[], value:[], date:[]}}  (columns, not records)
#         reference rows use parameter "pm25", sensor rows "pm25_kal"
# stdout: JSON {rows:{station:[], ..., sd:[]}, removed_outliers, functions, parameters}
suppressPackageStartupMessages({
  library(dplyr)
  library(jsonlite)
})

input <- fromJSON(file("stdin"), simplifyDataFrame = TRUE)
source(file.path(input$analyse_together_dir, "funs", "data_to_tool_fun.R"))

df <- as.data.frame(input$rows, stringsAsFactors = FALSE)
if (nrow(df) == 0) {
  cat(toJSON(list(rows = setNames(list(), character(0)), removed_outliers = 0L, functions = character(0), parameters = list()), auto_unbox = TRUE))
  quit(status = 0)
}

called <- character(0)
step <- function(name, value) {  # records every function that was actually applied
  called <<- c(called, name)
  value
}

# 1. reference stations: the raw value counts as calibrated value
df <- step("add_ref_kal", add_ref_kal(df)) %>% dplyr::filter(parameter == "pm25_kal")

# 2. outlier cut-off, same rule as the tool (communication_module.R): value < cutoff
n_before <- nrow(df)
df <- step("outlier cut-off (value < cutoff)", df %>% dplyr::filter(value < input$cutoff))
removed <- n_before - nrow(df)

# 3. sensor uncertainty: percentage of the value with a minimum, using the package defaults.
#    Reference stations get 0. The defaults are read back from the function so the audit
#    reports what R really used.
df <- step("add_uncertainty_sensor_percent", add_uncertainty_sensor_percent(df))
defaults <- formals(add_uncertainty_sensor_percent)

cat(toJSON(list(
  rows = df,
  removed_outliers = removed,
  functions = called,
  parameters = list(
    outlier_cutoff = input$cutoff,
    sensor_uncertainty_percent = eval(defaults$uc_pm25),
    sensor_uncertainty_min_ug_m3 = eval(defaults$uc_min_pm25)
  )
), auto_unbox = TRUE, digits = NA, na = "null", dataframe = "columns"))
