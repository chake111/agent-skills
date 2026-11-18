<#
.SYNOPSIS
    Link the skills in this repository into an agent skills directory.

.DESCRIPTION
    Creates one directory junction per folder under .\skills.
    Existing entries are left untouched and reported as skipped.

.PARAMETER Target
    Skills directory to install into. Defaults to $HOME\.agents\skills.

.EXAMPLE
    .\scripts\install.ps1
    .\scripts\install.ps1 -Target "$HOME\.claude\skills"
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $HOME '.agents\skills')
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillsDir = Join-Path $repoRoot 'skills'

if (-not (Test-Path -LiteralPath $skillsDir -PathType Container)) {
    throw "skills directory not found: $skillsDir"
}

if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
}

Write-Host "source: $skillsDir"
Write-Host "target: $Target"
Write-Host ""

$created = 0
$skipped = 0
$failed = 0

Get-ChildItem -LiteralPath $skillsDir -Directory | Sort-Object Name | ForEach-Object {
    $name = $_.Name
    $source = $_.FullName
    $link = Join-Path $Target $name

    if (Test-Path -LiteralPath $link) {
        $existing = Get-Item -LiteralPath $link -Force
        if ($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            Write-Host "skip   $name (a link already exists)"
        }
        else {
            Write-Host "skip   $name (a real directory or file already exists)"
        }
        $skipped++
        return
    }

    try {
        New-Item -ItemType Junction -Path $link -Target $source -ErrorAction Stop | Out-Null
        Write-Host "link   $name -> $source"
        $created++
    }
    catch {
        Write-Warning "failed $name : $($_.Exception.Message)"
        $failed++
    }
}

Write-Host ""
Write-Host "created: $created, skipped: $skipped, failed: $failed"

if ($failed -gt 0) {
    exit 1
}