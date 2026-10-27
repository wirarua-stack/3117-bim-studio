#Requires -Version 7.4
<#
Copy existing Windows acceptance evidence into artifact staging without changing
or interpreting acceptance verdicts. Missing evidence is reported, not fabricated.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Destination,
    [string]$RunRoot,
    [string]$RunnerPreflight
)
$ErrorActionPreference = 'Stop'
$script:destinationPath = [System.IO.Path]::GetFullPath($Destination)
[System.IO.Directory]::CreateDirectory($script:destinationPath) | Out-Null

$script:copied = [System.Collections.Generic.List[string]]::new()
$script:missing = [System.Collections.Generic.List[string]]::new()
$script:errors = [System.Collections.Generic.List[string]]::new()

function Copy-EvidencePart {
    param([Parameter(Mandatory = $true)][string]$SourcePath,
          [Parameter(Mandatory = $true)][string]$RelativeName)
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        $script:missing.Add($RelativeName)
        return
    }
    $targetPath = Join-Path $script:destinationPath $RelativeName
    try {
        if (Test-Path -LiteralPath $targetPath) {
            throw 'Refusing to overwrite already staged evidence'
        }
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($targetPath)) | Out-Null
        Copy-Item -LiteralPath $SourcePath -Destination $targetPath -Recurse -Force -ErrorAction Stop
        $script:copied.Add($RelativeName)
    }
    catch {
        $script:errors.Add(('{0}: {1}' -f $RelativeName, $_.Exception.Message))
    }
}

if (-not [string]::IsNullOrWhiteSpace($RunnerPreflight)) {
    Copy-EvidencePart -SourcePath $RunnerPreflight -RelativeName 'runner-preflight.json'
}
else {
    $script:missing.Add('runner-preflight.json')
}

if (-not [string]::IsNullOrWhiteSpace($RunRoot) -and
    (Test-Path -LiteralPath $RunRoot -PathType Container)) {
    foreach ($name in @('run.json','preflight.json','WINDOWS_ACCEPTANCE.json',
                        'WINDOWS_ACCEPTANCE.md','controller-logs','results','ifc-runtime')) {
        Copy-EvidencePart -SourcePath (Join-Path $RunRoot $name) -RelativeName $name
    }
    foreach ($variant in @('unpatched','patched')) {
        $hostSource = Join-Path $RunRoot "hosts/$variant"
        foreach ($name in @('host-manifest.json','source-integrity.json','build-status.json','logs')) {
            $relativeName = "hosts/$variant/$name"
            Copy-EvidencePart -SourcePath (Join-Path $hostSource $name) -RelativeName $relativeName
        }
    }
}
else {
    $script:missing.Add('acceptance-run-root')
}

$status = if ($script:errors.Count -gt 0) { 'copy_failed' }
          elseif ($script:missing.Count -gt 0) { 'partial_copy' }
          else { 'complete_copy' }
$report = [ordered]@{
    schema = 1
    kind = 'windows_acceptance_evidence_transport'
    status = $status
    copied_items = $script:copied.ToArray()
    missing_items = $script:missing.ToArray()
    copy_errors = $script:errors.ToArray()
    windows_acceptance_certified = $false
    release_ready = $false
    note = 'Copying evidence does not execute, certify, or override Windows acceptance.'
}
$reportPath = Join-Path $script:destinationPath 'collection-status.json'
[System.IO.File]::WriteAllText(
    $reportPath,
    (($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Evidence transport: $status; copied $($script:copied.Count); missing $($script:missing.Count); errors $($script:errors.Count)"
if ($script:errors.Count -gt 0) {
    throw "Evidence copy failed. Review $reportPath and preserved partial staging."
}
