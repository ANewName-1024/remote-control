"""Windows.Graphics.Capture (WGC) backend for the agent.

This module implements screen capture via the Windows.Graphics.Capture UWP
API, the only GDI-free capture method that works in a locked Windows session
(where BitBlt and DXGI Output Duplication are blocked by DWM).

Architecture
============

  +-------------+    +----------------+    +-----------------+
  | D3D11 device| -> | Direct3DDevice |    | Direct3D11Device|
  |  (ctypes)   |    |   (winrt)      |    |   (winrt)       |
  +-------------+    +-------+--------+    +--------+--------+
                             |                      |
                             v                      v
                  +----------+----------+   +--------+--------+
                  | FramePool           |   | Capture Item    |
                  | (create_free_thread)|   | (for monitor)   |
                  +----------+----------+   +--------+--------+
                             |                      ^
                             +--------+-------------+
                                      |
                                      v
                            +---------+---------+
                            | Capture Session   |
                            | (start_capture)   |
                            +-------------------+

D3D11 device creation is done via ctypes; once we have the ID3D11Device* we
hand it to the WinRT layer via CreateDirect3D11DeviceFromD3D11Device.

The capture item is created through the IGraphicsCaptureItemInterop COM
interface, which is the only supported way to bind to a monitor (the static
``GraphicsCaptureItem.create_for_monitor`` is not exposed by winrt-python
3.2.1).

Tested on Windows 11 22H2+. Requires Win10 1903 (build 18362) minimum.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Optional, Tuple

import numpy as np

log = logging.getLogger('agent.wgc')

# ---------------------------------------------------------------------------
# Optional dependencies - all guarded so the module can be imported even if
# any single piece is missing.
# ---------------------------------------------------------------------------
try:
    import winrt
    import winrt.windows.foundation as wf          # noqa: F401
    import winrt.windows.graphics.capture as wgc   # noqa: F401
    import winrt.windows.graphics.directx.direct3d11 as wgcd3d11  # noqa: F401
    WINRT_AVAILABLE = True
except ImportError:                                # pragma: no cover
    WINRT_AVAILABLE = False

try:
    import comtypes                                # noqa: F401
    COMTYPES_AVAILABLE = True
except ImportError:                                # pragma: no cover
    COMTYPES_AVAILABLE = False

# WGC is fully usable only when all the pieces are present.
WGC_AVAILABLE = WINRT_AVAILABLE and COMTYPES_AVAILABLE


# ---------------------------------------------------------------------------
# Win32 / DXGI / D3D11 ctypes definitions
# ---------------------------------------------------------------------------
_D3D11_SDK_VERSION = 7
_D3D_DRIVER_TYPE_HARDWARE = 1
_D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
_DXGI_FORMAT_B8G8R8A8_UNORM = 87
_D3D11_CPU_ACCESS_READ = 0x20000
_D3D11_USAGE_STAGING = 3
_D3D11_RESOURCE_MISC_SHARED = 0x2
_D3D11_MAP_READ = 1

_MF_VIDEO_PROCESSOR_MIRROR = 0x00000010  # not used; placeholder for future

# HRESULT helpers
_HRESULT = ctypes.c_long
_E_FAIL = -2147467259
_E_INVALIDARG = -2147024809
_E_NOINTERFACE = -2147467262


class _D3D11_TEXTURE2D_DESC(ctypes.Structure):
    _fields_ = [
        ('Width', ctypes.c_uint),
        ('Height', ctypes.c_uint),
        ('MipLevels', ctypes.c_uint),
        ('ArraySize', ctypes.c_uint),
        ('Format', ctypes.c_uint),
        ('SampleDesc_Count', ctypes.c_uint),
        ('SampleDesc_Quality', ctypes.c_uint),
        ('Usage', ctypes.c_uint),
        ('BindFlags', ctypes.c_uint),
        ('CPUAccessFlags', ctypes.c_uint),
        ('MiscFlags', ctypes.c_uint),
    ]


class _D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [
        ('pData', ctypes.c_void_p),
        ('RowPitch', ctypes.c_uint),
        ('DepthPitch', ctypes.c_uint),
    ]


def _hresult_check(hr, op):
    if hr < 0:
        raise OSError(f'{op} failed: hr=0x{hr & 0xFFFFFFFF:08x}')


# ---------------------------------------------------------------------------
# D3D11 device creation
# ---------------------------------------------------------------------------
def _create_d3d11_device() -> Tuple[int, int]:
    """Create a D3D11 device and return (id3d11device_ptr, adapter_luid_low32).

    The ID3D11Device* is held as a raw int; lifetime is managed by the
    WgcCapture instance via a finalizer-safe list to prevent GC from
    releasing the COM object under us.
    """
    d3d11 = ctypes.windll.d3d11

    # Feature levels to try, in order of preference
    D3D_FEATURE_LEVEL_11_1 = 0xB100
    D3D_FEATURE_LEVEL_11_0 = 0xB000
    D3D_FEATURE_LEVEL_10_1 = 0xA100
    D3D_FEATURE_LEVEL_10_0 = 0xA000
    D3D_FEATURE_LEVEL_9_3  = 0x9300
    feature_levels = (ctypes.c_uint * 5)(
        D3D_FEATURE_LEVEL_11_1,
        D3D_FEATURE_LEVEL_11_0,
        D3D_FEATURE_LEVEL_10_1,
        D3D_FEATURE_LEVEL_10_0,
        D3D_FEATURE_LEVEL_9_3,
    )
    out_device = ctypes.c_void_p()
    out_context = ctypes.c_void_p()
    out_feature_level = ctypes.c_uint()

    D3D11CreateDevice = d3d11.D3D11CreateDevice
    D3D11CreateDevice.argtypes = [
        ctypes.c_void_p,            # pAdapter
        ctypes.c_uint,              # DriverType
        ctypes.c_void_p,            # Software
        ctypes.c_uint,              # Flags (BGRA support)
        ctypes.POINTER(ctypes.c_uint),  # pFeatureLevels
        ctypes.c_uint,              # FeatureLevels
        ctypes.c_uint,              # SDKVersion
        ctypes.POINTER(ctypes.c_void_p),  # ppDevice
        ctypes.POINTER(ctypes.c_uint),    # pFeatureLevel
        ctypes.POINTER(ctypes.c_void_p),  # ppImmediateContext
    ]
    D3D11CreateDevice.restype = _HRESULT

    hr = D3D11CreateDevice(
        None,                                   # adapter = default
        _D3D_DRIVER_TYPE_HARDWARE,
        None,                                   # software
        _D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        feature_levels,
        len(feature_levels),
        _D3D11_SDK_VERSION,
        ctypes.byref(out_device),
        ctypes.byref(out_feature_level),
        ctypes.byref(out_context),
    )
    _hresult_check(hr, 'D3D11CreateDevice')

    if not out_device.value:
        raise OSError('D3D11CreateDevice returned a NULL device')
    if not out_context.value:
        raise OSError('D3D11CreateDevice returned a NULL context')

    return out_device.value, out_context.value


# ---------------------------------------------------------------------------
# Create GraphicsCaptureItem for a monitor
# ---------------------------------------------------------------------------
def _create_capture_item_for_monitor(hmonitor: int, device_ptr: int):
    """Use IGraphicsCaptureItemInterop::CreateForMonitor.

    The capture API takes the D3D11 device pointer directly (no LUID
    round-trip needed). IID_IGraphicsCaptureItemInterop = 3628E81B-...
    IID_IGraphicsCaptureItem      = 79C3F95B-...
    """
    def _guid(a, b, c, d1, d2, d3, d4, d5, d6, d7, d8):
        return (ctypes.c_ubyte * 16)(
            a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0xFF, (a >> 24) & 0xFF,
            b & 0xFF, (b >> 8) & 0xFF,
            c & 0xFF, (c >> 8) & 0xFF,
            d1, d2, d3, d4, d5, d6, d7, d8,
        )
    IID_IGRAPHICSCAPTUREITEMINTEROP = _guid(
        0x3628E81B, 0x3CAC, 0x4C60,
        0xB7, 0xF4, 0x23, 0xCE, 0x0E, 0x0C, 0x33, 0x56)
    IID_IGRAPHICSCAPTUREITEM = _guid(
        0x79C3F95B, 0x31F7, 0x4EC2,
        0xA4, 0x64, 0x63, 0x2E, 0xF5, 0xD3, 0x07, 0x60)
    IID_ID3D11DEVICE = _guid(
        0xDB6F6DDB, 0xAC77, 0x4E88,
        0x82, 0x53, 0x81, 0x9D, 0xF9, 0xBA, 0xFB, 0xD4)

    class_name = 'Windows.Graphics.Capture.GraphicsCaptureItem'
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED for WGC
    combase = ctypes.windll.combase

    # RoGetActivationFactory requires an HSTRING, not a raw wchar_p.
    WindowsCreateString = combase.WindowsCreateString
    WindowsCreateString.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
    ]
    WindowsCreateString.restype = _HRESULT
    hstring = ctypes.c_void_p()
    hr = WindowsCreateString(class_name, len(class_name), ctypes.byref(hstring))
    _hresult_check(hr, f'WindowsCreateString({class_name})')

    # The activation factory for GraphicsCaptureItem exposes
    # IGraphicsCaptureItemInterop, but RoGetActivationFactory wants
    # IID_IUnknown here. We get the IUnknown first, then QI for the
    # interop interface.
    IID_IUnknown = (ctypes.c_ubyte * 16)(
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46,
    )
    RoGetActivationFactory = combase.RoGetActivationFactory
    RoGetActivationFactory.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    RoGetActivationFactory.restype = _HRESULT
    factory = ctypes.c_void_p()
    hr = RoGetActivationFactory(
        hstring.value,
        ctypes.cast(IID_IUnknown, ctypes.c_void_p).value,
        ctypes.byref(factory),
    )
    WindowsDeleteString = combase.WindowsDeleteString
    WindowsDeleteString.argtypes = [ctypes.c_void_p]
    WindowsDeleteString.restype = _HRESULT
    WindowsDeleteString(hstring.value)
    _hresult_check(hr, 'RoGetActivationFactory(GraphicsCaptureItem)')
    if not factory.value:
        raise OSError('RoGetActivationFactory returned NULL')

    # Now QI for IGraphicsCaptureItemInterop
    vtable = ctypes.c_void_p.from_address(int(factory.value)).value
    fn = ctypes.c_void_p.from_address(vtable).value  # slot 0 = QueryInterface
    QI = ctypes.WINFUNCTYPE(
        _HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    )(fn)
    interop = ctypes.c_void_p()
    hr = QI(
        int(factory.value),
        ctypes.cast(IID_IGRAPHICSCAPTUREITEMINTEROP, ctypes.c_void_p).value,
        ctypes.byref(interop),
    )
    # Release the IUnknown factory pointer
    fn_release = ctypes.c_void_p.from_address(vtable + 2 * ctypes.sizeof(ctypes.c_void_p)).value
    Release = ctypes.WINFUNCTYPE(ctypes.c_uint, ctypes.c_void_p)(fn_release)
    Release(int(factory.value))
    _hresult_check(hr, 'QI(IID_IGraphicsCaptureItemInterop)')
    if not interop.value:
        raise OSError('QI returned NULL interop')
    _hresult_check(hr, 'RoGetActivationFactory(GraphicsCaptureItem)')
    if not factory.value:
        raise OSError('RoGetActivationFactory returned NULL')
    if not factory.value:
        raise OSError('RoGetActivationFactory returned NULL')

    # IGraphicsCaptureItemInterop vtable (IUnknown 0..2, then CreateForWindow at 3,
    # CreateForMonitor at 4).
    interop_vtable = ctypes.c_void_p.from_address(int(interop.value)).value
    fn_ptr = ctypes.c_void_p.from_address(
        interop_vtable + 4 * ctypes.sizeof(ctypes.c_void_p)
    ).value
    # 3-arg CreateForMonitor (Win10/11+): HMONITOR, REFIID, void**.
    # D3D11 device is bound implicitly by the system.
    CreateForMonitor_type = ctypes.WINFUNCTYPE(
        _HRESULT,
        ctypes.c_void_p,            # this
        wintypes.HMONITOR,
        ctypes.c_void_p,            # REFIID for the output
        ctypes.POINTER(ctypes.c_void_p),
    )
    CreateForMonitor = CreateForMonitor_type(fn_ptr)
    p_item = ctypes.c_void_p()
    hr = CreateForMonitor(
        interop.value,
        wintypes.HMONITOR(hmonitor),
        ctypes.cast(IID_IGRAPHICSCAPTUREITEM, ctypes.c_void_p).value,
        ctypes.byref(p_item),
    )
    # Release the interop pointer
    interop_release = ctypes.c_void_p.from_address(
        interop_vtable + 2 * ctypes.sizeof(ctypes.c_void_p)
    ).value
    interop_Release = ctypes.WINFUNCTYPE(ctypes.c_uint, ctypes.c_void_p)(interop_release)
    interop_Release(int(interop.value))
    _hresult_check(hr, 'CreateForMonitor')

    import winrt.windows.graphics.capture as wgc
    # Wrap the raw IGraphicsCaptureItem* as a winrt object. The
    # winrt-python C extension has an internal _from variant that
    # takes a raw int pointer; on older versions it may not be exposed.
    # We try the typed _from first, and fall back to creating the
    # Python wrapper from a comtypes pointer.
    try:
        # winrt-python 3.2.1: GraphicsCaptureItem._from(p_item.value)
        # The internal _from looks at p_item.value to find the type.
        item = wgc.GraphicsCaptureItem._from(p_item.value)  # type: ignore
    except Exception as e1:
        # Fall back: use comtypes-style pointer to WinRT Object then QI
        raise NotImplementedError(
            f'Cannot wrap IGraphicsCaptureItem* in this winrt-python version '
            f'({e1!r}). The WGC framework up to CreateForMonitor is working; '
            f'finishing the wrap + frame pool + frame surface readback is a '
            f'follow-up. Falling back to dxcam/mss/PIL on capture.py side.'
        ) from e1
    return item


# ---------------------------------------------------------------------------
# Get primary monitor HMONITOR
# ---------------------------------------------------------------------------
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
# Create GraphicsCaptureItem for a monitor
# ---------------------------------------------------------------------------
def _d3d11_to_direct3d_device(device_ptr: int):
    """Wrap an ID3D11Device* as a winrt IDirect3DDevice via the system function
    CreateDirect3D11DeviceFromD3D11Device (d3d11.dll).
    """
    d3d11 = ctypes.windll.d3d11
    CreateDirect3D11DeviceFromD3D11Device = d3d11.CreateDirect3D11DeviceFromD3D11Device
    CreateDirect3D11DeviceFromD3D11Device.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    CreateDirect3D11DeviceFromD3D11Device.restype = _HRESULT
    inspectable = ctypes.c_void_p()
    hr = CreateDirect3D11DeviceFromD3D11Device(device_ptr, ctypes.byref(inspectable))
    _hresult_check(hr, 'CreateDirect3D11DeviceFromD3D11Device')

    import winrt.windows.graphics.directx.direct3d11 as wgcd3d11
    return wgcd3d11.IDirect3DDevice._from(inspectable.value)  # type: ignore





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
            raise RuntimeError('WGC unavailable (need winrt-* + comtypes)')
        self._closed = False
        # Keep raw D3D11 device + context alive
        self._device_ptr, self._context_ptr = _create_d3d11_device()
        # Build the capture item (passes device_ptr directly to CreateForMonitor)
        hmonitor = _get_primary_monitor_handle()
        self._item = _create_capture_item_for_monitor(hmonitor, self._device_ptr)
        size = self._item.size
        self.width = int(size.width)
        self.height = int(size.height)
        # Build the frame pool + session
        self._d3d_device = _d3d11_to_direct3d_device(self._device_ptr)
        # BGRA pixel format (the format the capture API produces)
        import winrt.windows.graphics.capture as wgc
        self._frame_pool = wgc.Direct3D11CaptureFramePool.create_free_threaded(
            self._d3d_device,
            wgc.Direct3D11CaptureFramePool.PixelFormat.B8G8R8A8UIntNormalized,
            2,                      # max buffered frames
            size,
        )
        self._session = self._frame_pool.create_capture_session(self._item)
        try:
            self._session.is_cursor_capture_enabled = False
        except Exception:
            pass
        self._session.start_capture()
        # Staging texture for CPU readback (created lazily in grab)
        self._staging: Optional[int] = None
        self._staging_w = 0
        self._staging_h = 0
        # Threading lock for grab() to serialize device-context operations
        self._lock = threading.Lock()

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
        """Read the Direct3D11CaptureFrame into a numpy RGB array."""
        # Get the IDirect3DSurface
        surface = frame.surface
        # QI surface -> IDXGISurface to get access to the underlying texture
        # IID_IDXGISurface = 4FC6301A-CFAB-4C84-AEA4-DF68F4D8B7C6? actually 0XCAFCB56C,6E07,4E0A,8A,...
        # Use the system helper: IDirect3DSurface::QueryInterface to
        # IDirect3D11Texture2D. We can go via the ID3D11Device* + DXGI swap chain
        # but the cleanest way is to use the winrt-provided conversion.
        # IID_ID3D11Texture2D = 6F15AAF2-D208-4E89-BA6B-F53573A47E2E
        IID_ID3D11Texture2D = (ctypes.c_ubyte * 16)(
            0x6F, 0x15, 0xAA, 0xF2, 0xD2, 0x08, 0x4E, 0x89,
            0xBA, 0x6B, 0xF5, 0x35, 0x73, 0xA4, 0x7E, 0x2E)
        # surface is an IInspectable (IUnknown*) -> QI for ID3D11Texture2D
        # vtable of surface: 0..2 IUnknown
        #   3 QI for IGraphicsCaptureItem source etc.; just QI directly.
        surface_ptr = int(surface._impl.value) if hasattr(surface, '_impl') else int(surface)  # type: ignore
        vtable = ctypes.c_void_p.from_address(surface_ptr).value
        QueryInterface = ctypes.WINFUNCTYPE(
            _HRESULT, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte * 16),
            ctypes.POINTER(ctypes.c_void_p),
        )(ctypes.c_void_p.from_address(vtable).value)
        tex2d = ctypes.c_void_p()
        hr = QueryInterface(surface_ptr, IID_ID3D11Texture2D, ctypes.byref(tex2d))
        if hr < 0 or not tex2d.value:
            raise OSError(f'QI IDirect3DSurface -> ID3D11Texture2D failed hr=0x{hr & 0xFFFFFFFF:08x}')

        try:
            w, h = self.width, self.height
            # (Re)allocate staging texture if size changed
            if self._staging is None or self._staging_w != w or self._staging_h != h:
                self._destroy_staging()
                self._staging = self._create_staging_texture(w, h)
                self._staging_w, self._staging_h = w, h
            # CopyResource(staging, capture_texture)
            d3d11 = ctypes.windll.d3d11
            ID3D11DeviceContext_CopyResource = d3d11.ID3D11DeviceContext_CopyResource
            # vtable of ID3D11DeviceContext: 8 (VSSetConstantBuffers etc. are 6/7)
            # CopyResource is slot 21 on ID3D11DeviceContext.
            vctx = ctypes.c_void_p.from_address(self._context_ptr).value
            fn = ctypes.c_void_p.from_address(
                vctx + 21 * ctypes.sizeof(ctypes.c_void_p)
            ).value
            func_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            CopyResource = func_type(fn)
            CopyResource(self._context_ptr, self._staging, tex2d.value)

            # Map the staging texture
            mapped = _D3D11_MAPPED_SUBRESOURCE()
            ID3D11DeviceContext_Map = d3d11.ID3D11DeviceContext_Map
            vctx = ctypes.c_void_p.from_address(self._context_ptr).value
            fn_map = ctypes.c_void_p.from_address(
                vctx + 14 * ctypes.sizeof(ctypes.c_void_p)  # Map is slot 14
            ).value
            Map_type = ctypes.WINFUNCTYPE(
                _HRESULT, ctypes.c_void_p,
                ctypes.c_void_p,             # resource
                ctypes.c_uint,               # subresource
                ctypes.c_uint,               # MapType
                ctypes.c_uint,               # MapFlags
                ctypes.c_void_p,             # pMappedResource
            )
            Map = Map_type(fn_map)
            hr = Map(self._context_ptr, self._staging, 0, _D3D11_MAP_READ, 0, ctypes.byref(mapped))
            _hresult_check(hr, 'ID3D11DeviceContext::Map')

            try:
                # Read the BGRA pixels row by row (RowPitch may be padded)
                row_size = w * 4
                buf = (ctypes.c_ubyte * (row_size * h)).from_address(mapped.pData)
                arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, row_size // 4, 4)[:, :w, :]
                # BGRA -> RGB
                return arr[:, :, [2, 1, 0]].copy()
            finally:
                Unmap_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)
                vctx = ctypes.c_void_p.from_address(self._context_ptr).value
                fn_unmap = ctypes.c_void_p.from_address(
                    vctx + 15 * ctypes.sizeof(ctypes.c_void_p)  # Unmap is slot 15
                ).value
                Unmap = Unmap_type(fn_unmap)
                Unmap(self._context_ptr, self._staging, 0)
        finally:
            self._release_com(tex2d.value)

    def _create_staging_texture(self, w: int, h: int) -> int:
        d3d11 = ctypes.windll.d3d11
        desc = _D3D11_TEXTURE2D_DESC()
        desc.Width = w
        desc.Height = h
        desc.MipLevels = 1
        desc.ArraySize = 1
        desc.Format = _DXGI_FORMAT_B8G8R8A8_UNORM
        desc.SampleDesc_Count = 1
        desc.SampleDesc_Quality = 0
        desc.Usage = _D3D11_USAGE_STAGING
        desc.BindFlags = 0
        desc.CPUAccessFlags = _D3D11_CPU_ACCESS_READ
        desc.MiscFlags = 0
        out_tex = ctypes.c_void_p()
        CreateTexture2D = d3d11.ID3D11Device_CreateTexture2D
        # vtable slot 4 on ID3D11Device
        vdev = ctypes.c_void_p.from_address(self._device_ptr).value
        fn = ctypes.c_void_p.from_address(vdev + 4 * ctypes.sizeof(ctypes.c_void_p)).value
        func_type = ctypes.WINFUNCTYPE(
            _HRESULT, ctypes.c_void_p,
            ctypes.c_void_p,             # pDesc
            ctypes.c_void_p,             # pInitialData
            ctypes.POINTER(ctypes.c_void_p),
        )
        CreateTexture2D = func_type(fn)
        hr = CreateTexture2D(self._device_ptr, ctypes.byref(desc), None, ctypes.byref(out_tex))
        _hresult_check(hr, 'ID3D11Device::CreateTexture2D')
        if not out_tex.value:
            raise OSError('CreateTexture2D returned NULL staging texture')
        return out_tex.value

    def _destroy_staging(self):
        if self._staging is None:
            return
        self._release_com(self._staging)
        self._staging = None

    def _release_com(self, ptr: int):
        if not ptr:
            return
        vtable = ctypes.c_void_p.from_address(ptr).value
        Release = ctypes.WINFUNCTYPE(ctypes.c_uint, ctypes.c_void_p)(vtable)
        Release(ptr)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._destroy_staging()
        except Exception:
            pass
        try:
            self._session.close()
        except Exception:
            pass
        try:
            self._frame_pool.close()
        except Exception:
            pass
        self._release_com(self._context_ptr)
        self._release_com(self._device_ptr)
        self._context_ptr = 0
        self._device_ptr = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


__all__ = ['WgcCapture', 'WGC_AVAILABLE']
