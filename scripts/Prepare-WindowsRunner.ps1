#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$EvidencePath,
    [string]$RunnerTemp = $env:RUNNER_TEMP,
    [string]$RunId = $env:GITHUB_RUN_ID,
    [string]$RunAttempt = $env:GITHUB_RUN_ATTEMPT,
    [string]$GitHubEnvPath = $env:GITHUB_ENV
)

function Get-RunnerDriveObservation {
    param([string]$Label, [string]$ProbePath)
    $record = [ordered]@{
        label = $Label; probe_path = $ProbePath; volume_root = $null
        is_ready = $false; drive_type = $null; available_free_bytes = $null
        total_free_bytes = $null; total_bytes = $null; error = $null
    }
    try {
        if ([string]::IsNullOrWhiteSpace($ProbePath)) { throw 'Probe path is empty' }
        $volume = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($ProbePath))
        $drive = [System.IO.DriveInfo]::new($volume)
        $record.volume_root = $volume
        $record.is_ready = $drive.IsReady
        $record.drive_type = $drive.DriveType.ToString()
        if (-not $drive.IsReady) { throw 'Volume is not ready' }
        $record.available_free_bytes = $drive.AvailableFreeSpace
        $record.total_free_bytes = $drive.TotalFreeSpace
        $record.total_bytes = $drive.TotalSize
    }
    catch { $record.error = $_.Exception.Message }
    return [pscustomobject]$record
}

function Get-RunnerEligibleDrives {
    param([object[]]$Observations)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($record in $Observations) {
        if ($record.is_ready -and $record.drive_type -eq 'Fixed' -and
            $null -ne $record.available_free_bytes -and $record.available_free_bytes -ge 30GB -and
            $seen.Add($record.volume_root)) {
            $record
        }
    }
}

function New-RunnerWorkRoot {
    param([string]$VolumeRoot, [string]$Id, [string]$Attempt, [string]$Nonce)
    if ($Id -notmatch '^[0-9]+$' -or $Attempt -notmatch '^[0-9]+$' -or $Nonce -notmatch '^[a-f0-9]{8}$') {
        throw 'Run ID, attempt and nonce must form one safe path component'
    }
    return [System.IO.Path]::Combine($VolumeRoot, 'b3117', "$Id-$Attempt-$Nonce")
}

function ConvertTo-RunnerEnvironmentEntry {
    param([string]$WorkRoot)
    if ([string]::IsNullOrWhiteSpace($WorkRoot) -or $WorkRoot.Contains([char]13) -or $WorkRoot.Contains([char]10)) {
        throw 'Work root must be a nonempty single-line value'
    }
    return "BIM3117_ACCEPTANCE_ROOT=$WorkRoot"
}

