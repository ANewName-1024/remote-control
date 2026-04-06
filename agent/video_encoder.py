"""
Video Encoder for Remote Control Agent
- Delta Frame: Only send changed screen regions
- ZSTD Compression: Better than base64
- H.264 via subprocess (ffmpeg) when available, fallback to JPEG+ZSTD
"""
import os
import time
import struct
import logging
import subprocess
import threading
import queue
from io import BytesIO
from typing import Optional, Tuple, List

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False
    logging.warning("zstandard not available, using raw bytes")

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Config
COMPRESSION_LEVEL = 3 if ZSTD_AVAILABLE else 0
SCREENSHOT_METHOD = 'PIL'  # 'mss' or 'PIL'
USE_H264 = os.environ.get('USE_H264', '0') == '1'

class VideoEncoder:
    def __init__(self, width: int, height: int, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.last_frame = None
        self.frame_count = 0
        self.last_keyframe_time = 0
        self.keyframe_interval = 2.0  # seconds between keyframes
        
        # Delta tracking
        self.region_history = []  # [(x, y, w, h), ...]
        self.change_threshold = 0.05  # 5% pixel change triggers region
        
        # H.264 subprocess (if ffmpeg available)
        self.ffmpeg_proc = None
        self._init_h264()
        
        # ZSTD context
        if ZSTD_AVAILABLE:
            self._zstd_ctx = zstd.ZstdCompressor(level=COMPRESSION_LEVEL)
        
        logging.info(f"VideoEncoder: {width}x{height} @ {fps}fps, H264={USE_H264}, ZSTD={ZSTD_AVAILABLE}")
    
    def _init_h264(self):
        """Try to start ffmpeg H.264 encoder subprocess."""
        if not USE_H264:
            return
        
        try:
            # Check if ffmpeg is available
            subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            
            self.ffmpeg_proc = subprocess.Popen(
                [
                    'ffmpeg', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                    '-s', f'{self.width}x{self.height}',
                    '-r', str(self.fps),
                    '-i', '-',  # stdin
                    '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-tune', 'fastdecode', '-zerolatency',
                    '-b:v', '1500k', '-maxrate', '2000k',
                    '-pix_fmt', 'yuv420p',
                    '-f', 'h264', '-'  # output to stdout
                ],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            logging.info("H.264 encoder (ffmpeg) started")
        except Exception as e:
            logging.warning(f"H.264 init failed: {e}, falling back to JPEG+ZSTD")
            self.ffmpeg_proc = None
    
    def capture_screen(self) -> Optional[bytes]:
        """Capture full screen, return raw RGB bytes."""
        try:
            if SCREENSHOT_METHOD == 'mss' and MSS_AVAILABLE:
                with mss.mss() as sct:
                    img = sct.grab(sct.monitors[1])
                    # Convert BGRA to RGB
                    import numpy as np
                    arr = np.array(img)
                    return arr[:, :, :3].tobytes()
            elif PIL_AVAILABLE:
                img = ImageGrab.grab()
                return img.convert('RGB').tobytes('raw', 'RGB')
        except Exception as e:
            logging.warning(f"Capture error: {e}")
        return None
    
    def compute_diff_regions(self, frame1: bytes, frame2: bytes) -> List[Tuple[int, int, int, int]]:
        """Compute changed regions between two frames. Returns list of (x,y,w,h)."""
        if not self.last_frame:
            return [(0, 0, self.width, self.height)]
        
        # Simple block-based diff
        block_size = 64
        changed = []
        
        for y in range(0, self.height, block_size):
            for x in range(0, self.width, block_size):
                b1 = frame1[y*self.width*3 + x*3 : (y+block_size)*self.width*3]
                b2 = frame2[y*self.width*3 + x*3 : (y+block_size)*self.width*3]
                
                if b1 != b2:
                    changed.append((x, y, min(block_size, self.width-x), min(block_size, self.height-y)))
        
        return changed if changed else []
    
    def encode_frame(self, rgb_data: bytes, force_keyframe: bool = False) -> bytes:
        """
        Encode a frame. Returns encoded bytes ready for transmission.
        Frame format: [1 byte flag][4 bytes length][payload]
        flag: 0x01=keyframe(JPEG/H264), 0x02=delta, 0x03=keyframe+yuv
        """
        now = time.time()
        is_keyframe = force_keyframe or (now - self.last_keyframe_time > self.keyframe_interval)
        
        if is_keyframe:
            self.last_keyframe_time = now
            return self._encode_keyframe(rgb_data)
        else:
            return self._encode_delta(rgb_data)
    
    def _encode_keyframe(self, rgb_data: bytes) -> bytes:
        """Full frame - JPEG or H.264."""
        if self.ffmpeg_proc:
            # H.264
            try:
                self.ffmpeg_proc.stdin.write(rgb_data)
                self.ffmpeg_proc.stdin.flush()
                h264_data = self.ffmpeg_proc.stdout.read(4)
                # Read NAL units until we get a frame
                # Simple: read until stdout has enough
                frame_data = b''
                while len(frame_data) < 10000:  # reasonable frame size
                    byte = self.ffmpeg_proc.stdout.read(1)
                    if not byte:
                        break
                    frame_data += byte
                    # Check for end marker (0x000001 or end of frame)
                    if len(frame_data) > 5 and frame_data[-4:] == b'\x00\x00\x01\xb3':
                        break
                
                if frame_data:
                    return b'\x01' + len(frame_data).to_bytes(4, 'big') + frame_data
            except Exception as e:
                logging.warning(f"H.264 encode error: {e}")
        
        # Fallback: JPEG
        try:
            img = Image.frombytes('RGB', (self.width, self.height), rgb_data)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=75)
            jpeg_data = buf.getvalue()
            return b'\x01' + len(jpeg_data).to_bytes(4, 'big') + jpeg_data
        except Exception as e:
            logging.warning(f"JPEG encode error: {e}")
            return b''
    
    def _encode_delta(self, rgb_data: bytes) -> bytes:
        """Delta frame - only changed regions."""
        if not self.last_frame:
            return self._encode_keyframe(rgb_data)
        
        regions = self.compute_diff_regions(self.last_frame, rgb_data)
        
        if not regions:
            return b'\x03'  # no change marker
        
        # Pack regions + pixel data
        region_data = b''
        pixels_data = b''
        
        try:
            img = Image.frombytes('RGB', (self.width, self.height), rgb_data)
            
            for (x, y, w, h) in regions[:10]:  # max 10 regions per frame
                # Compress region as JPEG
                region = img.crop((x, y, x+w, y+h))
                buf = BytesIO()
                region.save(buf, format='JPEG', quality=60)
                region_jpg = buf.getvalue()
                
                region_data += struct.pack('HHHH', x, y, w, h)
                pixels_data += struct.pack('I', len(region_jpg)) + region_jpg
            
            # Compress combined data with ZSTD if available
            payload = region_data + pixels_data
            if ZSTD_AVAILABLE:
                payload = self._zstd_ctx.compress(payload)
            
            return b'\x02' + struct.pack('I', len(payload)) + payload
        except Exception as e:
            logging.warning(f"Delta encode error: {e}")
            return self._encode_keyframe(rgb_data)
    
    def close(self):
        if self.ffmpeg_proc:
            self.ffmpeg_proc.stdin.close()
            self.ffmpeg_proc.wait(timeout=2)
            logging.info("H.264 encoder closed")
