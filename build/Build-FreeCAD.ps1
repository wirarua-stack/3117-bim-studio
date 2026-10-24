#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkRoot,
    [Parameter(Mandatory = $true)][ValidateSet('Unpatched', 'Patched')][string]$Variant,
    [ValidateRange(1, 8)][int]$Jobs = 2,
    [string]$PythonExe = 'python',
    [string]$SevenZipExe = '',
    [switch]$VerifyLocks
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and -not $VerifyLocks) {
    throw 'A real Windows x64 host is required. No Windows build or acceptance was executed.'
}
$Driver = Join-Path $PSScriptRoot 'build_freecad.py'
$DriverArgs = @($Driver, '--work-root', $WorkRoot, '--variant', $Variant.ToLowerInvariant(), '--jobs', "$Jobs")
if ($SevenZipExe) { $DriverArgs += @('--seven-zip', $SevenZipExe) }
if ($VerifyLocks) { $DriverArgs += '--verify-locks' }
& $PythonExe @DriverArgs
if ($LASTEXITCODE -ne 0) { throw "FreeCAD build driver failed with exit code $LASTEXITCODE. See the recorded build logs." }
