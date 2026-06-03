"""Click Windows Start button to verify pyautogui actually affects WEI3216 desktop."""
import json, time
from websockets.sync.client import connect

WS = "ws://8.137.116.121:9080/client"
PASSWORD = "cdd39ee08a38ee62393a630ed05981e745f14e2b19c73b594210d10cebd914de"
AGENT_ID = "a6bd2444-84cd-5c96-b860-cbfaa2c2571a"

ws = connect(WS)
ws.send(json.dumps({"type": "auth", "password": PASSWORD, "agentId": AGENT_ID}))
# wait auth_ok
for _ in range(3):
    msg = json.loads(ws.recv(timeout=2))
    if msg.get("type") == "auth_ok":
        print("[OK] auth_ok — agent ready, sending clicks")
        break
# 1. Move mouse to center (verifies pyautogui.moveTo works)
print("step 1: moveTo(1280, 720) — center of 2560x1440")
ws.send(json.dumps({"type": "mouse", "action": "move", "x": 1280, "y": 720}))
time.sleep(0.5)
# 2. Click Windows Start button bottom-left (2560x1440 screen)
# Start button center: ~(20, 1450) — taskbar height ~40px
print("step 2: click(20, 1450) — Windows Start button")
ws.send(json.dumps({"type": "mouse", "action": "click", "x": 20, "y": 1450, "button": "left"}))
time.sleep(1.5)
# 3. Type 'cmd' to search
print("step 3: type 'cmd' to search")
for k in 'cmd':
    ws.send(json.dumps({"type": "key", "action": "press", "key": k}))
    time.sleep(0.05)
time.sleep(0.5)
# 4. Press Enter
print("step 4: press Enter")
ws.send(json.dumps({"type": "key", "action": "press", "key": "enter"}))
time.sleep(1.5)
print("[DONE] check Start menu + cmd window on WEI3216 desktop")
ws.close()
