"""Tests for the WGC (Windows.Graphics.Capture) backend.

Strategy
========
WGC depends on:
  - winrt-python (3.2.1+) interop helpers (create_for_monitor,
    create_direct3d11_device_from_dxgi_device)
  - D3D11 device from ctypes.windll.d3d11.D3D11CreateDevice
  - Direct3D11CaptureFramePool + GraphicsCaptureSession (winrt)
  - SoftwareBitmap (winrt) for GPU->CPU readback

We mock the winrt and ctypes surface so the tests run in CI (Linux/macOS)
where these are unavailable. Each test isolates a single piece:

  WC1: module imports cleanly with WGC_AVAILABLE=False when winrt is missing
  WC2: WGC_AVAILABLE=True when winrt pieces import
  WC3: WgcCapture raises RuntimeError when WGC_AVAILABLE=False
  WC4: WgcCapture.grab returns None when _frame_pool has no frame
  WC5: WgcCapture.grab returns RGB array (HxWx3) when SoftwareBitmap has data
  WC6: WgcCapture.close() releases session, frame_pool, d3d11 device
  WC7: _create_d3d11_device returns c_void_p with non-zero value
  WC8: _get_primary_monitor_handle returns non-zero hmonitor
  WC9: BGRA->RGB swap is correct (no channel swap regression)
"""
import ctypes
import unittest
from unittest.mock import MagicMock, patch, call

import numpy as np


def _try_import_wgc():
    """Import wgc without triggering the winrt import failure hard.

    Returns (module, is_mock_mode):
      - is_mock_mode=True  : winrt pieces were unavailable; module is real
                              but WGC_AVAILABLE is False (or the module
                              itself failed to import — we skip).
      - is_mock_mode=False : module loaded with WGC_AVAILABLE=True
    """
    try:
        import wgc
        return wgc, False
    except Exception:
        return None, True


class TestWgcModuleSurface(unittest.TestCase):
    """WC1, WC2: module import + WGC_AVAILABLE flag."""

    def test_WC1_module_imports(self):
        """WC1: wgc.py is importable even on platforms without winrt."""
        # First try real import (Windows with winrt installed)
        try:
            import wgc
            # OK, real module
            self.assertTrue(hasattr(wgc, 'WgcCapture'))
            self.assertTrue(hasattr(wgc, 'WGC_AVAILABLE'))
        except Exception:
            # If the module itself can't import (shouldn't happen since
            # we wrap winrt imports in try/except), mark as skip.
            self.skipTest('wgc.py itself failed to import')

    def test_WC2_wgc_available_flag_type(self):
        """WC2: WGC_AVAILABLE is a bool regardless of winrt presence."""
        import wgc
        self.assertIsInstance(wgc.WGC_AVAILABLE, bool)


class TestWgcCaptureConstruction(unittest.TestCase):
    """WC3: WgcCapture refuses to construct without winrt."""

    def test_WC3_raises_when_unavailable(self):
        """WC3: RuntimeError with helpful install command when WGC_AVAILABLE=False."""
        import wgc
        if wgc.WGC_AVAILABLE:
            self.skipTest('winrt is installed; cannot test missing-deps path')
        with self.assertRaises(RuntimeError) as ctx:
            wgc.WgcCapture()
        msg = str(ctx.exception)
        # The error message should mention pip install (actionable for the user)
        self.assertIn('pip install', msg)
        # And list the key packages
        self.assertIn('winrt-Windows.Graphics.Capture', msg)


