param(
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [ValidateSet('Current','School')][string]$Context='Current',
    [ValidateSet('1','1.25','1.5')][string]$QtScale='1'
)
$ErrorActionPreference='Stop'
$kitRoot=$PSScriptRoot
$targetRoot=[IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $targetRoot) { throw 'OutputRoot already exists; use a new folder.' }
[void][IO.Directory]::CreateDirectory($targetRoot)
function Write-NewJson($path,$value) {
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
    try { $writer.Write(($value | ConvertTo-Json -Depth 35)) } finally { $writer.Dispose() }
}
function Write-NewText($path,$value) {
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
    try { $writer.Write($value) } finally { $writer.Dispose() }
}
function Hash-File($path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$result=[ordered]@{status='incomplete';phase='preflight';recorded_at_utc=[DateTime]::UtcNow.ToString('o');context_declared_by_operator=$Context;context_independently_verified=$false;qt_scale_factor=$QtScale;scale_scope='Process-only Qt simulation; OS display settings unchanged';school_acceptance='not evaluated';real_student_data_used=$false;normal_launch_performed=$false;setup_executed=$false;security_policy_changed=$false;shortcut_changed=$false;parent_process_environment_modified=$false;exit_code=$null;checks_passed=0;errors=@()}
$process=$null
try {
    $lock=Get-Content -LiteralPath (Join-Path $kitRoot 'CANDIDATE_LOCK.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifestPath=Join-Path $kitRoot 'WINDOWS_FILES.json.gz'
    if ((Hash-File $manifestPath) -ne '969b6b748c5bcc025ca5ea431cc4841364afcc6c96f8e7b65478ad76786aef07') { throw 'File manifest SHA256 mismatch.' }
    $manifestStream=[IO.File]::OpenRead($manifestPath)
    $manifestGzip=[IO.Compression.GZipStream]::new($manifestStream,[IO.Compression.CompressionMode]::Decompress)
    $manifestReader=[IO.StreamReader]::new($manifestGzip,[Text.Encoding]::UTF8)
    try { $files=$manifestReader.ReadToEnd() | ConvertFrom-Json }
    finally { $manifestReader.Dispose() }
    $zipPath=Join-Path $kitRoot $lock.windows.zip
    $result.source_commit=$lock.source_commit
    if ($lock.source_commit -ne '943115609854894bc7be8b5b6ec1edc6fef29095' -or $lock.version -ne '1.0.6' -or $lock.windows.zip_sha256 -ne 'f9cb228af774b53fa6ccb73a64f5a9b55a6c15fc1b551b253ded9adad6f6aaaa' -or $lock.windows.exe_sha256 -ne 'a7c157823a648433d9d420fdd73216b8777fe7066a5bf37b3484e3758f3b9701') { throw 'Candidate lock identity mismatch.' }
    if ((Hash-File $zipPath) -ne $lock.windows.zip_sha256) { throw 'Candidate ZIP SHA256 mismatch.' }
    $result.zip_sha256=$lock.windows.zip_sha256
    $appRoot=Join-Path $targetRoot 'candidate'
    [void][IO.Directory]::CreateDirectory($appRoot)
    $prefix=$appRoot+[IO.Path]::DirectorySeparatorChar
    $result.phase='extract-and-verify'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::OpenRead($zipPath)
    $seen=New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $fileCount=0
    try {
        foreach ($entry in $archive.Entries) {
            $name=$entry.FullName.Replace('\','/')
            if ([string]::IsNullOrEmpty($name) -or $name.StartsWith('/') -or $name.Contains(':')) { throw 'Unsafe ZIP path.' }
            foreach ($part in $name.Split('/')) { if ($part -eq '..' -or $part -eq '.' -or $part.EndsWith(' ') -or $part.EndsWith('.')) { throw 'Unsafe ZIP segment.' } }
            if (-not $seen.Add($name)) { throw 'Duplicate ZIP path.' }
            if ((([int64]$entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'ZIP symlink is not allowed.' }
            $destination=[IO.Path]::GetFullPath((Join-Path $appRoot $name.Replace('/',[IO.Path]::DirectorySeparatorChar)))
            if (-not $destination.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'ZIP path escapes output root.' }
            if ($name.EndsWith('/')) { [void][IO.Directory]::CreateDirectory($destination); continue }
            $expected=$files.PSObject.Properties[$name]
            if ($null -eq $expected -or $entry.Length -ne $expected.Value.bytes) { throw ('Unexpected ZIP file: '+$name) }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
            $entryStream=$entry.Open()
            $output=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $entryStream.CopyTo($output) } finally { $output.Dispose(); $entryStream.Dispose() }
            if ((Hash-File $destination) -ne $expected.Value.sha256) { throw ('Extracted file SHA256 mismatch: '+$name) }
            $fileCount++
        }
    } finally { $archive.Dispose() }
    if ($fileCount -ne @($files.PSObject.Properties).Count) { throw 'Candidate file count mismatch.' }
    $result.verified_files=$fileCount
    $identity=Get-Content -LiteralPath (Join-Path $appRoot 'BUILD_SOURCE.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($identity.source_commit -ne $lock.source_commit -or $identity.source_clean -ne $true -or $identity.version -ne $lock.version -or $identity.target -ne 'windows') { throw 'Embedded source identity mismatch.' }
    $exe=Join-Path $appRoot 'Goedu-Split.exe'
    if ((Hash-File $exe) -ne $lock.windows.exe_sha256) { throw 'Executable SHA256 mismatch.' }
    $result.executable_sha256=$lock.windows.exe_sha256
    $result.authenticode=(Get-AuthenticodeSignature -LiteralPath $exe).Status.ToString()
    $isolation=Join-Path $targetRoot 'process-isolation'
    foreach ($leaf in @('tmp','roaming','local')) { [void][IO.Directory]::CreateDirectory((Join-Path $isolation $leaf)) }
    $qaRoot=Join-Path $targetRoot 'synthetic-qa'
    if ($qaRoot.Contains('"') -or $qaRoot.Contains("`n") -or $qaRoot.Contains("`r")) { throw 'Invalid QA output argument.' }
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$exe
    $start.Arguments='--synthetic-qa "'+$qaRoot+'"'
    $start.WorkingDirectory=$appRoot
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $start.EnvironmentVariables['APPDATA']=Join-Path $isolation 'roaming'
    $start.EnvironmentVariables['LOCALAPPDATA']=Join-Path $isolation 'local'
    $start.EnvironmentVariables['TEMP']=Join-Path $isolation 'tmp'
    $start.EnvironmentVariables['TMP']=Join-Path $isolation 'tmp'
    $start.EnvironmentVariables['QT_SCALE_FACTOR']=$QtScale
    foreach ($variable in @('QT_QPA_PLATFORM','QT_SCREEN_SCALE_FACTORS','QT_FONT_DPI')) { $start.EnvironmentVariables.Remove($variable) }
    $result.phase='start-isolated-frozen-qa'
    $process=New-Object Diagnostics.Process
    $process.StartInfo=$start
    [void]$process.Start()
    $result.test_pid=$process.Id
    $stdout=$process.StandardOutput.ReadToEndAsync()
    $stderr=$process.StandardError.ReadToEndAsync()
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while (-not $process.WaitForExit(1000)) {
        if ($timer.Elapsed.TotalSeconds -gt 450) { $process.Kill(); $result.timed_out=$true; throw 'Only this isolated test process was terminated after 450 seconds.' }
    }
    $result.duration_seconds=[Math]::Round($timer.Elapsed.TotalSeconds,3)
    $result.exit_code=$process.ExitCode
    if ($stdout.Wait(2000)) { Write-NewText (Join-Path $targetRoot 'stdout.log') $stdout.Result }
    if ($stderr.Wait(2000)) { Write-NewText (Join-Path $targetRoot 'stderr.log') $stderr.Result }
    $result.phase='validate-results'
    if ($process.ExitCode -ne 0) { throw ('Frozen QA exit code '+$process.ExitCode) }
    $qa=Get-Content -LiteralPath (Join-Path $qaRoot 'QA_REPORT.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($qa.status -ne 'passed' -or $qa.frozen -ne $true -or @($qa.errors).Count -ne 0 -or $qa.executable_sha256 -ne $lock.windows.exe_sha256) { throw 'Frozen QA identity or status mismatch.' }
    if (@(Compare-Object -ReferenceObject @($lock.checks_required) -DifferenceObject @($qa.checks.PSObject.Properties.Name)).Count -ne 0) { throw 'Missing or extra QA check.' }
    foreach ($check in $qa.checks.PSObject.Properties) { if ($check.Value -isnot [bool] -or $check.Value -ne $true) { throw ('Failed QA check: '+$check.Name) } }
    if ($qa.native_window.platform -ne 'windows' -or $qa.native_window.initial_id -ne $qa.native_window.final_id -or @($qa.native_window.destroyed_before_close).Count -ne 0) { throw 'Native main window was not preserved.' }
    if (@($qa.unexpected_chart_windows).Count -ne 0 -or (Get-Item -LiteralPath (Join-Path $qaRoot 'NATIVE_CRASH.log')).Length -ne 0) { throw 'Unexpected chart window or native crash log.' }
    $result.checks_passed=@($qa.checks.PSObject.Properties).Count
    $result.portfolio=$qa.portfolio
    $result.chart_images=@($qa.analysis.chart_files).Count
    $result.status='passed-automated-synthetic-only'
    $result.phase='complete'
} catch {
    $result.status='failed-or-blocked'
    $result.errors=@([ordered]@{exception_type=$_.Exception.GetType().FullName;message=$_.Exception.Message;hresult=$_.Exception.HResult;native_error_code=$_.Exception.NativeErrorCode})
} finally {
    if ($null -ne $process) { $process.Dispose() }
    Write-NewJson (Join-Path $targetRoot 'RUN_RESULT.json') $result
}
$result | ConvertTo-Json -Depth 12
if ($result.status -ne 'passed-automated-synthetic-only') { exit 1 }
