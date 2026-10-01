# Real Compose environment for a task; no seed users or substitute API.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]*$')]
    [string] $Name,
    [Parameter(Mandatory)]
    [ValidateRange(1024, 65000)]
    [int] $PortBase,
    [Parameter(Mandatory)]
    [string] $DataDir,
    # This is a new real installation, never recovery of a missing database.
    [switch] $InitializeDatabase
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not [IO.Path]::IsPathFullyQualified($DataDir)) {
    throw 'DataDir must be an absolute persistent path outside the checkout.'
}
$runtimeRoot = [IO.Path]::GetFullPath($DataDir).TrimEnd('\', '/')
$worktrees = @(& git -C $projectRoot worktree list --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect worktrees; no services started.' }
foreach ($line in $worktrees) {
    if (-not $line.StartsWith('worktree ')) { continue }
    $checkout = [IO.Path]::GetFullPath($line.Substring(9)).TrimEnd('\', '/')
    if ($runtimeRoot.Equals($checkout, [StringComparison]::OrdinalIgnoreCase) -or
        $runtimeRoot.StartsWith($checkout + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "DataDir is inside a worktree: $checkout. No services started."
    }
}
# Reject junctions/symlinks in the chosen path, so lexical containment cannot hide a worktree.
$ancestor = $runtimeRoot
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "DataDir has a junction/symlink ancestor: $ancestor. Use its real path."
        }
    }
    $ancestor = [IO.Path]::GetDirectoryName($ancestor)
}
$databaseMarker = Join-Path $runtimeRoot 'postgres/PG_VERSION'
$hasDatabase = Test-Path -LiteralPath $databaseMarker -PathType Leaf
if (-not $hasDatabase -and -not $InitializeDatabase) {
    throw 'Existing PostgreSQL data was not found. Restore data and original secret volumes first; initialization requires an explicit -InitializeDatabase.'
}
if (-not $hasDatabase -and (Test-Path -LiteralPath $runtimeRoot) -and
    @(Get-ChildItem -LiteralPath $runtimeRoot -Force).Count -gt 0) {
    throw 'DataDir is nonempty without PG_VERSION. Refusing to initialize over partial runtime data.'
}
$composeProject = $Name
$compose = @('compose', '-p', $composeProject, '--project-directory', $projectRoot,
    '-f', (Join-Path $projectRoot 'compose.yaml'), '-f', (Join-Path $projectRoot 'compose.dev.yaml'))
# A relocated database must keep the original project name and all original secrets.
if ($hasDatabase) {
    foreach ($suffix in @('chatballs-secrets', 'chatballs-secrets-platform', 'chatballs-secrets-schema')) {
        & docker volume inspect "${composeProject}_$suffix" --format '{{.Name}}' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Original secret volume is missing: ${composeProject}_$suffix" }
    }
}
$values = @{
    CHATBALLS_DEV_DATA_DIR = $runtimeRoot.Replace('\', '/')
    POSTGRES_HOST_PORT = [string]$PortBase
    REDIS_HOST_PORT = [string]($PortBase + 1)
    BACKEND_APP_PORT = [string]($PortBase + 2)
    BACKEND_PLATFORM_PORT = [string]($PortBase + 3)
    INTERNAL_UI_PORT = [string]($PortBase + 4)
    WEB_CHAT_PORT = [string]($PortBase + 5)
}
$previous = @{}
try {
    foreach ($key in $values.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process')
    }
    & docker @compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed.' }
    & docker @compose up -d --build --wait postgres redis backend-app backend-platform frontend web-chat worker worker-events
    if ($LASTEXITCODE -ne 0) { throw 'The real environment did not become healthy. Inspect Compose logs; data was not removed.' }
    $frontend = "http://localhost:$($PortBase + 4)"
    $response = $null
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try {
            $response = Invoke-RestMethod "$frontend/api/v1/health/ready/" -TimeoutSec 5
            break
        } catch {
            if ($attempt -eq 9) { throw }
            Start-Sleep -Seconds 2
        }
    }
    if ($response.status -ne 'ok' -or -not $response.checks.database -or -not $response.checks.redis) {
        throw 'Frontend API proxy readiness failed.'
    }
    Write-Output "Environment: $composeProject; data: $runtimeRoot; frontend: $frontend; API: http://localhost:$($PortBase + 2)"
} finally {
    foreach ($key in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
}
