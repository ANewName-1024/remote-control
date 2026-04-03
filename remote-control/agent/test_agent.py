import sys, os, logging
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', '.'), 'RemoteControlAgent')
LOG_FILE = os.path.join(CONFIG_DIR, 'agent.log')
os.makedirs(CONFIG_DIR, exist_ok=True)
fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
logging.basicConfig(level=logging.INFO, handlers=[fh])
logging.info("TEST: Agent started")
print("STDOUT: Agent started", flush=True)
sys.exit(0)
