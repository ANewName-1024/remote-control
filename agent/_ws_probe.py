"""主动注入 test mouse event via VPS to agent"""
import asyncio, json, sys, time, base64
from websockets.sync.client import connect

WS = "ws://8.137.116.121:9080/client"
PASSWORD = "cdd39ee08a38ee62393a630ed05981e745f14e2b19c73b594210d10cebd914de"
AGENT_ID = "a6bd2444-84cd-5c96-b860-cbfaa2c2571a"

# Send: connect → auth → wait for screen → send mouse click
def main():
    print(f"[1/4] connecting to {WS}")
    ws = connect(WS)
    print(f"[2/4] connected, sending auth as agent={AGENT_ID}")
    ws.send(json.dumps({
        "type": "auth",
        "password": PASSWORD,
        "agentId": AGENT_ID,
    }))
    # Read next message (could be auth result or first frame)
    for i in range(5):
        try:
            msg = ws.recv(timeout=2)
            data = json.loads(msg) if isinstance(msg, (str, bytes)) else msg
            t = data.get("type") if isinstance(data, dict) else "?"
            print(f"  recv #{i}: type={t} (data len={len(msg)})")
            if t == "screen":
                print(f"    screen fmt={data.get('fmt')} size={data.get('w')}x{data.get('h')}")
                break
        except Exception as e:
            print(f"  recv #{i}: TIMEOUT {e}")
            break
    print(f"[3/4] sending mouse click at (500,500) left button")
    ws.send(json.dumps({
        "type": "mouse",
        "action": "click",
        "x": 500, "y": 500,
        "button": "left",
    }))
    print(f"[3b/4] sending key 'h' press")
    ws.send(json.dumps({
        "type": "key",
        "action": "press",
        "key": "h",
    }))
    time.sleep(1)
    print(f"[4/4] done. closing.")
    ws.close()
    print("OK")

if __name__ == "__main__":
    main()
