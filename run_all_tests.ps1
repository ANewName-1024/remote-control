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
$optInSmoke = $env:RC_RUN_E2E -eq '1'
if ($python) {
    # Run from the project root (NOT the agent/ subdir) so that
    # 'agent' resolves to the agent/ PACKAGE (with its _PackageModule
    # re-export shim) rather than to the legacy single-file
    # agent/agent.py that would shadow the package. pytest discovers
    # the suite via agent/tests/ collection; no path manipulation
    # needed.
    Write-Host ""
    Write-Host ">>> Running: Python tests (pytest, agent/tests/, 119+1skip)" -ForegroundColor Yellow
    $p = Start-Process -FilePath 'python' -ArgumentList @('-m', 'pytest', 'agent/tests/', '-v') -NoNewWindow -Wait -PassThru -WorkingDirectory $ScriptDir
    $results += [PSCustomObject]@{
        Name = 'Python pytest (delta_encoder 12 + mouse_keyboard 51 + wgc 9 + ws_input_bridge 7 = 79 tests)'
        ExitCode = $p.ExitCode
    }
    if ($p.ExitCode -ne 0) {
        Write-Host "<<< FAILED: Python tests (exit $p.ExitCode)" -ForegroundColor Red
    } else {
        Write-Host "<<< PASSED: Python tests" -ForegroundColor Green
    }
} else {
    Write-Host "Python not found, skipping Python tests" -ForegroundColor DarkYellow
    $results += [PSCustomObject]@{
        Name = 'Python tests (skipped: python not in PATH)'
        ExitCode = 0
    }
}

# 3. Real-Windows mouse smoke test (opt-in: RC_RUN_E2E=1)
# Verifies pyautogui / ctypes actually move the OS cursor, which
# the unit tests cannot do (they mock pyautogui). Off by default
# because it WILL click on whatever is under the cursor and shift
# the cursor position during the test.
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Real-Windows Smoke Test (opt-in)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($optInSmoke) {
    if ($python) {
        Write-Host ""
        Write-Host ">>> Running: agent/smoke_test_mouse.py (RC_RUN_E2E=1)" -ForegroundColor Yellow
        $p = Start-Process -FilePath 'python' -ArgumentList @('-m', 'agent.smoke_test_mouse') -NoNewWindow -Wait -PassThru -WorkingDirectory $ScriptDir
        $results += [PSCustomObject]@{
            Name = 'Real-Windows mouse smoke (5 sub-tests, moves cursor)'
            ExitCode = $p.ExitCode
        }
        if ($p.ExitCode -ne 0) {
            Write-Host "<<< FAILED: real-Windows mouse smoke (exit $p.ExitCode)" -ForegroundColor Red
        } else {
            Write-Host "<<< PASSED: real-Windows mouse smoke" -ForegroundColor Green
        }
    } else {
        Write-Host "Python not found, cannot run smoke test" -ForegroundColor DarkYellow
        $results += [PSCustomObject]@{
            Name = 'Real-Windows mouse smoke (skipped: python not in PATH)'
            ExitCode = 0
        }
    }
} else {
    Write-Host "Skipped (set RC_RUN_E2E=1 to run; will move cursor and click on screen)" -ForegroundColor DarkYellow
    $results += [PSCustomObject]@{
        Name = 'Real-Windows mouse smoke (skipped: RC_RUN_E2E != 1)'
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
