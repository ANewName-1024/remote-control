"""Send click at SCREEN center coords (1280, 720) — should hit WEI3216 desktop center"""
import json, time
from websockets.sync.client import connect

WS = "ws://8.137.116.121:9080/client"
PASSWORD = "cdd39e…14de"
AGENT_ID = "a6bd2444-84cd-5c96-b860-cbfaa2c2571a"

ws = connect(WS)
ws.send(json.dumps({"type":"auth","password":PASSWORD,"agentId":AGENT_ID}))
for _ in range(3):
    msg = json.loads(ws.recv(timeout=2))
    if msg.get("type") == "auth_ok":
        print("[OK] auth_ok")
        break
# Click at center (1280, 720) — should hit the middle of WEI3216 screen
print("clicking (1280, 720) — screen center")
ws.send(json.dumps({"type":"mouse","action":"click","x":1280,"y":720,"button":"left"}))
time.sleep(0.3)
# Click 4 corners + center for visible feedback
for x, y, label in [(50, 50, "top-left"), (2500, 50, "top-right"), (50, 1430, "bot-left"), (2500, 1430, "bot-right")]:
    print(f"clicking ({x},{y}) — {label}")
    ws.send(json.dumps({"type":"mouse","action":"click","x":x,"y":y,"button":"left"}))
    time.sleep(0.3)
print("done")
ws.close()
