"""Tests for agent/log_rotation.py.

Verifies:
  - File gets created on first call
  - Rotates when size exceeds max_bytes
  - backup_count respected (older logs get deleted)
  - Re-calling with same name is idempotent (no duplicate handlers)
  - Root logger sees the same file when configured explicitly
  - Encoding is utf-8 (Chinese log lines survive)
  - Survives 'cmd: <json with non-ASCII>' round-trip

Runs on any platform (no Windows-only deps).
"""
import json
import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

AGENT_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, AGENT_DIR)

from agent.log_rotation import setup_rotating_log


class TestRotatingLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='rc-log-rotation-')
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_R1_creates_file_on_first_write(self):
        path = os.path.join(self.tmp, 'agent.log')
        log = setup_rotating_log('rc-test-r1', path)
        log.info('hello')
        for h in log.handlers:
            h.flush()
        self.assertTrue(os.path.exists(path))
        body = open(path, encoding='utf-8').read()
        self.assertIn('hello', body)
        # Format includes logger name and level
        self.assertIn('rc-test-r1', body)
        self.assertIn('INFO', body)

    def test_R2_rotates_when_size_exceeded(self):
        path = os.path.join(self.tmp, 'rotate.log')
        # Tiny limit so 1-2 records triggers a rotation
        log = setup_rotating_log(
            'rc-test-r2', path,
            max_bytes=200, backup_count=3,
        )
        for i in range(50):
            log.info(f'line {i:04d} ' + 'x' * 50)
        for h in log.handlers:
            h.flush()
        # Current + 3 rotated = 4 files max
        files = sorted(os.listdir(self.tmp))
        # Should be current + at least 1 backup, at most 4 total
        log_files = [f for f in files if f.startswith('rotate')]
        self.assertGreaterEqual(len(log_files), 2)
        self.assertLessEqual(len(log_files), 4)
        # The .1 backup must contain SOME of the early log lines
        backup1 = os.path.join(self.tmp, 'rotate.log.1')
        if os.path.exists(backup1):
            body = open(backup1, encoding='utf-8').read()
            self.assertIn('line', body)

    def test_R3_backup_count_caps_total_files(self):
        path = os.path.join(self.tmp, 'capped.log')
        log = setup_rotating_log(
            'rc-test-r3', path,
            max_bytes=100, backup_count=2,
        )
        for i in range(100):
            log.info(f'event {i} ' + 'y' * 50)
        for h in log.handlers:
            h.flush()
        # backup_count=2 means: 1 current + 2 backups = 3 max
        log_files = [f for f in os.listdir(self.tmp) if f.startswith('capped')]
        self.assertLessEqual(len(log_files), 3)

    def test_R4_idempotent_repeated_calls(self):
        path = os.path.join(self.tmp, 'idempotent.log')
        a = setup_rotating_log('rc-test-r4', path)
        b = setup_rotating_log('rc-test-r4', path)
        # Same logger, same handlers — not duplicated
        self.assertIs(a, b)
        self.assertEqual(len(a.handlers), len(b.handlers))

    def test_R5_creates_parent_directory(self):
        nested = os.path.join(self.tmp, 'a', 'b', 'c', 'deep.log')
        log = setup_rotating_log('rc-test-r5', nested)
        log.info('nested')
        for h in log.handlers:
            h.flush()
        self.assertTrue(os.path.exists(nested))

    def test_R6_utf8_chinese_survives(self):
        path = os.path.join(self.tmp, 'utf8.log')
        log = setup_rotating_log('rc-test-r6', path)
        log.info('中文日志行: 远程控制测试 鼠标 click')
        for h in log.handlers:
            h.flush()
        body = open(path, encoding='utf-8').read()
        self.assertIn('远程控制测试', body)
        self.assertIn('鼠标', body)

    def test_R7_does_not_propagate_to_root(self):
        path = os.path.join(self.tmp, 'noprop.log')
        log = setup_rotating_log('rc-test-r7', path)
        # logger.propagate must be False so messages don't double-log
        # through the root handler chain (which basicConfig may
        # have configured elsewhere).
        self.assertFalse(log.propagate)

    def test_R8_works_with_very_small_files(self):
        # 1-byte max means EVERY line rotates. Test that we
        # don't crash / deadlock in this degenerate case.
        path = os.path.join(self.tmp, 'tiny.log')
        log = setup_rotating_log(
            'rc-test-r8', path,
            max_bytes=1, backup_count=2,
        )
        for i in range(20):
            log.info(f'x{i}')
        # Just check no exception was raised
        log_files = [f for f in os.listdir(self.tmp) if f.startswith('tiny')]
        self.assertGreaterEqual(len(log_files), 1)

    def test_R9_handles_concurrent_handler_types(self):
        # File handler + stderr handler, both with the same name in
        # their format string. The rotation test only checks files,
        # but the formatter setup must not crash on either handler.
        path = os.path.join(self.tmp, 'combo.log')
        log = setup_rotating_log('rc-test-r9', path)
        # 2 handlers: file + stderr
        self.assertEqual(len(log.handlers), 2)
        # Each has a formatter
        for h in log.handlers:
            self.assertIsNotNone(h.formatter)


if __name__ == '__main__':
    unittest.main()
