import ssl
import socket
from .block import JerichoBlock
from .buffer import ChunkBuffer
from collections import deque

class JerichoSocket(object):
    """Simple wrapper around a socket object to supply client information
    with a socket.
    
    """
    def __init__(self, sock):
        self.sock = sock
        self.ssl = isinstance(sock, ssl.SSLSocket)
        self.block = None
        self.state = None
        self.write_buffer = deque()
        
    def handle_headers(self, headers):
        """Method is called with the headers dict when ready"""
        self.block = JerichoBlock.create_block(headers['uid'],
                                               headers['socket_amount'])
        self.buffer = ChunkBuffer(headers['block_size'])
        self.block.add(self, headers['block_size'], headers['index'])
        
    def handle_read(self):
        """
        Method that is called whenever the socket returns positive on a
        `select.select` call for reading.
        
        NOTE: This is after handshaking is finished.
        
        Reads bytes into the chunk buffer from the underlying socket.
        """
        try:
            data = self.sock_read(4096)
        except socket.error as err:
            self.close()
            return True
        if not data:
            self.close()
            return True
        self.buffer.write(data)
    
    def handle_write(self):
        """
        Method that is called whenever the socket returns positive on a
        `select.select` call for writing.
        
        NOTE: This is after handshaking is finished.
        """
        if self.write_buffer:
            self.sock_write(self.write_buffer.popleft())
    
    def write(self, data):
        """This assumes correct sized blocks to be send"""
        self.write_buffer.append(data)
        
    def read(self):
        """Read data from the chunk buffer.
        
        NOTE: This does not read from the socket directly and will raise a
              `BufferError` if there is not enough data available. Use the
              `readable` method for checking if this will succeed.
        """
        return self.buffer.read()
    
    def readable(self):
        """Returns if you can read from this Socket without exception being
        raised."""
        return self.buffer.readable()
    
    def fileno(self):
        """Returns the file number of the underlying socket object."""
        return self.sock.fileno()
    
    def sock_read(self, size):
        """Reads from the underlying socket object."""
        if self.ssl:
            return self.sock.read(size)
        else:
            return self.sock.recv(size)
        
    def sock_write(self, data):
        """Writes to the underlying socket object."""
        if self.ssl:
            return self.sock.write(data)
        else:
            return self.sock.send(data)
        
    def close(self):
        self.buffer.close()
        self.sock.shutdown(socket.SHUT_RD)
        self.sock.close()
        pass