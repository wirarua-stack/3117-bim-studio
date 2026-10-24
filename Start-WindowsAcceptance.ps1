#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkRoot,
    [ValidateRange(1, 8)][int]$Jobs = 2,
    [string]$PythonExe = 'python',
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'scripts/run_acceptance.py'), '--work-root', $WorkRoot,
               '--jobs', "$Jobs", '--powershell', (Join-Path $PSHOME 'pwsh.exe'))
if ($PreflightOnly) { $arguments += '--preflight-only' }
& $PythonExe @arguments
if ($LASTEXITCODE -ne 0) { throw "Windows acceptance stopped with exit code $LASTEXITCODE. Read the run's logs and JSON status." }
