# Shared full build; invoked by build.ps1 and the per-volume entry points.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$Book)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$bookName = "Book$Book"
$bookDir = Join-Path $projectRoot $bookName
$buildDir = Join-Path $projectRoot "tmp/build/$bookName"
$relativeOutput = "../tmp/build/$bookName"
$indexStyle = Join-Path $projectRoot 'Shared/geometry.ist'
$logFile = Join-Path $buildDir "$bookName.log"
$started = Get-Date

# Reuse the existing TeX Live installation if this shell lacks its PATH entry.
$previousPath = $env:PATH
$knownTexBin = 'D:\texstudio\texlive\2025\bin\windows'
if (-not (Get-Command xelatex -ErrorAction SilentlyContinue) -and
    (Test-Path -LiteralPath (Join-Path $knownTexBin 'xelatex.exe'))) {
    $env:PATH = "$knownTexBin;$env:PATH"
}

function Invoke-BuildStep {
    param([string]$Executable, [string[]]$Arguments, [string]$StepName)
    Write-Host "[$bookName] $StepName"
    $stepLog = Join-Path $buildDir "$StepName.console.log"
    $savedPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 wraps redirected native stderr in error records.
        # Judge the native process by its exit code; retain both streams in the log.
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments *> $stepLog
        $nativeExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($nativeExitCode -ne 0) {
        Get-Content -LiteralPath $stepLog -Tail 20 | Write-Host
        throw "$StepName failed. See $stepLog"
    }
}

