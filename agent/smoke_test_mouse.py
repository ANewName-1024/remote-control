"""Real-Windows smoke test for mouse injection.

PURPOSE
=======
The unit tests in tests/ prove that pyautogui / ctypes are CALLED
with the right arguments. They cannot prove the OS actually moved
the cursor (mocked pyautogui lies about position()). This script
proves end-to-end mouse injection works on a real Windows desktop.

USAGE
=====
Run on the Windows host where the agent will be deployed, ideally
in the SAME user session the agent's helper process will run in.

    python -m agent.smoke_test_mouse
    # or:
    python agent\\smoke_test_mouse.py

It will:
  1. Record cursor start position
  2. Move the cursor to (200, 200)
  3. Read pyautogui.position() and compare
  4. Try a click
  5. Try a drag from (300, 300) to (500, 500)
  6. Report PASS / FAIL with the actual cursor positions

DO NOT run this on a server you don't have KVM access to: a failed
test will leave the cursor at a weird position and any click
during the test will register on whatever app happens to be
underneath. The script saves and restores the cursor position
on exit, so this is safe to run from a terminal, but don't run
it in a production user session you care about.

EXIT CODES
==========
  0  all sub-tests passed
  1  one or more sub-tests failed
  2  prerequisites not met (e.g. pyautogui not installed, no display)
"""
import os
import sys
import time

# Add agent/ to path so we can import input_inject
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def _fail(msg: str) -> None:
    print(f'  [FAIL] {msg}')


def _pass(msg: str) -> None:
    print(f'  [PASS] {msg}')


def _section(title: str) -> None:
    print()
    print('=' * 60)
    print(f'  {title}')
    print('=' * 60)


