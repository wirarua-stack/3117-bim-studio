#Requires -Version 7.4
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$EvidenceRoot)
$ErrorActionPreference = 'Stop'

function Assert-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
function New-FixtureFile {
    param([string]$Path, [string]$Value = 'fixture')
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($Path)) | Out-Null
    [System.IO.File]::WriteAllText($Path, $Value, [System.Text.UTF8Encoding]::new($false))
}

if (Test-Path -LiteralPath $EvidenceRoot) {
    throw 'Use a fresh synthetic evidence root; refusing to replace an existing tree'
}
$collector = Join-Path $PSScriptRoot '../scripts/Collect-WindowsEvidence.ps1'
$sourceRoot = Join-Path $EvidenceRoot 'complete/source'
$destination = Join-Path $EvidenceRoot 'complete/staging'
$runnerPreflight = Join-Path $EvidenceRoot 'complete/runner-preflight.json'

foreach ($name in @('run.json','preflight.json','WINDOWS_ACCEPTANCE.json',
                    'WINDOWS_ACCEPTANCE.md','controller-logs/collect.log',
                    'results/native-patched/summary.json','ifc-runtime/runtime.json')) {
    New-FixtureFile -Path (Join-Path $sourceRoot $name) -Value $name
}
foreach ($variant in @('unpatched','patched')) {
    foreach ($name in @('host-manifest.json','source-integrity.json','build-status.json','logs/build.log')) {
        New-FixtureFile -Path (Join-Path $sourceRoot "hosts/$variant/$name") -Value "$variant/$name"
    }
}
New-FixtureFile -Path $runnerPreflight -Value 'runner-preflight'
& $collector -Destination $destination -RunRoot $sourceRoot -RunnerPreflight $runnerPreflight
$fullReport = Get-Content -LiteralPath (Join-Path $destination 'collection-status.json') -Raw | ConvertFrom-Json
Assert-Condition ($fullReport.status -eq 'complete_copy') 'Complete source must produce complete_copy'
Assert-Condition (@($fullReport.missing_items).Count -eq 0) 'Complete source must report no missing entries'
Assert-Condition ((Get-Content -LiteralPath (Join-Path $destination 'results/native-patched/summary.json') -Raw) -eq 'results/native-patched/summary.json') 'Native evidence contents must survive copying'
Assert-Condition (Test-Path -LiteralPath (Join-Path $destination 'hosts/patched/logs/build.log')) 'Patched build logs must retain structure'
Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $destination 'results/results'))) 'Collection must not nest directories twice'
Assert-Condition ($fullReport.windows_acceptance_certified -eq $false) 'Evidence copy is not acceptance'

$partialRoot = Join-Path $EvidenceRoot 'partial/source'
$partialDestination = Join-Path $EvidenceRoot 'partial/staging'
New-FixtureFile -Path (Join-Path $partialRoot 'run.json') -Value 'failed-run'
& $collector -Destination $partialDestination -RunRoot $partialRoot
$partialReport = Get-Content -LiteralPath (Join-Path $partialDestination 'collection-status.json') -Raw | ConvertFrom-Json
Assert-Condition ($partialReport.status -eq 'partial_copy') 'Missing reports must remain explicit partial_copy'
Assert-Condition (@($partialReport.missing_items).Count -gt 0) 'Absent files must appear in missing_items'
Assert-Condition (Test-Path -LiteralPath (Join-Path $partialDestination 'run.json')) 'Partial failures must retain existing original evidence'
Assert-Condition ($partialReport.release_ready -eq $false) 'Partial evidence must not authorize release'

$emptyDestination = Join-Path $EvidenceRoot 'missing/staging'
& $collector -Destination $emptyDestination
$emptyReport = Get-Content -LiteralPath (Join-Path $emptyDestination 'collection-status.json') -Raw | ConvertFrom-Json
Assert-Condition ($emptyReport.status -eq 'partial_copy') 'Missing run root must be reported without inventing evidence'
Assert-Condition ($emptyReport.windows_acceptance_certified -eq $false) 'Missing root cannot certify Windows acceptance'

$summary = [ordered]@{
    schema = 1
    kind = 'synthetic_windows_evidence_copy_test'
    status = 'passed'
    scenarios_passed = @('complete_copy','partial_copy','missing_root')
    windows_acceptance_executed = $false
    release_ready = $false
}
[System.IO.File]::WriteAllText(
    (Join-Path $EvidenceRoot 'test-summary.json'),
    (($summary | ConvertTo-Json -Depth 5) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)
$summary | ConvertTo-Json -Depth 5
