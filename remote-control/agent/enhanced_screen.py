"""
Enhanced Screen Capture with Delta Frames
- Only sends changed screen regions
- ZSTD compression for region data
- Falls back to full frame if no previous frame
"""
import os
import io
import time
import struct
import logging
import threading
import hashlib
from typing import List, Tuple, Optional, Dict, Any

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False
    logging.warning("zstandard not installed, delta compression disabled")

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.error("PIL not available!")

COMPRESSION_LEVEL = int(os.environ.get('ZSTD_LEVEL', '3'))
BLOCK_SIZE = 64  # pixel block size for change detection
MAX_REGIONS = 15  # max regions per frame
KEYFRAME_INTERVAL = 3.0  # seconds between forced keyframes


class DeltaScreenCapture:
    """
    Captures screen and computes delta frames.
    Encodes as: JSON header + compressed region JPEG data
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.last_rgb: Optional[bytes] = None
        self.last_time = 0.0
        self.frame_count = 0
        self.last_keyframe = 0.0
        self.bytes_saved = 0  # stats
        
        if ZSTD_AVAILABLE:
            self._zstd = zstd.ZstdCompressor(level=COMPRESSION_LEVEL)
            self._zstd_dctx = zstd.ZstdDecompressor()
        else:
            self._zstd = None
        
        # Frame cache for change detection
        self._cache = {}
        
        logging.info(f"DeltaScreenCapture: {width}x{height}, ZSTD={ZSTD_AVAILABLE}")
    
    def capture_and_encode(self) -> Dict[str, Any]:
        """
        Capture screen and encode as delta or keyframe.
        Returns a dict ready to send via WebSocket.
        
        Keyframe format:
          {'type': 'screen', 'fmt': 'kf', 'data': '<base64 jpeg>', 'w': w, 'h': h}
        
        Delta format:
          {'type': 'screen', 'fmt': 'df', 'data': '<base64 compressed>', 
           'regions': [(x,y,w,h), ...], 'w': w, 'h': h}
        """
        try:
            img = ImageGrab.grab()
            w, h = img.size
            rgb = img.convert('RGB').tobytes('raw', 'RGB')
        except Exception as e:
            logging.warning(f"Capture failed: {e}")
            return None
        
        now = time.time()
        self.frame_count += 1
        
        # Force keyframe periodically or on first frame
        is_keyframe = (
            self.last_rgb is None or 
            now - self.last_keyframe > KEYFRAME_INTERVAL
        )
        
        if is_keyframe:
            self.last_keyframe = now
            self.last_rgb = rgb
            return self._encode_keyframe(img)
        else:
            return self._encode_delta(img, rgb)
    
    def _encode_keyframe(self, img: Image.Image) -> Dict[str, Any]:
        """Encode full frame as JPEG."""
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75)
        jpeg = buf.getvalue()
        
        import base64
        return {
            'type': 'screen',
            'fmt': 'kf',  # keyframe
            'data': base64.b64encode(jpeg).decode('ascii'),
            'w': self.width,
            'h': self.height,
            'ts': time.time()
        }
    
    def _encode_delta(self, img: Image.Image, rgb: bytes) -> Optional[Dict[str, Any]]:
        """Encode only changed regions."""
        if self.last_rgb is None:
            return self._encode_keyframe(img)
        
        # Compute changed blocks
        regions = self._compute_changed_regions(self.last_rgb, rgb)
        
        if not regions:
            return None  # no change, skip frame
        
        self.last_rgb = rgb
        
        # Extract and encode each region as JPEG
        region_list = []
        pixel_data = b''
        
        for (x, y, w, h) in regions[:MAX_REGIONS]:
            region = img.crop((x, y, x+w, y+h))
            buf = io.BytesIO()
            region.save(buf, format='JPEG', quality=65)
            region_jpg = buf.getvalue()
            
            region_list.append([x, y, w, h])
            pixel_data += struct.pack('I', len(region_jpg)) + region_jpg
        
        # Compress with ZSTD
        if self._zstd:
            try:
                compressed = self._zstd.compress(pixel_data)
            except Exception as e:
                logging.warning(f"ZSTD compress failed: {e}, using raw")
                compressed = pixel_data
        else:
            compressed = pixel_data
        
        self.bytes_saved += len(pixel_data) - len(compressed)
        
        import base64
        return {
            'type': 'screen',
            'fmt': 'df',  # delta frame
            'data': base64.b64encode(compressed).decode('ascii'),
            'regions': region_list,
            'w': self.width,
            'h': self.height,
            'ts': time.time(),
            'saved': self.bytes_saved
        }
    
    def _compute_changed_regions(self, prev: bytes, curr: bytes) -> List[Tuple[int, int, int, int]]:
        """Block-based change detection. Returns list of (x,y,w,h) of changed blocks."""
        regions = []
        bw = BLOCK_SIZE
        bh = BLOCK_SIZE
        
        for y in range(0, self.height, bh):
            for x in range(0, self.width, bw):
                # Compare this block
                py = y * self.width * 3
                pyo = x * 3
                
                changed = False
                for by in range(min(bh, self.height - y)):
                    o1 = py + by * self.width * 3 + pyo
                    o2 = y * self.width * 3 + (y + by) * self.width * 3 + x * 3
                    
                    if prev[o1:o1+3] != curr[o1:o1+3]:
                        # Simple byte comparison
                        b1 = prev[o1:o1+bw*3]
                        b2 = curr[o2:o2+bw*3]
                        if b1 != b2:
                            changed = True
                            break
                
                # Quick hash check
                if changed:
                    # Compute hash of block in prev and curr
                    o1 = y * self.width * 3 + x * 3
                    s1 = min(bw * 3, self.width * 3 - x * 3)
                    for by in range(min(bh, self.height - y)):
                        s = (y + by) * self.width * 3
                        e = s + min(bw * 3, self.width * 3 - x * 3)
                        if prev[s:e] != curr[s:e]:
                            regions.append((x, y, min(bw, self.width-x), min(bh, self.height-y)))
                            break
        
        # Merge adjacent regions
        return self._merge_regions(regions)
    
    def _merge_regions(self, regions: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
        """Merge adjacent regions to reduce count."""
        if not regions:
            return []
        
        # Sort by position
        regions = sorted(regions, key=lambda r: (r[1], r[0]))
        merged = [regions[0]]
        
        for (x, y, w, h) in regions[1:]:
            prev = merged[-1]
            px, py, pw, ph = prev
            
            # If adjacent (within 2 pixels) and same row, merge
            if (abs(x - (px + pw)) <= 4 and y == py and h == ph):
                merged[-1] = (px, py, x - px + w, ph)
            else:
                merged.append((x, y, w, h))
        
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
