import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from studio import proc

# A driver like HyperFrames: its browser lives in another process group and is relaunched when it dies.
DRIVER = r'''
import os, signal, subprocess, sys, time
record = sys.argv[1]
def launch():
    child = subprocess.Popen(['sleep', '60'], start_new_session=True)
    with open(record, 'a') as out:
        out.write(f"{child.pid}\n")
    return child
child = launch()
signal.signal(signal.SIGTERM, lambda *_: None)
print('ready', flush=True)
while True:
    if child.poll() is not None:
        child = launch()
    time.sleep(.05)
'''


class Cancelled(Exception):
    pass


class StreamTests(unittest.TestCase):
    def test_cancelling_a_browser_driver_leaves_no_process_behind(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / 'children.txt'
            started = []

            def check():
                if started and time.time() - started[0] > .8:
                    raise Cancelled()

            def on_line(line):
                if line == 'ready':
                    started.append(time.time())

            with self.assertRaises(Cancelled):
                proc.stream([sys.executable, '-c', DRIVER, record], check, on_line, process_group=True)
            time.sleep(.5)
            for pid in (int(value) for value in record.read_text().split()):
                with self.subTest(pid=pid), self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
