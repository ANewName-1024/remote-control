"""Smoke test: verify agent.wgc.WgcCapture works end-to-end.

Used during Phase 2 B 方案 2.0 — confirms the existing 240-line
winrt-python based wgc.py can actually grab frames, before we
integrate it into helper.py.
"""
import sys
import time
sys.path.insert(0, '.')
sys.path.insert(0, '..')

from agent.wgc import WgcCapture, WGC_AVAILABLE

print(f'WGC_AVAILABLE = {WGC_AVAILABLE}')
if not WGC_AVAILABLE:
    print('skip: winrt pieces missing')
    sys.exit(0)

t0 = time.time()
cap = WgcCapture()
print(f'WgcCapture init: {time.time()-t0:.2f}s, size {cap.width}x{cap.height}')

t0 = time.time()
arr = cap.grab()
ok = arr is not None
print(f'grab #1: ok={ok}', end='')
if ok:
    print(f' shape={arr.shape} mean_BGR={arr[:,:,0].mean():.0f},{arr[:,:,1].mean():.0f},{arr[:,:,2].mean():.0f} time={(time.time()-t0)*1000:.0f}ms')
else:
    print(' time={:.0f}ms'.format((time.time()-t0)*1000))

# 5fps 持续 5s
total = 0
got = 0
t_total = time.time()
while time.time() - t_total < 5.0:
    a = cap.grab()
    total += 1
    if a is not None:
        got += 1
    time.sleep(0.2)
print(f'5s @ 5fps: {got}/{total} frames ({got/total*100:.0f}%)')

cap.close()
print('OK')
