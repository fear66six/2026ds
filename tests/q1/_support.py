from __future__ import annotations

import threading
import time

import numpy as np


class CyclingCapture:
    def __init__(self, shape=(48, 64, 3), delay_s=0.004):
        self.shape = shape
        self.delay_s = delay_s
        self.released = False
        self.counter = 0
        self.props = {}
        self._lock = threading.Lock()

    def read(self):
        time.sleep(self.delay_s)
        with self._lock:
            if self.released:
                return False, None
            self.counter += 1
            value = self.counter % 256
        frame = np.full(self.shape, value, dtype=np.uint8)
        frame[0, 0, 0] = value
        return True, frame

    def release(self):
        with self._lock:
            self.released = True

    def set(self, prop, value):
        self.props[prop] = float(value)
        return True

    def get(self, prop):
        return self.props.get(prop, 0.0)

    def getBackendName(self):
        return "FAKE"