try {
    foreach ($toolName in @('xelatex', 'biber', 'makeindex')) {
        if (-not (Get-Command $toolName -ErrorAction SilentlyContinue)) {
            throw "Missing $toolName. Add the existing TeX Live bin directory to PATH."
        }
    }
    if (-not (Test-Path -LiteralPath $indexStyle)) { throw "Missing $indexStyle" }
    if (-not (Test-Path -LiteralPath (Join-Path $bookDir "$bookName.tex"))) {
        throw "Missing $bookName.tex"
    }
    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
    $texArguments = @('-interaction=nonstopmode', '-halt-on-error', '-synctex=1',
        "-output-directory=$relativeOutput", "$bookName.tex")

    Push-Location -LiteralPath $bookDir
    try {
        Invoke-BuildStep 'xelatex' $texArguments 'xelatex-1'
        $bcf = Join-Path $buildDir "$bookName.bcf"
        if ((Test-Path -LiteralPath $bcf) -and
            ((Get-Content -Raw -LiteralPath $bcf) -match '<bcf:citekey[^>]*>')) {
            # Relative paths avoid Biber's Windows Unicode absolute-path issue.
            Invoke-BuildStep 'biber' @("--output-directory=$relativeOutput",
                "$relativeOutput/$bookName") 'biber'
        } else {
            Write-Host "[$bookName] No citations; skipping Biber."
            foreach ($extension in @('bbl', 'blg')) {
                $staleFile = Join-Path $buildDir "$bookName.$extension"
                if (Test-Path -LiteralPath $staleFile) {
                    Remove-Item -LiteralPath $staleFile -Force
                }
            }
        }
    } finally { Pop-Location }

    $builtIndexes = @()
    $indexInputHashes = @{}
    foreach ($indexName in @('chinese', 'foreign', 'symbols')) {
        $idx = Join-Path $buildDir "$indexName.idx"
        if (-not (Test-Path -LiteralPath $idx) -or (Get-Item -LiteralPath $idx).Length -eq 0) {
            foreach ($extension in @('ind', 'ilg')) {
                $staleFile = Join-Path $buildDir "$indexName.$extension"
                if (Test-Path -LiteralPath $staleFile) {
                    Remove-Item -LiteralPath $staleFile -Force
                }
            }
            Write-Host "[$bookName] $indexName index is empty."
            continue
        }
        $indexInputHashes[$indexName] = (Get-FileHash -LiteralPath $idx).Hash
        Push-Location -LiteralPath $buildDir
        try {
            Invoke-BuildStep 'makeindex' @('-q', '-s', $indexStyle, "$indexName.idx") "index-$indexName"
        } finally { Pop-Location }
        $indexOutput = Join-Path $buildDir "$indexName.ind"
        $indexLog = Get-Content -Raw -LiteralPath (Join-Path $buildDir "$indexName.ilg")
        if (-not (Test-Path -LiteralPath $indexOutput) -or
            (Get-Item -LiteralPath $indexOutput).Length -eq 0 -or
            $indexLog -notmatch '\b0 rejected\b' -or $indexLog -notmatch '\b0 warnings\b') {
            throw "$indexName index failed validation; see $buildDir."
        }
        $builtIndexes += $indexName
    }

    Push-Location -LiteralPath $bookDir
    try {
        foreach ($pass in 2..3) {
            Invoke-BuildStep 'xelatex' $texArguments "xelatex-$pass"
        }
    } finally { Pop-Location }

    # A new contents tree may need more passes before references stabilize.
    # Keep this bounded; the final diagnostic check still rejects unresolved runs.
    Push-Location -LiteralPath $bookDir
    try {
        foreach ($referenceRound in 1..3) {
            $referenceLog = Get-Content -Raw -LiteralPath $logFile
            if ($referenceLog -notmatch 'Label\(s\) may have changed|Rerun to get cross-references right|Please rerun LaTeX') {
                break
            }
            Invoke-BuildStep 'xelatex' $texArguments "xelatex-reference-sync-$referenceRound"
        }
    } finally { Pop-Location }

    # A clean first pass has no resolved references or contents yet. Its index
    # page numbers can therefore differ from the later typesetting passes.
    # Rebuild only changed index inputs, then settle references before publishing.
    $indexesStable = $false
    foreach ($indexRound in 1..4) {
        $changedIndexes = @($builtIndexes | Where-Object {
            (Get-FileHash -LiteralPath (Join-Path $buildDir "$_.idx")).Hash -ne $indexInputHashes[$_]
        })
        if ($changedIndexes.Count -eq 0) {
            $indexesStable = $true
            break
        }
        if ($indexRound -eq 4) { break }
        foreach ($indexName in $changedIndexes) {
            $idx = Join-Path $buildDir "$indexName.idx"
            $indexInputHashes[$indexName] = (Get-FileHash -LiteralPath $idx).Hash
            Push-Location -LiteralPath $buildDir
            try {
                Invoke-BuildStep 'makeindex' @('-q', '-s', $indexStyle, "$indexName.idx") "index-$indexName-sync-$indexRound"
            } finally { Pop-Location }
            $indexOutput = Join-Path $buildDir "$indexName.ind"
            $indexLog = Get-Content -Raw -LiteralPath (Join-Path $buildDir "$indexName.ilg")
            if (-not (Test-Path -LiteralPath $indexOutput) -or
                (Get-Item -LiteralPath $indexOutput).Length -eq 0 -or
                $indexLog -notmatch '\b0 rejected\b' -or $indexLog -notmatch '\b0 warnings\b') {
                throw "$indexName index failed validation; see $buildDir."
            }
        }
        Push-Location -LiteralPath $bookDir
        try {
            foreach ($pass in 1..2) {
                Invoke-BuildStep 'xelatex' $texArguments "xelatex-index-sync-$indexRound-$pass"
            }
        } finally { Pop-Location }
    }
    if (-not $indexesStable) { throw "Index page numbers did not stabilize; see $buildDir." }

    $buildLog = Get-Content -Raw -LiteralPath $logFile
    $fatalPatterns = @('(?m)^! ', 'There were undefined references',
        'Citation .* undefined', 'Missing character', 'multiply-defined',
        'Label\(s\) may have changed', 'Rerun to get cross-references right',
        'Please \(re\)run Biber', 'Please rerun LaTeX', 'Token not allowed in a PDF string')
    foreach ($pattern in $fatalPatterns) {
        if ($buildLog -match $pattern) { throw "Unresolved build diagnostic: $pattern. See $logFile" }
    }
    foreach ($indexName in $builtIndexes) {
        if (-not $buildLog.Contains("$indexName.ind")) {
            throw "$indexName index was generated but not included in the PDF."
        }
    }
    foreach ($extension in @('pdf', 'synctex.gz')) {
        $artifact = Join-Path $buildDir "$bookName.$extension"
        if (-not (Test-Path -LiteralPath $artifact) -or (Get-Item -LiteralPath $artifact).Length -eq 0) {
            throw "Missing or empty build artifact: $artifact"
        }
    }
    Copy-Item -LiteralPath (Join-Path $buildDir "$bookName.pdf") -Destination $bookDir -Force
    Copy-Item -LiteralPath (Join-Path $buildDir "$bookName.synctex.gz") -Destination $bookDir -Force
    Copy-Item -LiteralPath (Join-Path $buildDir "$bookName.pdf") -Destination $projectRoot -Force
    $pageSummary = ([regex]::Match($buildLog, 'Output written on[^\r\n]+')).Value
    Write-Host "[$bookName] $pageSummary" -ForegroundColor Green
    Write-Host "[$bookName] Verified and published locally in $([int]((Get-Date) - $started).TotalSeconds)s." -ForegroundColor Green
} finally {
    $env:PATH = $previousPath
}
