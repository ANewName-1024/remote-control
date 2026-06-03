"""Verify 4-backend fallback: WGC > DXGI > mss > PIL.

Confirms ScreenCapture picks WGC first (no init_apartment call = default MTA).
"""
import sys
import time
sys.path.insert(0, '.')
sys.path.insert(0, '..')

from agent.capture import ScreenCapture

t0 = time.time()
sc = ScreenCapture()
print(f'backend={sc.backend} size={sc.width}x{sc.height} init={time.time()-t0:.2f}s')
print(f'status={sc.status()}')

# Grab 5 frames
for i in range(5):
    a = sc.grab()
    if a is not None:
        print(f'  grab #{i}: shape={a.shape} mean={a.mean():.0f}')
    else:
        print(f'  grab #{i}: None')
    time.sleep(0.2)

sc.close()
print('OK')
