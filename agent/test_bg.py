import os, sys, logging
APP = os.environ.get('APPDATA','.') + '\\RemoteControlAgent'
os.makedirs(APP, exist_ok=True)
LOG = APP + '\\agent.log'
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(LOG, encoding='utf-8')])
logging.info(f"Agent PID={os.getpid()} started")
print(f"Agent PID={os.getpid()} started, log={LOG}", flush=True)

import time
time.sleep(30)
logging.info("Agent still alive after 30s")
print("Agent still alive after 30s", flush=True)
