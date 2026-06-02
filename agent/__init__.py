"""Remote Control Agent package.

Two-process architecture (added 2026-06-02 to support capture in locked
Windows sessions, modeled after RustDesk / MeshCentral patterns):

  - agent.service: runs as SYSTEM in Session 0, owns WebSocket + spawns helper
  - agent.helper:  runs in user Session 1+, captures + injects input
  - agent.protocol: named-pipe IPC primitives
  - agent.capture: DXGI > mss > PIL.ImageGrab screen capture
  - agent.input_inject: pyautogui / ctypes mouse + keyboard

Run with:
  python -m agent --mode=service    # service mode
  python -m agent --mode=helper     # helper mode (auto-spawned by service)
"""
__version__ = '2.0.0'
