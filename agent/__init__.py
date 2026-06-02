"""Remote Control Agent package.

Two-process architecture (added 2026-06-02 to support capture in locked
Windows sessions, modeled after RustDesk / MeshCentral patterns):

  - agent.service: runs as SYSTEM in Session 0, owns WebSocket + spawns helper
  - agent.helper:  runs in user Session 1+, captures + injects input
  - agent.protocol: named-pipe IPC primitives
  - agent.capture: DXGI > mss > PIL.ImageGrab screen capture
  - agent.input_inject: pyautogui / ctypes mouse + keyboard

This __init__.py exists to make ``import agent; agent.<name>`` work the
same way it did when agent.py was a flat top-level module (before
commit 2281efc split it into a package). It does this by replacing this
module's class with a ModuleType subclass that forwards attribute
lookups to the agent.agent submodule.

Design notes (postmortem of the test_mouse_keyboard.py pre-existing
bugs that surfaced during WGC test wiring):

  * Availability flags (WIN32_AVAILABLE, MSS_AVAILABLE, ...) are
    computed once at agent.agent import time, when ``import win32api``
    either succeeds or fails for the live interpreter. In a test
    environment we pre-mock ``win32api`` etc. into sys.modules BEFORE
    agent.agent is loaded — but agent.agent IS already loaded by the
    time ``try_import_agent()`` runs. We therefore re-derive the flags
    dynamically from sys.modules on every package-level access and
    mirror the live value onto the submodule so that
    ``agent.agent.WIN32_AVAILABLE`` (read by handle_clipboard and
    friends via local name lookup) also reflects the mocked state.

  * A common test-isolation bug in this suite is forgetting to call
    ``_patch.stop()`` in tearDown. If we cached writes in
    ``self.__dict__`` like a normal module, a leaked mock would
    shadow the real function for the entire remainder of the run.
    Instead we *only* mirror writes to the submodule, so the
    canonical value lives there. The package's __dict__ is kept
    empty for non-dunder names so __getattr__ always sees the
    submodule's current state.

Run with:
  python -m agent --mode=service    # service mode
  python -m agent --mode=helper     # helper mode (auto-spawned by service)
"""
__version__ = '2.0.0'

import sys
from types import ModuleType


# When sys.modules has these (e.g. tests inject MagicMock), the
# corresponding *_AVAILABLE flag is True. We also flip the flag on
# the submodule so agent.py's local-name lookups see the live state.
_AVAILABILITY_DEPS = {
    'WIN32_AVAILABLE': ('win32api', 'win32clipboard', 'win32con', 'win32gui'),
    'PYAUTOGUI_AVAILABLE': ('pyautogui',),
    'MSS_AVAILABLE': ('mss',),
    'PSUTIL_AVAILABLE': ('psutil',),
    'WS_AVAILABLE': ('websocket',),
    'PYTHONCOM_AVAILABLE': ('pythoncom',),
}


class _PackageModule(ModuleType):
    """Module subclass that delegates every non-dunder attribute to
    the agent.agent submodule."""

    # Names whose dunder scope is reserved by the import system.
    _DUNDER = frozenset({
        '__path__', '__file__', '__loader__', '__spec__', '__name__',
        '__package__', '__cached__', '__builtins__',
    })

    def _resolve_sub(self):
        sub = sys.modules.get(f'{self.__name__}.agent')
        if sub is None:
            import importlib as _il
            sub = _il.import_module(f'{self.__name__}.agent')
        return sub

    def __getattr__(self, name: str):
        # Reject only dunders that are not in our reserved set; let
        # the rest fall through to a normal AttributeError after the
        # delegation chain below fails.
        if name in self._DUNDER:
            raise AttributeError(name)

        # 1. Dynamic availability flags.
        if name in _AVAILABILITY_DEPS:
            value = any(sys.modules.get(d) is not None for d in _AVAILABILITY_DEPS[name])
            sub = self._resolve_sub()
            cur = sub.__dict__.get(name)
            if cur is False:
                sub.__dict__[name] = value
            return value

        sub = self._resolve_sub()

        # 2. ``from agent import agent`` and bare ``agent.agent`` should
        # return the submodule itself.
        if name == 'agent':
            return sub

        # 3. Real definition on the submodule?
        if hasattr(sub, name):
            return getattr(sub, name)

        # 4. sys.modules fallback (e.g. ``agent.win32clipboard`` when
        # the test injected a MagicMock there before agent.agent
        # imported it for real).
        if name != self.__name__:
            mod = sys.modules.get(name)
            if mod is not None and mod is not self:
                # Cache on submodule so agent.py's local-name lookup
                # works (e.g. ``import win32clipboard`` at the top of
                # agent.agent binds ``win32clipboard`` on the submodule).
                cur = sub.__dict__.get(name)
                if cur is None:
                    try:
                        sub.__dict__[name] = mod
                    except (AttributeError, TypeError):
                        pass
                # And flip any flag whose availability depends on it.
                for flag, deps in _AVAILABILITY_DEPS.items():
                    if name in deps and sub.__dict__.get(flag) is False:
                        try:
                            sub.__dict__[flag] = True
                        except (AttributeError, TypeError):
                            pass
                return mod

        raise AttributeError(
            f"module {self.__name__!r} has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value):
        # We do NOT store non-dunder names in self.__dict__. The
        # canonical value lives in agent.agent's __dict__ so leaked
        # mocks (e.g. a tearDown that forgot to call _upload_p.stop())
        # get replaced as soon as the next patch.object sets the
        # original back.
        if name.startswith('__') and name.endswith('__'):
            super().__setattr__(name, value)
            return
        sub = sys.modules.get(f'{self.__name__}.agent')
        if sub is not None:
            try:
                setattr(sub, name, value)
            except (AttributeError, TypeError):
                pass

    def __delattr__(self, name: str):
        if name.startswith('__') and name.endswith('__'):
            super().__delattr__(name)
            return
        # Forward the delete to the submodule so the canonical value
        # is removed. This matches normal module semantics (a
        # ``del agent.X`` in user code should make ``agent.X`` look
        # unassigned).
        sub = self._resolve_sub()
        if hasattr(sub, name):
            delattr(sub, name)


# Replace this module's class so PEP 562 hooks take effect.
sys.modules[__name__].__class__ = _PackageModule
