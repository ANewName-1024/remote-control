"""Screen capture interface with four backends, in priority order:

  1. WGC    (Windows.Graphics.Capture, UWP) - works in LOCKED sessions,
                                              Win10 1903+ / Win11
  2. dxcam  (DXGI Desktop Duplication)      - works in unlocked session,
                                              Win10+
  3. mss    (Win32 GDI)                     - works when user logged in
  4. PIL.ImageGrab (Win32 GDI)              - last-ditch fallback

Returns frames as numpy.uint8 array (H, W, 3) in RGB format.
The helper runs in the user's interactive session, so WGC is preferred
when available because it can capture even when the workstation is
locked (where DWM blocks BitBlt / DXGI).
"""
import logging
from typing import Optional, Tuple

import numpy as np

# Backend availability flags
try:
    import dxcam
    DXCAM_AVAILABLE = True
except ImportError:
    DXCAM_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# WinRT / WGC requires:
#   pip install winrt-runtime winrt-Windows.Graphics.Capture
#   pip install winrt-Windows.Foundation winrt-Windows.UI.Composition
# and a modern Direct3D11 binding. These are heavy deps so we only
# declare WGC as available if all pieces are importable.
WGC_AVAILABLE = False
try:
    import winrt  # type: ignore  # noqa: F401
    import winrt.windows.graphics.capture as wgc  # type: ignore
    import winrt.windows.graphics.directx.direct3d11 as d3d11  # type: ignore
    WGC_AVAILABLE = True
except ImportError:
    pass


log = logging.getLogger('agent.capture')


class ScreenCapture:
    """Multi-backend screen capture for the user session.

    The instance is bound to one backend; the backend is selected at init
    and never re-tried at runtime (avoids hot-loop overhead).
    """

    def __init__(self):
        self.backend: str = 'none'
        self.width: int = 0
        self.height: int = 0
        # backend-specific resources
        self._wgc_frame_pool = None
        self._wgc_session = None
        self._wgc_item = None
        self._wgc_d3d_device = None
        self._cam: Optional['dxcam.DXCamera'] = None
        self._sct = None
        self._init_backend()

    def _init_backend(self):
        # 1. WGC (preferred for locked sessions)
        if WGC_AVAILABLE:
            try:
                self._init_wgc()
                self.backend = 'wgc'
                log.info(f'capture: WGC UWP backend ({self.width}x{self.height})')
                return
            except Exception as e:
                log.debug(f'WGC init failed: {e}')

        if DXCAM_AVAILABLE:
            try:
                # output_idx=0 => primary display
                # output_color='RGB' => dxcam returns RGB array directly
                self._cam = dxcam.create(output_idx=0, output_color='RGB')
                if self._cam is not None:
                    self.width  = self._cam.width
                    self.height = self._cam.height
                    self.backend = 'dxcam'
                    log.info(f'capture: DXGI backend ({self.width}x{self.height})')
                    return
            except Exception as e:
                log.debug(f'dxcam init failed: {e}')

        if MSS_AVAILABLE:
            try:
                self._sct = mss.mss()
                mon = self._sct.monitors[0]
                self.width  = mon['width']
                self.height = mon['height']
                self.backend = 'mss'
                log.info(f'capture: mss backend ({self.width}x{self.height})')
                return
            except Exception as e:
                log.debug(f'mss init failed: {e}')

        if PIL_AVAILABLE:
            try:
                img = ImageGrab.grab()
                self.width, self.height = img.size
                self.backend = 'pil'
                log.info(f'capture: PIL.ImageGrab fallback ({self.width}x{self.height})')
                return
            except Exception as e:
                log.debug(f'PIL.ImageGrab init failed: {e}')

        raise RuntimeError('no screen capture backend available (install winrt+dx11, dxcam, mss, or Pillow)')

    def _init_wgc(self):
        """Initialize Windows.Graphics.Capture for the primary monitor.

        Note: a full implementation requires Direct3D11 device creation
        via ctypes + d3d11.dll. This skeleton provides the wiring; the
        d3d11 device init is left as a future PR (requires ~80 lines of
        ctypes boilerplate for CreateDevice + QueryInterface).
        """
        # TODO(2.1+): implement d3d11 device init via ctypes
        #   d3d11.CreateDevice(None, 0, 0, 0, None, 0, D3D_DRIVER_TYPE_HARDWARE)
        #   + QI for ID3D11Device5 (needed for CreateDirect3D11SurfaceFromHandle)
        raise NotImplementedError('WGC backend skeleton only; full implementation in 2.1+')

    def grab(self) -> Optional[np.ndarray]:
        """Grab a single frame. Returns HxWx3 RGB uint8 array, or None on failure."""
        try:
            if self.backend == 'wgc':
                return self._grab_wgc()
            if self.backend == 'dxcam':
                frame = self._cam.grab()
                if frame is None:
                    return None
                return frame  # already RGB

            if self.backend == 'mss':
                mon = self._sct.monitors[0]
                shot = self._sct.grab(mon)
                # shot.bgra is BGRA bytes; drop alpha and swap to RGB
                arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
                return arr[:, :, [2, 1, 0]]

            if self.backend == 'pil':
                img = ImageGrab.grab()
                return np.array(img.convert('RGB'))

        except Exception as e:
            log.warning(f'grab failed ({self.backend}): {e}')
            return None

        return None

    def _grab_wgc(self) -> Optional[np.ndarray]:
        """TODO(2.1+): map the latest Direct3D11CaptureFrame to a numpy
        array. Requires DirectX11 staging texture readback."""
        raise NotImplementedError('WGC grab skeleton only')

    def close(self):
        try:
            if self._cam is not None:
                self._cam.release()
        except Exception:
            pass
        try:
            if self._sct is not None:
                self._sct.close()
        except Exception:
            pass
        try:
            if self._wgc_session is not None:
                self._wgc_session.close()
        except Exception:
            pass
        try:
            if self._wgc_frame_pool is not None:
                self._wgc_frame_pool.close()
        except Exception:
            pass

    def status(self) -> dict:
        return {
            'backend': self.backend,
            'width':   self.width,
            'height':  self.height,
            'wgc_available':     WGC_AVAILABLE,
            'dxcam_available':   DXCAM_AVAILABLE,
            'mss_available':     MSS_AVAILABLE,
            'pil_available':     PIL_AVAILABLE,
        }
