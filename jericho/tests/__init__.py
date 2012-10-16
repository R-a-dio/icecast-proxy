import sys
import threading
class StdThreaded(object):
    def __init__(self):
        super(StdThreaded, self).__init__()
        self.lock = threading.RLock()
    def write(self, *args, **kwargs):
        with self.lock:
            stdout.write(*args, **kwargs)
            
stdout = sys.stdout
sys.stdout = StdThreaded()