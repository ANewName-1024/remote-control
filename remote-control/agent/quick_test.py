import os, logging, sys
APP = os.environ.get('APPDATA', '.') + '\\RemoteControlAgent'
os.makedirs(APP, exist_ok=True)
LOG = APP + '\\agent.log'
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(LOG, encoding='utf-8')])
logging.info(f"Python: {sys.version}")
logging.info("Quick test OK")
print("DONE", flush=True)
