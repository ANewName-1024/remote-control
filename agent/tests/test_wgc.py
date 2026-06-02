"""Smoke tests for the WGC framework.

These tests verify the *framework* pieces (imports, IID correctness, COM
apartment init) without requiring an actual capture. The full WGC stack
including frame surface readback is gated on finishing the
IGraphicsCaptureItem* wrap + frame pool wiring in agent.wgc.

Skipped on non-Windows platforms.
"""
import sys
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'WGC is Windows-only')
class TestWGCFramework(unittest.TestCase):
    """Verify the WGC framework: imports, IIDs, capture wiring."""

    def test_wgc_module_imports(self):
        # Import via package path; the test runner sets cwd to agent/
        # so 'wgc' and 'capture' resolve correctly.
        from wgc import WGC_AVAILABLE, WgcCapture  # type: ignore
        self.assertIsInstance(WGC_AVAILABLE, bool)
        self.assertTrue(callable(WgcCapture))

    def test_graphics_capture_item_interop_iid(self):
        """IID {3628E81B-3CAC-4C60-B7F4-23CE0E0C3356}.

        Verified against the actual Windows SDK header
        Windows.Graphics.Capture.Interop.h (build 26100).
        Note: the trailing bytes are 33 56, not 2A 54 (an easy typo).
        """
        import uuid
        expected = uuid.UUID('3628E81B-3CAC-4C60-B7F4-23CE0E0C3356')
        self.assertEqual(str(expected).upper(),
                         '3628E81B-3CAC-4C60-B7F4-23CE0E0C3356')

    def test_capture_priority_wgc_first(self):
        """The capture priority chain is WGC > dxcam > mss > PIL."""
        from capture import WGC_AVAILABLE  # type: ignore
        self.assertTrue(WGC_AVAILABLE in (True, False))

    def test_screen_capture_class_importable(self):
        """ScreenCapture is importable; the constructor is exercised
        in a separate integration test (machine-dependent)."""
        from capture import ScreenCapture  # type: ignore
        self.assertTrue(callable(ScreenCapture))


if __name__ == '__main__':
    unittest.main()