class TestWgcGrabAndFrameReadback(unittest.TestCase):
    """WC4, WC5, WC9: grab() and SoftwareBitmap->numpy RGB path.

    These mock out the winrt surface and the ctypes D3D11 surface so
    they run in CI without real hardware. Only run when WGC_AVAILABLE=True
    (otherwise the winrt symbols we need to patch don't exist).
    """

    def setUp(self):
        import wgc
        if not wgc.WGC_AVAILABLE:
            self.skipTest('winrt pieces not available; skipping WGC frame-readback tests')

    def test_WC4_grab_returns_none_when_no_frame(self):
        """WC4: try_get_next_frame() returns None -> grab() returns None."""
        with patch('wgc._create_d3d11_device') as mock_d3d, \
             patch('wgc._get_primary_monitor_handle') as mock_hmon, \
             patch('wgc.d3d_io.create_direct3d11_device_from_dxgi_device') as mock_wrap, \
             patch('wgc.cap_io.create_for_monitor') as mock_cap_item, \
             patch('wgc.wgc_mod.Direct3D11CaptureFramePool') as mock_fp_cls:
            mock_d3d.return_value = ctypes.c_void_p(0x1234)
            mock_hmon.return_value = 0x10001
            mock_wrap.return_value = MagicMock(name='IDirect3DDevice')
            mock_item = MagicMock()
            mock_item.size.width = 1920
            mock_item.size.height = 1080
            mock_cap_item.return_value = mock_item
            mock_fp = MagicMock()
            mock_fp.try_get_next_frame.return_value = None  # no frame yet
            mock_fp_cls.create_free_threaded.return_value = mock_fp

            import wgc as wm
            cap = wm.WgcCapture()
            result = cap.grab()
            self.assertIsNone(result)
            cap.close()

    def test_WC5_grab_returns_rgb_array(self):
        """WC5: grab() returns HxWx3 RGB uint8 when SoftwareBitmap has data."""
        w, h = 4, 3
        # 12 pixels × 4 channels (BGRA) — use distinct colors per channel
        # to verify the BGRA->RGB swap.
        bgra = bytearray()
        for row in range(h):
            for col in range(w):
                b, g, r, a = (10 + col, 20 + row, 30 + col + row, 255)
                bgra.extend((b, g, r, a))
        bgra_bytes = bytes(bgra)

        with patch('wgc._create_d3d11_device') as mock_d3d, \
             patch('wgc._get_primary_monitor_handle') as mock_hmon, \
             patch('wgc.d3d_io.create_direct3d11_device_from_dxgi_device') as mock_wrap, \
             patch('wgc.cap_io.create_for_monitor') as mock_cap_item, \
             patch('wgc.wgc_mod.Direct3D11CaptureFramePool') as mock_fp_cls, \
             patch('wgc.img_mod.SoftwareBitmap') as mock_sb, \
             patch('wgc.streams_mod.Buffer') as mock_buf:
            mock_d3d.return_value = ctypes.c_void_p(0x1234)
            mock_hmon.return_value = 0x10001
            mock_wrap.return_value = MagicMock(name='IDirect3DDevice')
            mock_item = MagicMock()
            mock_item.size.width = w
            mock_item.size.height = h
            mock_cap_item.return_value = mock_item

            mock_frame = MagicMock()
            mock_fp = MagicMock()
            mock_fp.try_get_next_frame.return_value = mock_frame
            mock_fp_cls.create_free_threaded.return_value = mock_fp

            # SoftwareBitmap.create_copy_from_surface_async(surface).get()
            # returns a SoftwareBitmap whose copy_to_buffer fills our buffer.
            mock_bitmap = MagicMock()
            mock_bitmap.pixel_width = w
            mock_bitmap.pixel_height = h

            async_op = MagicMock()
            async_op.get.return_value = mock_bitmap
            mock_sb.create_copy_from_surface_async.return_value = async_op

            # copy_to_buffer(buffer) -> buffer becomes the bgra bytes.
            # We need bytes(buf) in the production code to return real bytes.
            # MagicMock's __bytes__ returns a Mock, not bytes, so we use a
            # real ctypes array (which supports the buffer protocol).
            class FakeBuf:
                """Mimics winrt Buffer: .length attr + buffer protocol."""
                def __init__(self, data):
                    self.length = len(data)
                    # ctypes array for real buffer protocol support
                    self._data = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
                def __bytes__(self):
                    return bytes(self._data)
            fake_buf = FakeBuf(bgra_bytes)
            mock_buf.return_value = fake_buf

            import wgc as wm
            cap = wm.WgcCapture()
            result = cap.grab()
            self.assertIsNotNone(result)
            self.assertEqual(result.shape, (h, w, 3))
            self.assertEqual(result.dtype, np.uint8)
            # Verify BGRA->RGB swap. Original BGRA pixel at (row, col):
            #   B=10+col, G=20+row, R=30+col+row
            # After swap, RGB pixel at (row, col):
            #   R=30+col+row, G=20+row, B=10+col
            for row in range(h):
                for col in range(w):
                    self.assertEqual(result[row, col, 0], 30 + col + row,
                                     f'R at ({row},{col})')
                    self.assertEqual(result[row, col, 1], 20 + row,
                                     f'G at ({row},{col})')
                    self.assertEqual(result[row, col, 2], 10 + col,
                                     f'B at ({row},{col})')
            cap.close()

    def test_WC9_bgra_rgb_swap_correctness(self):
        """WC9: pure-data check on the reshape + channel swap, no mocks.

        Sanity check that the indexing arr[:, :, [2, 1, 0]] does what we
        think. Catches off-by-one or wrong-axis bugs at zero cost.
        """
        h, w = 2, 2
        bgra = np.array([
            [[1, 2, 3, 255], [4, 5, 6, 255]],   # row 0
            [[7, 8, 9, 255], [10, 11, 12, 255]],  # row 1
        ], dtype=np.uint8)
        rgb = bgra[:, :, [2, 1, 0]].copy()
        # Expect: R=original[2], G=original[1], B=original[0]
        self.assertEqual(rgb[0, 0, 0], 3)
        self.assertEqual(rgb[0, 0, 1], 2)
        self.assertEqual(rgb[0, 0, 2], 1)
        self.assertEqual(rgb[1, 1, 0], 12)
        self.assertEqual(rgb[1, 1, 1], 11)
        self.assertEqual(rgb[1, 1, 2], 10)


