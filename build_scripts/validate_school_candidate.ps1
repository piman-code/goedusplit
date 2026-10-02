# Install-free validation of one immutable candidate. Windows PowerShell 5.1+.
# Example: powershell -NoProfile -File validate_school_candidate.ps1 -CandidateZip <zip> -OutputRoot <new-folder> -Context School
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CandidateZip,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [ValidateSet('Unconfirmed', 'School', 'CI')][string]$Context = 'Unconfirmed',
    [ValidateRange(30, 900)][int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Version = '1.0.6'
$Commit = 'a7f7d95b6a751606ac75d1f6958ed9686bd9884b'
$ZipHash = '446a5478fef905f60dee2e83269394c7a2f27f80e9feed7d8fdfad9057563069'
$ExeHash = 'ca46662ff46611a8dc7716d356a102eb12acb7a240453f8bcac5ec398c22b965'
$GuideHash = '7539ac6d1f4b5863a7f73a44f6c151a1060207d78aa8e1c7dd5dd50e3c93143f'
$ExpectedChecks = @(
    'settings are explicit isolated INI', 'portfolio is isolated',
    'WebEngine is off the record', 'bundled calculator renders',
    'synthetic file loads and preserves fractional business values',
    'real JSON download preserves business values', 'downloaded work reopens',
    'cancelled save creates no extra JSON', 'tab switch retains loaded work',
    'no JavaScript or native warnings', 'core flow attempted no network',
    'native window capture exists'
)

function Assert-NoReparsePath([string]$Path) {
    $current = $Path
    while (-not [string]::IsNullOrEmpty($current)) {
        $item = $null
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch [System.Management.Automation.ItemNotFoundException] { }
        if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Reparse point refused'
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}

function Assert-True($Condition) {
    if (-not $Condition) { throw 'Validation assertion failed' }
}

function Read-Utf8Json([string]$Path) {
    $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
    return ([IO.File]::ReadAllText($Path, $utf8) | ConvertFrom-Json)
}

function Write-ExclusiveReport([string]$Path, $Value) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes(($Value | ConvertTo-Json -Depth 8))
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}

$report = [ordered]@{
    status = 'failed'; version = $Version; source_commit = $Commit
    candidate_zip_sha256 = $ZipHash; executable_sha256 = $ExeHash
    context = $Context; context_is_operator_declared = $true
    presentation = $(if ($Context -eq 'CI') { 'offscreen' } else { 'native' })
    validation_scope = 'synthetic candidate flow only'
    school_acceptance = 'not evaluated; no T01-T09 completion is inferred'
    os_version = [Environment]::OSVersion.Version.ToString()
    powershell_version = $PSVersionTable.PSVersion.ToString()
    checks = [ordered]@{}; errors = @(); exit_code = 1
    process_environment_restored = $true
}
$stage = 'platform'
$createdRoot = $false
$process = $null
$archive = $null
$zipStream = $null
$hasher = $null
$qpaChanged = $false
$previousQpa = [Environment]::GetEnvironmentVariable('QT_QPA_PLATFORM', 'Process')

try {
    Assert-True ($PSVersionTable.PSVersion -ge [Version]'5.1')
    Assert-True ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)
    $stage = 'output-path'
    $outputPath = [IO.Path]::GetFullPath($OutputRoot)
    Assert-True (-not $outputPath.StartsWith('\\'))
    Assert-NoReparsePath $outputPath
    $stage = 'existing-output'
    if (Test-Path -LiteralPath $outputPath) { throw 'Existing output preserved' }
    $stage = 'output-parent'
    Assert-True ([IO.Directory]::Exists([IO.Path]::GetDirectoryName($outputPath)))
    $null = New-Item -ItemType Directory -Path $outputPath -ErrorAction Stop
    $createdRoot = $true

    $stage = 'zip-path'
    $zipPath = [IO.Path]::GetFullPath($CandidateZip)
    Assert-True (-not $zipPath.StartsWith('\\'))
    Assert-NoReparsePath $zipPath
    Assert-True ([IO.File]::Exists($zipPath))
    $stage = 'zip-hash'
    $zipStream = [IO.File]::Open($zipPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $hasher = [Security.Cryptography.SHA256]::Create()
    $actualZipHash = [BitConverter]::ToString($hasher.ComputeHash($zipStream)).Replace('-', '').ToLowerInvariant()
    Assert-True ($actualZipHash -ceq $ZipHash)
    $zipStream.Position = 0
    $report.checks['pinned ZIP hash'] = $true

    $stage = 'zip-type-load'
    # ZipArchive and ZipArchiveMode belong to this assembly in .NET Framework.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $stage = 'zip-archive-open'
    $archive = New-Object -TypeName System.IO.Compression.ZipArchive -ArgumentList @($zipStream, [IO.Compression.ZipArchiveMode]::Read, $true)
    $stage = 'zip-entries'
    $names = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $entries = @{}
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        Assert-True (-not [string]::IsNullOrWhiteSpace($name))
        Assert-True (-not $name.StartsWith('/') -and $name -notmatch '[:\x00-\x1f]')
        Assert-True ($name -notmatch '(^|/)\.{1,2}(/|$)' -and $name -notmatch '//')
        $key = $name.TrimEnd('/')
        foreach ($part in $key.Split('/')) {
            Assert-True ($part -notmatch '[. ]$' -and $part -notmatch '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)')
        }
        Assert-True ($names.Add($key))
        Assert-True ((($entry.ExternalAttributes -shr 16) -band 0xF000) -ne 0xA000)
        Assert-True (($entry.ExternalAttributes -band 0x400) -eq 0)
        $entries[$name] = $entry
    }
    foreach ($required in @('Goedu-Split.exe', 'BUILD_SOURCE.json', '_internal/PySide6/QtWebEngineProcess.exe',
            '_internal/PySide6/plugins/platforms/qwindows.dll', '_internal/app/spliter_ox_web/index.html')) {
        Assert-True ($entries.ContainsKey($required) -and $entries[$required].Length -gt 0)
    }
    $report.checks['safe complete ZIP entries'] = $true

    $stage = 'zip-extraction'
    $payload = Join-Path $outputPath 'candidate'
    $null = New-Item -ItemType Directory -Path $payload -ErrorAction Stop
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        $target = [IO.Path]::GetFullPath((Join-Path $payload $name.Replace('/', '\')))
        Assert-True ($target.StartsWith($payload + '\', [StringComparison]::OrdinalIgnoreCase))
        Assert-NoReparsePath $target
        if ($name.EndsWith('/')) {
            $null = [IO.Directory]::CreateDirectory($target)
        } else {
            $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            Assert-NoReparsePath $target
            $entryStream = $entry.Open()
            try {
                $output = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $entryStream.CopyTo($output) } finally { $output.Dispose() }
            } finally { $entryStream.Dispose() }
        }
    }
    $archive.Dispose(); $archive = $null
    $stage = 'embedded-identity'
    $exe = Join-Path $payload 'Goedu-Split.exe'
    Assert-True ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExeHash)
    $identity = Read-Utf8Json (Join-Path $payload 'BUILD_SOURCE.json')
    Assert-True ($identity.source_commit -ceq $Commit -and $identity.version -ceq $Version -and $identity.target -ceq 'windows')
    Assert-True ($identity.source_clean -is [bool] -and $identity.source_clean -eq $true)
    Assert-True ($identity.executable_sha256 -ceq $ExeHash)
    $guideName = [string][char]0xC0AC + [char]0xC6A9 + ' ' + [char]0xC548 + [char]0xB0B4 + '.md'
    Assert-True ((Get-FileHash -LiteralPath (Join-Path $payload $guideName) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $GuideHash)
    $report.checks['executable and source identity'] = $true
    $report.checks['canonical guide hash'] = $true

    $stage = 'frozen-launch'
    # The application creates this directory itself; precreating it is a failure.
    $qaPath = Join-Path $outputPath 'synthetic-qa'
    if ($Context -eq 'CI') {
        [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', 'offscreen', 'Process')
    } else {
        [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', $null, 'Process')
    }
    $qpaChanged = $true
    $process = Start-Process -FilePath $exe -ArgumentList @('--synthetic-qa', ('"' + $qaPath + '"')) -WorkingDirectory $payload -PassThru
    $null = $process.Handle
    $stage = 'frozen-timeout'
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        # Kill only the process tree started above, never an installed app by name.
        & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F *> $null
        throw 'Candidate timed out'
    }
    $process.Refresh()
    $stage = 'frozen-exit'
    Assert-True ($process.ExitCode -eq 0)
    $stage = 'frozen-report'
    $qa = Read-Utf8Json (Join-Path $qaPath 'QA_REPORT.json')
    Assert-True ($qa.status -ceq 'passed' -and $qa.version -ceq $Version -and $qa.os -ceq 'Windows')
    Assert-True ($qa.architecture -ceq 'AMD64' -and $qa.input -ceq 'synthetic only')
    Assert-True ($qa.frozen -is [bool] -and $qa.frozen -eq $true)
    Assert-True ($qa.executable_sha256 -ceq $ExeHash -and @($qa.errors).Count -eq 0)
    $actualChecks = @($qa.checks.PSObject.Properties.Name)
    Assert-True ($actualChecks.Count -eq $ExpectedChecks.Count)
    foreach ($check in $ExpectedChecks) {
        Assert-True ($actualChecks -ccontains $check)
        Assert-True ($qa.checks.$check -is [bool] -and $qa.checks.$check -eq $true)
        $report.checks[$check] = $true
    }
    $stage = 'frozen-capture'
    $png = [IO.File]::ReadAllBytes((Join-Path $qaPath 'candidate-window.png'))
    Assert-True ($png.Length -gt 24)
    Assert-True ([BitConverter]::ToString($png[0..7]) -ceq '89-50-4E-47-0D-0A-1A-0A')
    Assert-True ([Text.Encoding]::ASCII.GetString($png[12..15]) -ceq 'IHDR')
    $widthBytes = [byte[]]$png[16..19]; [Array]::Reverse($widthBytes)
    $heightBytes = [byte[]]$png[20..23]; [Array]::Reverse($heightBytes)
    $report['capture_width'] = [BitConverter]::ToUInt32($widthBytes, 0)
    $report['capture_height'] = [BitConverter]::ToUInt32($heightBytes, 0)
    Assert-True ($report.capture_width -gt 0 -and $report.capture_height -gt 0)
    $report['architecture'] = $qa.architecture
    $report.status = 'passed-synthetic-only'
    $report.exit_code = 0
} catch {
    # Deliberately exclude exception text, paths, account names and hostnames.
    $report.errors = @($stage)
    $report['error_type'] = $_.Exception.GetType().Name
    $report['error_line'] = $_.InvocationInfo.ScriptLineNumber
    $report.status = 'failed'
    $report.exit_code = 1
} finally {
    if ($null -ne $archive) { $archive.Dispose() }
    if ($null -ne $zipStream) { $zipStream.Dispose() }
    if ($null -ne $hasher) { $hasher.Dispose() }
    if ($null -ne $process) {
        try {
            if (-not $process.HasExited) {
                & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F *> $null
            }
        } catch {
            $report.status = 'failed'; $report.exit_code = 1
            $report.errors = @($report.errors) + @('own-process-cleanup')
        } finally { $process.Dispose() }
    }
    if ($qpaChanged) {
        [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', $previousQpa, 'Process')
        $report.process_environment_restored = ([Environment]::GetEnvironmentVariable('QT_QPA_PLATFORM', 'Process') -ceq $previousQpa)
    }
    if ($createdRoot) {
        try {
            Assert-NoReparsePath $outputPath
            Write-ExclusiveReport (Join-Path $outputPath 'SCHOOL_VALIDATION_REPORT.json') $report
        } catch {
            $report.exit_code = 1
            $stage = 'exclusive-report-write'
        }
    }
}
if ($report.exit_code -eq 0) { Write-Host 'Passed: synthetic candidate validation only.' }
else { Write-Host ('Validation failed at stage: ' + $stage + '. Existing and partial outputs are preserved.') }
exit $report.exit_code
