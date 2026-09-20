# Run one CFD Agent case organized under C:\CFD-inputs\<case-name>\
# Expected layout per case:
#   C:\CFD-inputs\<case-name>\<anything>.scdoc
#   C:\CFD-inputs\<case-name>\prompt.txt
# Results go to C:\CFD-results\<case-name>\ (use -Overwrite to rerun the same case).
#
# Examples:
#   .\run-case.ps1 no-panel-b
#   .\run-case.ps1 with-panel-b -Overwrite
#   .\run-case.ps1 no-panel-b -Hidden          # background SpaceClaim, no keep-open
#   .\run-case.ps1 no-panel-b -DryRun          # print the command without running it

param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Case,
    [switch]$Overwrite,
    [switch]$Hidden,
    [switch]$DryRun
)

$caseDir = "C:\CFD-inputs\$Case"
$geo = Get-ChildItem -Path $caseDir -Filter *.scdoc -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $geo) {
    Write-Error "No .scdoc file found in $caseDir"
    exit 2
}
$promptPath = Join-Path $caseDir "prompt.txt"
if (-not (Test-Path $promptPath)) {
    Write-Error "Missing prompt file: $promptPath"
    exit 2
}

$outDir = "C:\CFD-results\$Case"
$uiMode = if ($Hidden) { "hidden" } else { "gui" }

$cliArgs = @(
    "run",
    "--geometry", $geo.FullName,
    "--prompt-file", $promptPath,
    "--output", $outDir,
    "--ui-mode", $uiMode
)
if (-not $Hidden) { $cliArgs += "--keep-open" }
if ($Overwrite) { $cliArgs += "--overwrite" }

if ($DryRun) {
    Write-Output "Case      : $Case"
    Write-Output "Geometry  : $($geo.FullName)"
    Write-Output "Prompt    : $promptPath"
    Write-Output "Output    : $outDir"
    Write-Output "UI mode   : $uiMode"
    Write-Output "Command   : cfd-agent $($cliArgs -join ' ')"
    exit 0
}

& "$PSScriptRoot\run-cfd-agent.ps1" @cliArgs
exit $LASTEXITCODE
