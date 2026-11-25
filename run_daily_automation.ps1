# Automated local ETL + SQL analytics runner for Windows Task Scheduler
$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\data analysis projects\zomato-analytics-2.0"
$VenvPython  = "D:\data analysis projects\.venv\Scripts\python.exe"

Set-Location $ProjectRoot
$env:PYTHONPATH = "."

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment python not found at: $VenvPython"
}

& $VenvPython run_pipeline.py --mode incremental --batch-size 5000
& $VenvPython run_phase5.py
