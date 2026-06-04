# Remote Control Test Runner
# Runs all test suites in sequence. Stops on first failure.
# Usage: powershell -ExecutionPolicy Bypass -File run_all_tests.ps1
#        or just: .\run_all_tests.ps1

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$tests = @(
    @{ Name = 'smoke_test.js (Static Deploy, 15 asserts)'; Cmd = 'node'; Args = @('smoke_test.js') },
    @{ Name = 'upload_test.js (multer 2.x, 12 asserts)'; Cmd = 'node'; Args = @('upload_test.js') },
    @{ Name = 'test_path_security.js (Path security, 16 asserts)'; Cmd = 'node'; Args = @('test_path_security.js') },
    @{ Name = 'test_http_api.js (HTTP REST API, 29 asserts)'; Cmd = 'node'; Args = @('test_http_api.js') },
    @{ Name = 'test_ws_protocol.js (WebSocket protocol, 14 asserts)'; Cmd = 'node'; Args = @('test_ws_protocol.js') },
    @{ Name = 'test_diag.js (App diag dump, 36 asserts)'; Cmd = 'node'; Args = @('test_diag.js') },
    @{ Name = 'test_e2e_flow.js (End-to-end, 24 asserts)'; Cmd = 'node'; Args = @('test_e2e_flow.js') }
)

$totalPassed = 0
$totalFailed = 0
$results = @()

# 1. JS tests
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  JS Test Suites" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

foreach ($t in $tests) {
    Write-Host ""
    Write-Host ">>> Running: $($t.Name)" -ForegroundColor Yellow
    $p = Start-Process -FilePath $t.Cmd -ArgumentList $t.Args -NoNewWindow -Wait -PassThru
    $results += [PSCustomObject]@{
        Name = $t.Name
        ExitCode = $p.ExitCode
    }
    if ($p.ExitCode -ne 0) {
        Write-Host "<<< FAILED: $($t.Name) (exit $p.ExitCode)" -ForegroundColor Red
    } else {
        Write-Host "<<< PASSED: $($t.Name)" -ForegroundColor Green
    }
}

# 2. Python tests (only if python is available)
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Python Test Suites" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$python = (Get-Command python -ErrorAction SilentlyContinue)
if ($python) {
    Write-Host ""
    Write-Host ">>> Running: Python tests (Delta Encoder + Mouse/Keyboard + WGC)" -ForegroundColor Yellow
    Push-Location (Join-Path $ScriptDir 'agent')
    try {
        $p = Start-Process -FilePath 'python' -ArgumentList @('-m', 'unittest', 'tests.test_delta_encoder', 'tests.test_mouse_keyboard', 'tests.test_wgc', '-v') -NoNewWindow -Wait -PassThru
        $results += [PSCustomObject]@{
            Name = 'Python unittest (delta_encoder 12 + mouse_keyboard 51 + wgc 9 = 72 tests)'
            ExitCode = $p.ExitCode
        }
        if ($p.ExitCode -ne 0) {
            Write-Host "<<< FAILED: Python tests (exit $p.ExitCode)" -ForegroundColor Red
        } else {
            Write-Host "<<< PASSED: Python tests" -ForegroundColor Green
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Python not found, skipping Python tests" -ForegroundColor DarkYellow
    $results += [PSCustomObject]@{
        Name = 'Python tests (skipped: python not in PATH)'
        ExitCode = 0
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize Name, ExitCode

$failed = @($results | Where-Object { $_.ExitCode -ne 0 }).Count
if ($failed -eq 0) {
    Write-Host "All test suites PASSED!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failed test suite(s) FAILED" -ForegroundColor Red
    exit 1
}