function Get-RunnerDesktopObservation {
    $record = [ordered]@{
        kind = 'informational_native_windows_observation'
        session_id = $null; window_station_visible = $null; monitor_count = $null
        virtual_screen = $null; user_interactive = [System.Environment]::UserInteractive
        errors = @()
        note = 'These WinAPI observations are not Qt desktop acceptance; the later GUI gate remains required.'
    }
    try {
        if (-not ('Bim3117Runner.NativeDesktop' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Bim3117Runner {
    [StructLayout(LayoutKind.Sequential)]
    public struct UserObjectFlags {
        [MarshalAs(UnmanagedType.Bool)] public bool Inherit;
        [MarshalAs(UnmanagedType.Bool)] public bool Reserved;
        public uint Flags;
    }
    public static class NativeDesktop {
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool ProcessIdToSessionId(uint processId, out uint sessionId);
        [DllImport("user32.dll", SetLastError=true)]
        public static extern IntPtr GetProcessWindowStation();
        [DllImport("user32.dll", EntryPoint="GetUserObjectInformationW", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetUserObjectInformation(
            IntPtr handle, int index, out UserObjectFlags flags, uint length, out uint needed);
        [DllImport("user32.dll")]
        public static extern int GetSystemMetrics(int index);
    }
}
'@
        }
        [uint32]$session = 0
        if ([Bim3117Runner.NativeDesktop]::ProcessIdToSessionId([uint32]$PID, [ref]$session)) {
            $record.session_id = $session
        }
        else { $record.errors += "ProcessIdToSessionId Win32 error: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
        $station = [Bim3117Runner.NativeDesktop]::GetProcessWindowStation()
        if ($station -eq [IntPtr]::Zero) {
            $record.errors += "GetProcessWindowStation Win32 error: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
        }
        else {
            $flags = [Bim3117Runner.UserObjectFlags]::new()
            [uint32]$needed = 0
            [uint32]$length = [Runtime.InteropServices.Marshal]::SizeOf($flags)
            if ([Bim3117Runner.NativeDesktop]::GetUserObjectInformation($station, 1, [ref]$flags, $length, [ref]$needed)) {
                $record.window_station_visible = [bool]($flags.Flags -band 1)
            }
            else { $record.errors += "GetUserObjectInformation Win32 error: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
        }
        $record.monitor_count = [Bim3117Runner.NativeDesktop]::GetSystemMetrics(80)
        $record.virtual_screen = [ordered]@{
            x = [Bim3117Runner.NativeDesktop]::GetSystemMetrics(76)
            y = [Bim3117Runner.NativeDesktop]::GetSystemMetrics(77)
            width = [Bim3117Runner.NativeDesktop]::GetSystemMetrics(78)
            height = [Bim3117Runner.NativeDesktop]::GetSystemMetrics(79)
        }
    }
    catch { $record.errors += $_.Exception.Message }
    return [pscustomobject]$record
}

function Invoke-RunnerPreparation {
    $ErrorActionPreference = 'Stop'
    $evidenceFile = [System.IO.Path]::GetFullPath($EvidencePath)
    if ([System.IO.File]::Exists($evidenceFile)) { throw "Refusing to overwrite runner evidence: $evidenceFile" }
    $record = [ordered]@{
        schema = 1; kind = 'runner_preparation'; created_at_utc = [DateTime]::UtcNow.ToString('o')
        status = 'started'; minimum_free_bytes = 30GB; powershell_version = $PSVersionTable.PSVersion.ToString()
        operating_system = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
        run_id = $RunId; run_attempt = $RunAttempt
        repository = $env:GITHUB_REPOSITORY; commit = $env:GITHUB_SHA
        drive_observations = @(); write_probes = @(); desktop_observation = $null
        selected_work_root = $null; windows_build_executed = $false; windows_acceptance_executed = $false
        release_ready = $false
    }
    try {
        if (-not $IsWindows) { throw 'Native Windows is required for runner preparation' }
        # C: is preferred because upstream FreeCAD CI reports inadequate workspace-drive capacity.
        $record.drive_observations = @(
            Get-RunnerDriveObservation -Label 'c_drive' -ProbePath 'C:\'
            Get-RunnerDriveObservation -Label 'runner_temp' -ProbePath $RunnerTemp
        )
        # Informational even if the runner is in Session 0 or has no visible window station.
        $record.desktop_observation = Get-RunnerDesktopObservation
        $eligible = @(Get-RunnerEligibleDrives -Observations $record.drive_observations)
        if ($eligible.Count -eq 0) {
            $measurements = ($record.drive_observations | ForEach-Object {
                if ($null -ne $_.available_free_bytes) {
                    "$($_.label) $($_.volume_root): $([Math]::Round($_.available_free_bytes / 1GB, 2)) GiB available"
                }
                else { "$($_.label): $($_.error)" }
            }) -join '; '
            throw "No measured local fixed drive has the required 30 GiB free. $measurements. No unrelated files were removed."
        }
        foreach ($drive in $eligible) {
            $workRoot = New-RunnerWorkRoot -VolumeRoot $drive.volume_root -Id $RunId -Attempt $RunAttempt -Nonce ([Guid]::NewGuid().ToString('N').Substring(0, 8))
            $parent = [System.IO.Path]::GetDirectoryName($workRoot)
            $probe = [System.IO.Path]::Combine($parent, '.probe-' + [Guid]::NewGuid().ToString('N'))
            $createdProbe = $false
            $attemptRecord = [ordered]@{ volume_root = $drive.volume_root; proposed_work_root = $workRoot; writable = $false; error = $null }
            try {
                [System.IO.Directory]::CreateDirectory($parent) | Out-Null
                if (Test-Path -LiteralPath $workRoot) { throw 'Generated work root already exists' }
                $stream = [System.IO.File]::Open($probe, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
                $createdProbe = $true
                try { $stream.WriteByte(0) } finally { $stream.Dispose() }
                $attemptRecord.writable = $true
                $record.selected_work_root = $workRoot
            }
            catch { $attemptRecord.error = $_.Exception.Message }
            finally {
                # Delete only the exact one-byte probe created by this invocation.
                if ($createdProbe) { [System.IO.File]::Delete($probe) }
                $record.write_probes += [pscustomobject]$attemptRecord
            }
            if ($record.selected_work_root) { break }
        }
        if (-not $record.selected_work_root) {
            throw 'Drives met the capacity threshold, but no isolated work-root parent was writable. See write_probes.'
        }
        if ([string]::IsNullOrWhiteSpace($GitHubEnvPath) -or -not [System.IO.File]::Exists($GitHubEnvPath)) {
            throw 'The existing GITHUB_ENV command file is required'
        }
        $entry = ConvertTo-RunnerEnvironmentEntry -WorkRoot $record.selected_work_root
        [System.IO.File]::AppendAllText($GitHubEnvPath, $entry + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        $record.status = 'capacity_prepared_not_acceptance'
        Write-Host "Selected isolated work root: $($record.selected_work_root)"
        Write-Host "Session: $($record.desktop_observation.session_id); visible window station: $($record.desktop_observation.window_station_visible); monitors: $($record.desktop_observation.monitor_count). GUI acceptance remains pending."
    }
    catch {
        $record.status = 'blocked'
        $record.error = $_.Exception.Message
        throw
    }
    finally {
        $record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($evidenceFile)) | Out-Null
        [System.IO.File]::WriteAllText($evidenceFile, ($record | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        Write-Host "Runner preparation evidence: $evidenceFile"
    }
}

# Dot-sourcing exposes the pure path/capacity helpers for focused offline checks.
if ($MyInvocation.InvocationName -ne '.') { Invoke-RunnerPreparation }