def main() -> int:
    if not HAS_PYAUTOGUI:
        print('FATAL: pyautogui not installed; cannot run on real Windows')
        print('       pip install pyautogui')
        return 2

    # Read screen size (this also implicitly checks we have a display)
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception as e:
        print(f'FATAL: cannot read screen size: {e}')
        print('       Are you running in a real interactive session?')
        return 2

    # Read starting cursor position so we can restore at exit
    try:
        start_x, start_y = pyautogui.position()
    except Exception as e:
        print(f'FATAL: cannot read cursor position: {e}')
        return 2

    print(f'Display: {screen_w}x{screen_h}')
    print(f'Cursor at start: ({start_x}, {start_y})')
    print('NOTE: cursor will be moved during tests and restored on exit.')

    # Target positions. Use the center-ish area to avoid hitting
    # taskbars / dock areas. (200, 200) and (500, 500) are well
    # inside a 1080p+ display.
    target_a = (min(200, screen_w - 1), min(200, screen_h - 1))
    target_b = (min(500, screen_w - 1), min(500, screen_h - 1))
    # 2 px tolerance matches agent/input_inject.py:verify_at()
    TOL = 2

    failures = 0

    try:
        # ---- 1. Move ----
        _section('Test 1: move cursor')
        pyautogui.moveTo(target_a[0], target_a[1], duration=0)
        time.sleep(0.05)  # pyautogui / SendInput are async
        actual = pyautogui.position()
        if abs(actual[0] - target_a[0]) <= TOL and abs(actual[1] - target_a[1]) <= TOL:
            _pass(f'cursor at {actual} (target {target_a})')
        else:
            _fail(f'cursor at {actual}, expected {target_a} (tolerance {TOL})')
            _fail('  -> SendInput likely failing. Causes:')
            _fail('     - Running in Session 0 (services)')
            _fail('     - UAC / different integrity level')
            _fail('     - Display locked or no input desktop')
            failures += 1

        # ---- 2. Move again to a different position ----
        _section('Test 2: move cursor to second position')
        pyautogui.moveTo(target_b[0], target_b[1], duration=0)
        time.sleep(0.05)
        actual = pyautogui.position()
        if abs(actual[0] - target_b[0]) <= TOL and abs(actual[1] - target_b[1]) <= TOL:
            _pass(f'cursor at {actual} (target {target_b})')
        else:
            _fail(f'cursor at {actual}, expected {target_b}')
            failures += 1

        # ---- 3. Click ----
        # Clicking is hard to verify in isolation, but we can at
        # least confirm the cursor stays put and pyautogui doesn't
        # raise. The actual "did a window get the click" question
        # is unanswerable in a headless test.
        _section('Test 3: click (cursor should stay put, no exception)')
        before = pyautogui.position()
        try:
            pyautogui.click()
            time.sleep(0.05)
            after = pyautogui.position()
            if before == after:
                _pass(f'click() returned cleanly, cursor stable at {after}')
            else:
                # On some systems, click() can move the cursor by 1
                # pixel. Tolerate that.
                if abs(before[0] - after[0]) <= TOL and abs(before[1] - after[1]) <= TOL:
                    _pass(f'click() returned cleanly, cursor moved {abs(before[0]-after[0]), abs(before[1]-after[1])}px (within tolerance)')
                else:
                    _fail(f'click() shifted cursor: {before} -> {after}')
                    failures += 1
        except Exception as e:
            _fail(f'click() raised: {e}')
            failures += 1

        # ---- 4. Drag ----
        # Move to a clean spot, then drag to a slightly different
        # spot. Verify cursor ends at the destination.
        _section('Test 4: drag from A to B (cursor should end at B)')
        start = (min(100, screen_w - 1), min(100, screen_h - 1))
        end = (min(700, screen_w - 1), min(700, screen_h - 1))
        try:
            pyautogui.moveTo(start[0], start[1], duration=0)
            time.sleep(0.05)
            # dragTo with button held = click + moveTo + release.
            # duration > 0 makes pyautogui step the move, but
            # SendInput does the actual work. We give it a small
            # but non-zero duration so the test feels real.
            pyautogui.dragTo(end[0], end[1], duration=0.2, button='left')
            time.sleep(0.1)
            actual = pyautogui.position()
            if abs(actual[0] - end[0]) <= TOL and abs(actual[1] - end[1]) <= TOL:
                _pass(f'drag completed, cursor at {actual} (target {end})')
            else:
                _fail(f'drag ended at {actual}, expected {end}')
                failures += 1
        except Exception as e:
            _fail(f'dragTo() raised: {e}')
            failures += 1

        # ---- 5. verify_at() helper test ----
        # This is the same code path the agent runs in production.
        # If THIS fails, your helper process will silently fail
        # to inject mouse on the host.
        _section('Test 5: agent.input_inject.verify_at() (the production guard)')
        try:
            from agent.input_inject import verify_at, PYAUTOGUI_AVAILABLE
            if not PYAUTOGUI_AVAILABLE:
                _fail('agent.input_inject reports PYAUTOGUI_AVAILABLE=False')
                failures += 1
            else:
                # Move to known target, then verify
                pyautogui.moveTo(target_a[0], target_a[1], duration=0)
                time.sleep(0.05)
                if verify_at(target_a[0], target_a[1]):
                    _pass(f'verify_at({target_a}) returned True (cursor matches)')
                else:
                    _fail(f'verify_at({target_a}) returned False (cursor mismatch)')
                    failures += 1
                # And the negative case
                bad = (target_a[0] + 9999, target_a[1] + 9999)
                if not verify_at(bad[0], bad[1]):
                    _pass(f'verify_at({bad}) correctly returned False (out of range)')
                else:
                    _fail(f'verify_at({bad}) returned True, expected False')
                    failures += 1
        except Exception as e:
            _fail(f'verify_at() raised: {e}')
            failures += 1

    finally:
        # Always restore the cursor. The test fails are useless
        # if the user is left with their cursor at (700, 700) and
        # their terminal half-typed.
        _section('Cleanup')
        try:
            pyautogui.moveTo(start_x, start_y, duration=0)
            time.sleep(0.05)
            cur = pyautogui.position()
            if cur == (start_x, start_y):
                _pass(f'cursor restored to start ({start_x}, {start_y})')
            else:
                _fail(f'cursor at {cur}, expected ({start_x}, {start_y})')
        except Exception as e:
            _fail(f'could not restore cursor: {e}')

    _section('Summary')
    if failures == 0:
        print('  ALL TESTS PASSED — mouse injection works on this host.')
        print('  Your agent helper process should also be able to inject mouse.')
        return 0
    else:
        print(f'  {failures} TEST(S) FAILED — see [FAIL] lines above for diagnosis.')
        print('  Common fixes:')
        print('    - Run the agent helper in the active user session (not Session 0)')
        print('    - Run as the same user that owns the desktop')
        print('    - Make sure UAC is not blocking the injection')
        print('    - Make sure the display is not locked')
        return 1


if __name__ == '__main__':
    sys.exit(main())
