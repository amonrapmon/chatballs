param([Parameter(Mandatory=$true)][string]$Folder)
$ErrorActionPreference = 'Stop'
$payload = @{
    report = Get-Content -LiteralPath (Join-Path $Folder 'report.json') -Raw | ConvertFrom-Json
    csv = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $Folder 'report.csv')))
    xlsx = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $Folder 'report.xlsx')))
}
$pythonScript = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verify_downloads.py') -Raw
$payload | ConvertTo-Json -Depth 40 -Compress | docker compose exec -T backend-admin python -c $pythonScript
if ($LASTEXITCODE -ne 0) { throw 'Browser export verification failed' }
