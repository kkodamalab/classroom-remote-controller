param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$ExpectedVersion
)
$ErrorActionPreference = 'Stop'
if (Test-Path $ReportPath) { Remove-Item $ReportPath }
$process = Start-Process -FilePath $ExePath -ArgumentList @('--diagnostics-self-test', "`"$ReportPath`"") -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'Portable diagnostic self-test timed out' }
if ($process.ExitCode -ne 0) {
  if (Test-Path $ReportPath) { Get-Content $ReportPath -Raw -Encoding utf8 | Write-Output }
  throw "Portable diagnostic self-test failed: $($process.ExitCode)"
}
$report = Get-Content $ReportPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($report.status -ne 'passed' -or -not $report.frozen -or $report.platform -ne 'win32') { throw 'Expected a passed Windows frozen-process report' }
if ($report.version -ne $ExpectedVersion -or $report.title -notlike "*v$ExpectedVersion*") { throw 'Wrong EXE version/title' }
if ($report.cases.Count -ne 5) { throw 'Missing diagnostic test cases' }
foreach ($case in $report.cases) {
  if ($case.code -ne $case.wire_code -or $case.pc_log -notlike "*$($case.code)*") { throw 'Diagnostic code mismatch' }
}
$fileVersion = (Get-Item $ExePath).VersionInfo.ProductVersion
if ($fileVersion -ne $ExpectedVersion) { throw "Wrong Windows ProductVersion: $fileVersion" }
Get-Content $ReportPath -Raw -Encoding utf8
