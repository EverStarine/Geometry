param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$buildExitCode = 0
try {
    & (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/Build-Book.ps1') -Book 5
} catch {
    Write-Error -ErrorAction Continue $_
    $buildExitCode = 1
}
if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
exit $buildExitCode