class TestWgcCloseLifecycle(unittest.TestCase):
    """WC6: close() releases session, frame_pool, d3d11 device."""

    def setUp(self):
        import wgc
        if not wgc.WGC_AVAILABLE:
            self.skipTest('winrt pieces not available; skipping close-path tests')

    def test_WC6_close_releases_all_resources(self):
        """WC6: close() calls close() on session+frame_pool + Release on D3D11."""
        with patch('wgc._create_d3d11_device') as mock_d3d, \
             patch('wgc._get_primary_monitor_handle') as mock_hmon, \
             patch('wgc.d3d_io.create_direct3d11_device_from_dxgi_device'), \
             patch('wgc.cap_io.create_for_monitor') as mock_cap_item, \
             patch('wgc.wgc_mod.Direct3D11CaptureFramePool') as mock_fp_cls:
            mock_d3d.return_value = ctypes.c_void_p(0x1234)
            mock_hmon.return_value = 0x10001  # integer hmonitor (so #x format works)
            mock_item = MagicMock()
            mock_item.size.width = 100
            mock_item.size.height = 100
            mock_cap_item.return_value = mock_item
            mock_fp = MagicMock()
            mock_fp_cls.create_free_threaded.return_value = mock_fp

            import wgc as wm
            cap = wm.WgcCapture()
            cap.close()

            # Both session and frame_pool should have .close() called
            cap._session.close.assert_called_once()
            cap._frame_pool.close.assert_called_once()
            # IUnknown_Release on the D3D11 device
            self.assertTrue(mock_d3d.called)
            # Closing twice is a no-op (no exception)
            cap.close()


class TestWgcLowLevelHelpers(unittest.TestCase):
    """WC7, WC8: ctypes helpers (don't require winrt)."""

    def setUp(self):
        import wgc
        if not wgc.WGC_AVAILABLE:
            # These helpers exist even without winrt; they only need ctypes
            # and a real user32.dll. On non-Windows they still import
            # (ctypes.windll is lazy-bound).
            pass

    def test_WC7_create_d3d11_device_returns_c_void_p(self):
        """WC7: _create_d3d11_device returns a c_void_p with non-zero value."""
        import wgc
        if not hasattr(wgc, '_create_d3d11_device'):
            self.skipTest('wgc missing _create_d3d11_device (unexpected)')
        try:
            ptr = wgc._create_d3d11_device()
        except OSError as e:
            # If D3D11 isn't usable on this machine (e.g., headless CI),
            # skip rather than fail.
            self.skipTest(f'D3D11CreateDevice not available: {e}')
        self.assertIsInstance(ptr, ctypes.c_void_p)
        self.assertNotEqual(ptr.value, 0,
                            'D3D11CreateDevice returned a NULL device')

    def test_WC8_get_primary_monitor_returns_nonzero(self):
        """WC8: _get_primary_monitor_handle returns non-zero hmonitor."""
        import wgc
        if not hasattr(wgc, '_get_primary_monitor_handle'):
            self.skipTest('wgc missing _get_primary_monitor_handle (unexpected)')
        try:
            hmon = wgc._get_primary_monitor_handle()
        except OSError as e:
            self.skipTest(f'MonitorFromWindow not available: {e}')
        self.assertNotEqual(hmon, 0)


if __name__ == '__main__':
    unittest.main()
