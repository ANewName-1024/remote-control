"""Windows.Graphics.Capture (WGC) backend for the agent.

The only GDI-free capture method that works in a locked Windows session
(where BitBlt and DXGI Output Duplication are blocked by DWM).

Implementation strategy
=======================
This version uses the official pywinrt/winrt-python 3.2.1 interop helpers
instead of hand-rolled COM ctypes. The official API is both shorter and
more robust:

  - create_for_monitor(hmonitor)            -> GraphicsCaptureItem
  - create_direct3d11_device_from_dxgi_device(id3d11device*)
                                              -> IDirect3DDevice (winrt)
  - Direct3D11CaptureFramePool.create_free_threaded(...)
  - GraphicsCaptureSession.start_capture()
  - Direct3D11CaptureFramePool.try_get_next_frame()
      -> Direct3D11CaptureFrame.surface (IDirect3DSurface)
  - SoftwareBitmap.create_copy_from_surface_async(surface)
      -> SoftwareBitmap (CPU-readable)
  - bitmap.copy_to_buffer(buffer)            -> bytes

The previous hand-rolled version (D3D11CreateDevice + IGraphicsCaptureItemInterop
+ IID_IGraphicsCaptureItem wrap + ID3D11DeviceContext::CopyResource/Map/Unmap) is
obsolete. Kept the imports/availability flags so the rest of the agent can
import this module the same way.

Tested on Windows 11 22H2+. Requires Win10 1903 (build 18362) minimum.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Optional

import numpy as np

log = logging.getLogger('agent.wgc')

# ---------------------------------------------------------------------------
# Optional dependencies - module imports even if WGC pieces are missing.
# ---------------------------------------------------------------------------
try:
    import winrt.windows.graphics as wg
    import winrt.windows.graphics.capture as wgc_mod
    import winrt.windows.graphics.directx as gdx
    import winrt.windows.graphics.directx.direct3d11 as d3d_mod
    import winrt.windows.graphics.directx.direct3d11.interop as d3d_io
    import winrt.windows.graphics.capture.interop as cap_io
    import winrt.windows.graphics.imaging as img_mod
    import winrt.windows.storage.streams as streams_mod
    WINRT_AVAILABLE = True
except ImportError:                                # pragma: no cover
    WINRT_AVAILABLE = False

WGC_AVAILABLE = WINRT_AVAILABLE


# ---------------------------------------------------------------------------
# D3D11 device creation (ctypes — only this one ctypes call remains)
# ---------------------------------------------------------------------------
_D3D11_SDK_VERSION = 7
_D3D_DRIVER_TYPE_HARDWARE = 1
_D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
_HRESULT = ctypes.c_long


def _hresult_check(hr, op):
    if hr < 0:
        raise OSError(f'{op} failed: hr=0x{hr & 0xFFFFFFFF:08x}')


def _create_d3d11_device() -> ctypes.c_void_p:
    """Create an ID3D11Device* for HW rendering with BGRA support.

    Returns the raw ID3D11Device*. The caller is responsible for the
    reference count; we keep it alive by storing the c_void_p in the
    WgcCapture instance.
    """
    d3d11 = ctypes.windll.d3d11
    out_device = ctypes.c_void_p()
    out_context = ctypes.c_void_p()
    out_fl = ctypes.c_uint()
    D3D11CreateDevice = d3d11.D3D11CreateDevice
    D3D11CreateDevice.restype = _HRESULT
    hr = D3D11CreateDevice(
        None,                                   # adapter = default
        _D3D_DRIVER_TYPE_HARDWARE,
        None,                                   # software
        _D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        None,                                   # feature levels = default
        0,
        _D3D11_SDK_VERSION,
        ctypes.byref(out_device),
        ctypes.byref(out_fl),
        ctypes.byref(out_context),
    )
    _hresult_check(hr, 'D3D11CreateDevice')
    if not out_device.value:
        raise OSError('D3D11CreateDevice returned a NULL device')
    return out_device


def _get_primary_monitor_handle() -> int:
    user32 = ctypes.windll.user32
    MONITOR_DEFAULTTOPRIMARY = 0x1
    hwnd = user32.GetDesktopWindow()
    if not hwnd:
        raise OSError('GetDesktopWindow returned NULL')
    hmonitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTOPRIMARY)
    if not hmonitor:
        raise OSError('MonitorFromWindow returned NULL')
    return int(hmonitor)


# ---------------------------------------------------------------------------
# The high-level WgcCapture class
# ---------------------------------------------------------------------------
class WgcCapture:
    """Windows.Graphics.Capture capture target for the primary monitor.

    Lifecycle:
        cap = WgcCapture()
        frame = cap.grab()  # HxWx3 RGB uint8, or None if no frame yet
        cap.close()
    """

    def __init__(self):
        if not WGC_AVAILABLE:
            raise RuntimeError(
                'WGC unavailable: need winrt-Windows.Graphics + Capture + '
                'Capture.Interop + DirectX.Direct3D11 + Direct3D11.Interop + '
                'Imaging + Storage.Streams. Run: '
                'python -m pip install winrt-runtime winrt-Windows.Foundation '
                'winrt-Windows.Graphics winrt-Windows.Graphics.Capture '
                'winrt-Windows.Graphics.Capture.Interop '
                'winrt-Windows.Graphics.DirectX '
                'winrt-Windows.Graphics.DirectX.Direct3D11 '
                'winrt-Windows.Graphics.DirectX.Direct3D11.Interop '
                'winrt-Windows.Graphics.Imaging winrt-Windows.Storage '
                'winrt-Windows.Storage.Streams'
            )

        self._closed = False
        self._lock = threading.Lock()
        # 1. D3D11 device (HW, BGRA)
        self._d3d11_device_ptr = _create_d3d11_device()
        # 2. Wrap as winrt IDirect3DDevice via official interop helper
        self._d3d_device = d3d_io.create_direct3d11_device_from_dxgi_device(
            self._d3d11_device_ptr.value
        )
        # 3. Capture item for the primary monitor
        hmonitor = _get_primary_monitor_handle()
        self._item = cap_io.create_for_monitor(hmonitor)
        size = self._item.size
        self.width = int(size.width)
        self.height = int(size.height)
        # 4. FramePool (BGRA8, 2 buffered) + Session
        self._frame_pool = wgc_mod.Direct3D11CaptureFramePool.create_free_threaded(
            self._d3d_device,
            gdx.DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,
            2,
            size,
        )
        self._session = self._frame_pool.create_capture_session(self._item)
        try:
            self._session.is_cursor_capture_enabled = False
        except Exception:
            pass
        # 5. Start capture (frames arrive async into the frame pool)
        self._session.start_capture()
        log.info(f'WGC: started {self.width}x{self.height} capture on monitor {hmonitor:#x}')

    def grab(self) -> Optional[np.ndarray]:
        """Return a fresh RGB frame or None if no frame is ready yet."""
        if self._closed:
            return None
        with self._lock:
            frame = self._frame_pool.try_get_next_frame()
            if frame is None:
                return None
            try:
                return self._read_frame_to_numpy(frame)
            finally:
                frame.close()

    def _read_frame_to_numpy(self, frame) -> np.ndarray:
        """Copy frame.surface -> SoftwareBitmap -> bytes -> numpy RGB array.

        SoftwareBitmap.create_copy_from_surface_async does the GPU->CPU
        readback for us; we then copy the BGRA bytes into a numpy array
        and swap channels to RGB (the agent's frame contract).
        """
        bitmap = img_mod.SoftwareBitmap.create_copy_from_surface_async(
            frame.surface
        ).get()
        w, h = int(bitmap.pixel_width), int(bitmap.pixel_height)
        # Allocate a Windows.Storage.Streams.Buffer of exactly w*h*4 bytes
        ibuf = streams_mod.Buffer(w * h * 4)
        bitmap.copy_to_buffer(ibuf)
        # Convert IBuffer to bytes — winrt's IBuffer supports the
        # buffer protocol (PEP 3118) on the underlying memory.
        data = bytes(ibuf)
        # BGRA -> RGB. Match capture.py / mss backend contract (HxWx3 RGB).
        arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
        return arr[:, :, [2, 1, 0]].copy()

    def close(self):
        if self._closed:
            return
        self._closed = True
        for name in ('_session', '_frame_pool'):
            try:
                getattr(self, name).close()
            except Exception:
                pass
        # Release the D3D11 device (refcount; the winrt IDirect3DDevice
        # above also holds one).
        if self._d3d11_device_ptr and self._d3d11_device_ptr.value:
            try:
                ctypes.windll.d3d11.IUnknown_Release(self._d3d11_device_ptr.value)
            except Exception:
                pass
            self._d3d11_device_ptr = ctypes.c_void_p()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


__all__ = ['WgcCapture', 'WGC_AVAILABLE']
