# CFD Agent launcher
# Sets the local HTTP proxy (needed for the Codex model endpoint) and
# the Ansys 2024 R1 root, then forwards all arguments to cfd-agent.
# Proxy port 7890 = FlClash mixed port; change it if your proxy uses another port.
#
# Examples:
#   .\run-cfd-agent.ps1 run --geometry C:\CFD-inputs\model.scdoc --prompt-file C:\CFD-inputs\prompt.txt --ui-mode gui --keep-open
#   .\run-cfd-agent.ps1 run --help
#   .\run-cfd-agent.ps1 resume --run-dir .\runs\YOUR-RUN-ID

$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:HTTP_PROXY  = "http://127.0.0.1:7890"
$env:AWP_ROOT241 = "C:\Program Files\ANSYS Inc\v241"

Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\cfd-agent.exe" @args
exit $LASTEXITCODE
