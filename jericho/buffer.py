import threading
import itertools
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
from collections import deque
from time import sleep
from . import chunks


MAX_BUFFER = 1024**2*16

class Buffer(object):
    def __init__(self, max_size=MAX_BUFFER):
        self.buffers = deque(maxlen=5)
        self.max_size = max_size
        self.lock = threading.Lock()
        self.closing = False
        self.eof = False
        self.read_pos = 0
        self.write_pos = 0

    def write(self, data):
        self.lock.acquire()
        try:
            if not self.buffers:
                self.buffers.append(StringIO())
                self.write_pos = 0
            buffer = self.buffers[-1]
            buffer.seek(self.write_pos)
            buffer.write(data)
            if buffer.tell() >= self.max_size:
                buffer = StringIO()
                self.buffers.append(buffer)
            self.write_pos = buffer.tell()
        finally:
            self.lock.release()

    def read(self, length=-1):
        read_buf = StringIO()
        remaining = length
        while True:
            if not self.buffers and not self.eof:
                sleep(0.5)
            elif not self.buffers and self.eof:
                return ''
            else:
                with self.lock:
                    buffer = self.buffers[0]
                    buffer.seek(self.read_pos)
                    read_buf.write(buffer.read(remaining))
                    self.read_pos = buffer.tell()
                    if length == -1:
                        # we did not limit the read, we exhausted the buffer, so delete it.
                        # keep reading from remaining buffers.
                        del self.buffers[0]
                        self.read_pos = 0
                    else:
                        #we limited the read so either we exhausted the buffer or not:
                        remaining = length - read_buf.tell()
                        if remaining > 0:
                            # exhausted, remove buffer, read more.
                            # keep reading from remaining buffers.
                            del self.buffers[0]
                            self.read_pos = 0
                        else:
                            # did not exhaust buffer, but read all that was requested.
                            # break to stop reading and return data of requested length.
                            break
        return read_buf.getvalue()

    def __len__(self):
        len = 0
        with self.lock:
            for buffer in self.buffers:
                buffer.seek(0, 2)
                if buffer == self.buffers[0]:
                    len += buffer.tell() - self.read_pos
                else:
                    len += buffer.tell()
            return len

    def close(self):
        self.eof = True
        
class ChunkBuffer(object):
    def __init__(self, chunk_size=1024):
        super(ChunkBuffer, self).__init__()
        self.chunk_size = chunk_size
        self.buffer = deque()
        self.length = 0
        self.lock = threading.Lock()
        self.eof = False
        
    def write(self, data):
        with self.lock:
            self.length += len(data)
            try:
                leftover = self.buffer.pop()
            except IndexError:
                leftover = ''
            for chunk in chunks(itertools.chain(leftover, data),
                                self.chunk_size):
                self.buffer.append(chunk)
        
    def read(self, size=None):
        size = self.chunk_size
        if len(self) < self.chunk_size and (not self.eof):
            raise BufferError("Not enough data available.")
        with self.lock:
            self.length -= size
            return self.buffer.popleft()
    
    def readable(self):
        if len(self) < self.chunk_size:
            return False
        return True
    
    def __len__(self):
        return self.length
    
    def __iter__(self):
        while True:
            yield self.read()
            
    def close(self):
        self.eof = True