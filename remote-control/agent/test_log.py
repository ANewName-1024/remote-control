import os, sys, logging
LOG = os.environ['APPDATA'] + '\\RemoteControlAgent\\agent.log'
os.makedirs(os.environ['APPDATA'] + '\\RemoteControlAgent', exist_ok=True)
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(LOG, encoding='utf-8')])
logging.info('DIRECT TEST OK')
print('Script finished', flush=True)
