[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$Book,
    [string]$ProjectRoot,
    [string]$OutlinePath
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$checkerPath = Join-Path $PSScriptRoot 'Check-Outline.py'
$checkerArguments = @($checkerPath, '--root', $ProjectRoot)
if ($PSBoundParameters.ContainsKey('Book')) {
    $checkerArguments += @('-Book', [string]$Book)
}
if ($OutlinePath) {
    $checkerArguments += @('--outline', $OutlinePath)
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    & $pythonCommand.Source -B @checkerArguments
} else {
    $launcherCommand = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcherCommand) {
        throw '需要 Python 3.10 或更高版本；本检查仅使用标准库。'
    }
    & $launcherCommand.Source -3 -B @checkerArguments
}
exit $LASTEXITCODE
