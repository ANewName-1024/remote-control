import os, sys, logging
APP = os.environ.get('APPDATA','.') + '\\RemoteControlAgent'
os.makedirs(APP, exist_ok=True)
LOG = APP + '\\agent.log'
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(LOG, encoding='utf-8')])
logging.info(f"PID={os.getpid()} starting, Python={sys.version}")

try:
    import websocket
    logging.info(f"websocket={websocket.__version__} OK")
except Exception as e:
    logging.error(f"websocket import failed: {e}")

try:
    import mss
    logging.info(f"mss OK")
except Exception as e:
    logging.error(f"mss import failed: {e}")

try:
    from PIL import ImageGrab
    logging.info("PIL ImageGrab OK")
except Exception as e:
    logging.error(f"PIL import failed: {e}")

try:
    import win32gui
    logging.info("win32gui OK")
except Exception as e:
    logging.error(f"win32gui import failed: {e}")

try:
    import pythoncom
    pythoncom.CoInitialize()
    logging.info("pythoncom OK")
except Exception as e:
    logging.error(f"pythoncom failed: {e}")

logging.info("All imports done, starting main loop")
print("All imports done", flush=True)

import time
for i in range(5):
    time.sleep(1)
    logging.info(f"tick {i+1}")
print("done", flush=True)
