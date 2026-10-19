# Build all five volumes, or a selection such as: .\build.ps1 -Book 1,3
[CmdletBinding()]
param([ValidateRange(1, 5)][int[]]$Book = @(1, 2, 3, 4, 5))
$ErrorActionPreference = 'Stop'
try {
    foreach ($bookNumber in ($Book | Select-Object -Unique)) {
        & (Join-Path $PSScriptRoot 'scripts/Build-Book.ps1') -Book $bookNumber
    }
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
