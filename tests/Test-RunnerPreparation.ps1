#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../scripts/Prepare-WindowsRunner.ps1') -EvidencePath 'unused-during-pure-helper-checks.json'

function Assert-RunnerCheck {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function New-DriveFixture {
    param([string]$Volume, [long]$Free, [string]$Type = 'Fixed', [bool]$Ready = $true)
    return [pscustomobject]@{ volume_root = $Volume; available_free_bytes = $Free; drive_type = $Type; is_ready = $Ready }
}

$passed = @()
$c = New-DriveFixture 'C:\' 30GB
$d = New-DriveFixture 'D:\' 80GB
$selected = @(Get-RunnerEligibleDrives @($c, $d))
Assert-RunnerCheck ($selected.Count -eq 2 -and $selected[0].volume_root -eq 'C:\') 'The measured C: candidate should retain preference when both qualify'
$passed += 'prefer_c_when_both_have_capacity'

$selected = @(Get-RunnerEligibleDrives @((New-DriveFixture 'C:\' (30GB - 1)), $d))
Assert-RunnerCheck ($selected.Count -eq 1 -and $selected[0].volume_root -eq 'D:\') 'The runner-temp drive should remain available when C: lacks capacity'
$passed += 'fall_back_when_c_below_threshold'

$selected = @(Get-RunnerEligibleDrives @($c, (New-DriveFixture 'c:\' 30GB)))
Assert-RunnerCheck ($selected.Count -eq 1) 'The same measured volume should be selected only once'
$passed += 'deduplicate_same_volume'

$selected = @(Get-RunnerEligibleDrives @(
    (New-DriveFixture 'C:\' (30GB - 1))
    (New-DriveFixture 'D:\' 100GB 'Network')
    (New-DriveFixture 'E:\' 100GB 'Fixed' $false)
))
Assert-RunnerCheck ($selected.Count -eq 0) 'Insufficient, nonlocal and unready volumes must not become build candidates'
$passed += 'reject_inadequate_or_nonlocal_volumes'

$volume = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetTempPath())
$root = New-RunnerWorkRoot -VolumeRoot $volume -Id '123456' -Attempt '2' -Nonce 'abc123ef'
Assert-RunnerCheck ($root -eq [System.IO.Path]::Combine($volume, 'b3117', '123456-2-abc123ef')) 'The root must remain short and isolate a run/attempt/nonce'
Assert-RunnerCheck (-not (Test-Path -LiteralPath $root)) 'Constructing a work-root path must leave it absent for the acceptance controller'
$passed += 'build_short_unique_path_without_creating_it'

$rejectedPath = $false
try { New-RunnerWorkRoot -VolumeRoot $volume -Id '../escape' -Attempt '2' -Nonce 'abc123ef' | Out-Null }
catch { $rejectedPath = $true }
$rejectedEnv = $false
try { ConvertTo-RunnerEnvironmentEntry ("C:\safe" + [char]10 + 'OTHER_VARIABLE=bad') | Out-Null }
catch { $rejectedEnv = $true }
Assert-RunnerCheck ($rejectedPath -and $rejectedEnv) 'Unsafe path components and multiline command-file entries must be rejected'
Assert-RunnerCheck ((ConvertTo-RunnerEnvironmentEntry $root) -eq "BIM3117_ACCEPTANCE_ROOT=$root") 'The command-file entry must name only the intended variable'
$passed += 'reject_path_and_environment_injection'

[ordered]@{
    schema = 1; kind = 'offline_runner_preparation_helper_checks'
    powershell_version = $PSVersionTable.PSVersion.ToString()
    operating_system = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    checks_passed = $passed; count = $passed.Count
    native_desktop_observation_executed = $false
    windows_build_executed = $false; windows_acceptance_executed = $false
} | ConvertTo-Json -Depth 5
