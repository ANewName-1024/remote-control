"""
Enhanced Screen Capture with Delta Frames
- Only sends changed screen regions (block-based)
- Pure Python implementation (no numpy needed)
- JPEG quality 75 for keyframes, 65 for delta regions
"""
import os
import io
import time
import struct
import logging
import threading
from typing import List, Tuple, Optional, Dict, Any

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.error("PIL not available!")

BLOCK_SIZE = 64   # pixels per block
MAX_REGIONS = 20  # max regions per delta frame
KEYFRAME_INTERVAL = 3.0  # seconds between forced keyframes


class DeltaScreenCapture:
    """
    Captures screen and computes delta frames.
    Block-based change detection without numpy.
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.last_rgb: Optional[bytes] = None
        self.last_time = 0.0
        self.frame_count = 0
        self.last_keyframe = 0.0
        self.bytes_saved = 0
        self._prev_hash = None
        
        # Pre-compute block grid
        self.bw = (width + BLOCK_SIZE - 1) // BLOCK_SIZE
        self.bh = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
        self.block_w = BLOCK_SIZE
        self.block_h = BLOCK_SIZE
        
        logging.info(f"DeltaScreenCapture: {width}x{height}, blocks={self.bw}x{self.bh}")
    
    def capture_and_encode(self) -> Optional[Dict[str, Any]]:
        """Capture screen and encode as keyframe or delta."""
        try:
            img = ImageGrab.grab()
            w, h = img.size
            rgb = img.convert('RGB').tobytes('raw', 'RGB')
        except Exception as e:
            logging.warning(f"Capture failed: {e}")
            return None
        
        now = time.time()
        self.frame_count += 1
        
        is_keyframe = (
            self.last_rgb is None or 
            now - self.last_keyframe > KEYFRAME_INTERVAL
        )
        
        if is_keyframe:
            self.last_keyframe = now
            self.last_rgb = rgb
            self._prev_hash = self._hash_frame(rgb)
            return self._encode_keyframe(img, w, h)
        else:
            result = self._encode_delta(img, rgb, w, h)
            self.last_rgb = rgb
            return result
    
    def _hash_frame(self, rgb: bytes) -> bytes:
        """Quick hash of frame using struct sampling."""
        # Sample every 100th byte for quick comparison
        return bytes(rgb[i] for i in range(0, min(len(rgb), 10000), 100))
    
    def _encode_keyframe(self, img: Image.Image, w: int, h: int) -> Dict[str, Any]:
        """Full frame as JPEG quality 75."""
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75)
        jpeg = buf.getvalue()
        
        import base64
        return {
            'type': 'screen',
            'fmt': 'kf',
            'data': base64.b64encode(jpeg).decode('ascii'),
            'w': w,
            'h': h,
            'ts': time.time()
        }
    
    def _encode_delta(self, img: Image.Image, rgb: bytes, w: int, h: int) -> Optional[Dict[str, Any]]:
        """Encode only changed blocks as JPEG regions."""
        # Find changed blocks
        blocks = self._find_changed_blocks(self.last_rgb, rgb, w, h)
        
        if not blocks:
            return None
        
        # Extract and encode each block as JPEG
        region_list = []
        pixel_data = b''
        
        for (x, y, bw, bh) in blocks[:MAX_REGIONS]:
            pass  # values from _merge_blocks are already correct
            
            region = img.crop((x, y, x + bw, y + bh))
            buf = io.BytesIO()
            region.save(buf, format='JPEG', quality=65)
            region_jpg = buf.getvalue()
            
            region_list.append([x, y, bw, bh])
            pixel_data += struct.pack('>HHHH', x, y, bw, bh)
            pixel_data += struct.pack('>I', len(region_jpg))
            pixel_data += region_jpg
        
        import base64
        return {
            'type': 'screen',
            'fmt': 'df',
            'data': base64.b64encode(pixel_data).decode('ascii'),
            'regions': region_list,
            'w': w,
            'h': h,
            'ts': time.time(),
            'blocks': len(blocks)
        }
    
    def _find_changed_blocks(self, prev: bytes, curr: bytes, w: int, h: int) -> List[Tuple[int, int]]:
        """Find blocks that have changed between frames."""
        if not prev or len(prev) != len(curr):
            return []
        
        changed = []
        stride = w * 3  # bytes per row (RGB)
        
        for by in range(self.bh):
            for bx in range(self.bw):
                x = bx * self.block_w
                y = by * self.block_h
                bw = min(self.block_w, w - x)
                bh = min(self.block_h, h - y)
                
                if self._block_changed(prev, curr, x, y, bw, bh, stride, w, h):
                    changed.append((bx, by))
        
        return self._merge_blocks(changed, w, h)
    
    def _block_changed(self, prev: bytes, curr: bytes, x: int, y: int, bw: int, bh: int, stride: int, w: int, h: int) -> bool:
        """Check if a block has changed using sampling."""
        # Sample 8x8 grid within block for speed
        sample_step_x = max(1, bw // 8)
        sample_step_y = max(1, bh // 8)
        
        for sy in range(bh):
            row_y = y + sy
            if row_y >= h:
                break
            p_row = row_y * stride
            c_row = row_y * stride
            
            for sx in range(0, bw, sample_step_x):
                px = x + sx
                if px >= w:
                    break
                
                pi = p_row + px * 3
                ci = c_row + px * 3
                
                # Compare RGB pixels (3 bytes)
                if prev[pi:pi+3] != curr[ci:ci+3]:
                    return True
        return False
    
    def _merge_blocks(self, blocks: List[Tuple[int, int]], w: int, h: int) -> List[Tuple[int, int]]:
        """Merge adjacent blocks into larger regions."""
        if not blocks:
            return []
        
        # Sort by position
        blocks_set = set(blocks)
        merged = []
        
        for bx, by in sorted(blocks_set):
            x = bx * self.block_w
            y = by * self.block_h
            bw = min(self.block_w, w - x)
            bh = min(self.block_h, h - y)
            
            merged.append((x, y, bw, bh))
        
        return merged


def get_screen_size():
    """Get screen resolution."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            return img.size
        except Exception:
            return 1920, 1080
