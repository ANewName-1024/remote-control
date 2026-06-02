<#
.SYNOPSIS
    Build a tar.gz of the server/ folder for VPS deployment.
.DESCRIPTION
    Excludes node_modules, .git, logs, runtime artifacts, IDE files.
    Output: deploy/dist/remote-control-server-<timestamp>.tar.gz
.EXAMPLE
    pwsh ./build-tar.ps1
    pwsh ./build-tar.ps1 -OutDir C:\temp
#>
[CmdletBinding()]
param(
    [string]$OutDir
)

# $PSScriptRoot is empty when invoked via some PowerShell hosts; fall back
# to MyInvocation.Definition for portability.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $OutDir) { $OutDir = Join-Path $scriptDir 'dist' }

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $scriptDir -Parent)  # project root

$stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$tarball = Join-Path $OutDir "remote-control-server-$stamp.tar.gz"
$null    = New-Item -ItemType Directory -Path $OutDir -Force

# Files / dirs to skip. Anchored to path boundary to avoid false positives
# (e.g. 'my_node_modules_thing' must not match).
$skip = @(
    'node_modules',
    '.git',
    '__pycache__',
    'dist',           # build output
    'build',          # build output
    'agent',          # Windows-only, not deployed to VPS
    'rust-relay',     # legacy Rust rewrite (kept for reference, not deployed)
    'tests',          # test fixtures
    'server\uploads', # runtime artifacts
    'server\static\app', # nested fixture dirs for tests
    'agent_*.log',
    '*.log',
    '*.pyc',
    '*.pyo',
    '*.egg-info',
    '.DS_Store',
    'Thumbs.db',
    'deploy\dist',
    'deploy\.env.vps',       # real config (uploaded separately via scp)
    'deploy\*.tar.gz',       # any generated tarball
    'deploy\check-mkdir.js', # debug helper, not part of deploy
    'AGENT.md.old',
    'AGENT.md',
    'DEBUGGING.md',
    'REFACTORING.md',
    'README.md',
    'SPEC.md',
    'test_design.md',
    'test_*.js',
    'smoke_test.js',
    'run_all_tests.ps1'
)

# tar on Windows 10+ supports --exclude and gzip. Use a relative list rooted at the project.
# We need to cd to the project root and tar *relative* paths so the tarball structure
# is server/, deploy/, etc. (deploy/ is included for the vps-install.sh + service file).
Push-Location .
try {
    $relPath = Resolve-Path . -Relative  # e.g. '.\projects\devtools\remote-control'
    Write-Host "[build-tar] project root: $((Get-Location).Path)"
    Write-Host "[build-tar] exclude rules: $($skip.Count)"

    # tar syntax on Windows: tar -czf OUT -C DIR <files...>
    $projectRoot = (Get-Location).Path
    $projectRoot = (Get-Location).Path
    # Use Get-ChildItem directly — GFS's -Include doesn't accept directory names
    # as entries (it expects file globs), so for tar packaging Get-ChildItem is
    # more predictable. GFS is still the right tool for ad-hoc file listing.
    $rawFiles = @(Get-ChildItem -Recurse -File -Force -ErrorAction SilentlyContinue)
    $entries = $rawFiles |
        Where-Object { $_.FullName -notmatch '[\\/](?:node_modules|\.git)[\\/]' -and $_.FullName -notmatch '\.(log|pyc|pyo)$' } |
        ForEach-Object { $_.FullName.Substring($projectRoot.Length + 1) }

    # Convert absolute to relative for tar (so the tarball stores `server/...`)
    $files = $entries | ForEach-Object { $_ -replace [regex]::Escape($projectRoot + '\'), '' }

    if (-not $files -or $files.Count -lt 1) {
        throw "no files to package"
    }
    Write-Host "[build-tar] entries after filter: $(@($files).Count)"

    # Apply excludes in PowerShell (more reliable than tar --exclude on Windows shell quoting).
    # Each pattern matches when preceded by start-of-string or path separator AND
    # followed by path separator or end-of-string — so root-level files like
    # 'AGENT.md' or 'run_all_tests.ps1' are matched (start-of-string + EOL) and
    # nested ones like '.git/config' or 'server/uploads' are matched (separator pairs).
    $excludeRe = [regex](
        '(?im)^(?:' + (($skip | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')(?:[\\/]|$)'
    )
    $kept = $files | Where-Object { $_ -notmatch $excludeRe.ToString() }
    Write-Host "[build-tar] files after excludes: $(@($kept).Count)"

    # Build tar with native Windows tar (BSDTAR / libarchive). Write filename list
    # to a temp file (-T <file>) — piping from PowerShell's | into tar's stdin
    # has had reliability issues on Windows (cmd quoting, encoding).
    $listFile = Join-Path ([System.IO.Path]::GetTempPath()) "rc-tar-$(Get-Random).txt"
    try {
        # Relative paths in the list file. Combined with `-C $projectRoot` in
        # the tar command below, this stores files as `server/index.js` etc.
        # in the tarball (no `D:\` drive-letter prefix that would break the
        # VPS extraction step).
        #
        # NB: BSD tar on Windows skips the first line of `-T` files (treats
        # it as a comment/header). We prepend a synthetic comment line so all
        # real entries are processed.
        $relList = @('# remote-control-server tarball - generated by build-tar.ps1') + $kept
        $relList | Set-Content -Path $listFile -Encoding UTF8
        Write-Host "[build-tar] tar -czf $tarball -C $projectRoot (from $listFile, $($kept.Count) files)"

        # BSD tar on Windows emits warnings to stderr even on success (e.g.
        # "Removing leading drive letter from member names"). PowerShell's
        # &-invocation of native commands with `2>&1` has shown odd behavior
        # on Windows 10 / PS 5.1, so we route through cmd /c to keep stderr
        # and stdout cleanly separated.
        $stderrFile = "$listFile.stderr"
        cmd /c "tar -czf `"$tarball`" -C `"$projectRoot`" -T `"$listFile`" 1>nul 2> `"$stderrFile`""
        if (Test-Path $stderrFile) {
            Get-Content $stderrFile | ForEach-Object { if ($_) { Write-Host "[tar] $_" } }
            Remove-Item $stderrFile -ErrorAction SilentlyContinue
        }

        # Sanity check: did tar actually write a non-empty archive?
        if (-not (Test-Path $tarball)) {
            throw "tar did not produce $tarball"
        }
        $size = (Get-Item $tarball).Length
        if ($size -lt 100) {
            throw "tar archive suspiciously small ($size bytes) — likely empty"
        }
    }
    finally {
        Remove-Item $listFile -ErrorAction SilentlyContinue
    }

    $size = (Get-Item $tarball).Length
    Write-Host "[build-tar] wrote $tarball ($([math]::Round($size/1KB,1)) KB, $($kept.Count) files)"
}
finally {
    Pop-Location
}
