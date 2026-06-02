"""Dispatcher entry point.

Usage:
    python -m agent --mode=service    # run as service (Session 0, SYSTEM)
    python -m agent --mode=helper     # run as helper (Session 1, user)
    python -m agent                   # legacy: detect mode from env or default to service

The service auto-spawns the helper in the active user session via
WTSQueryUserToken + CreateProcessAsUser. The helper auto-exits when the
service goes away (pipe disconnect).
"""
import sys
import os
import argparse
import logging

log = logging.getLogger('agent.main')


def detect_mode() -> str:
    """Auto-detect mode from environment (e.g. when started via the
    service launcher with --mode=helper, env RC_MODE=helper, etc.)."""
    env = os.environ.get('RC_MODE', '').lower()
    if env in ('service', 'helper'):
        return env
    # Legacy single-process mode: the user started agent.py directly.
    # We default to 'service' so they can still use it as before, but
    # the new install script overrides this.
    return 'service'


def main():
    p = argparse.ArgumentParser(description='Remote Control Agent')
    p.add_argument('--mode', choices=['service', 'helper', 'auto'],
                   default='auto',
                   help='Process mode: service (Session 0) or helper (Session 1)')
    p.add_argument('--config-dir', default=os.environ.get('RC_CONFIG_DIR'),
                   help='Override config dir (for tests)')
    args, unknown = p.parse_known_args()

    mode = args.mode if args.mode != 'auto' else detect_mode()

    if mode == 'service':
        from . import service
        return service.run(config_dir=args.config_dir)
    else:
        from . import helper
        return helper.run()


if __name__ == '__main__':
    sys.exit(main())
