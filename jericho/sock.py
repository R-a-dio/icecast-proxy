import ssl
import socket
from collections import deque
import errno
from .block import JerichoBlock
from .buffer import ChunkBuffer


class JerichoSocket(object):
    """Simple wrapper around a socket object to supply client information
    with a socket.
    
    """
    def __init__(self, sock):
        sock.setblocking(0)
        self.sock = sock
        self.ssl = isinstance(sock, ssl.SSLSocket)
        self.block = None
        self.state = None
        self.write_buffer = deque()
        self.write_bytes_send = 0
        self.closed = False
        
    def handle_headers(self, headers, block_store=None):
        """Method is called with the headers dict when ready"""
        self.block = JerichoBlock.create_block(headers['uid'],
                                               headers['socket_amount'],
                                               block_store=block_store)
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
            while True:
                data = self.sock_read(4096)
                if data:
                    self.buffer.write(data)
                else:
                    return True
        except socket.error as err:
            if err.errno == errno.EWOULDBLOCK:
                return False
            else:
                raise
        return False
    
    def handle_write(self):
        """
        Method that is called whenever the socket returns positive on a
        `select.select` call for writing.
        
        NOTE: This is after handshaking is finished.
        """
        while self.write_buffer:
            data = self.write_buffer.popleft()
            try:
                self.write_bytes_send += self.sock_write(data[self.write_bytes_send:])
            except socket.error as err:
                if err.errno == errno.EWOULDBLOCK:
                    break
                else:
                    raise
            finally:
                if len(data) >= self.write_bytes_send:
                    self.write_bytes_send = 0
                else:
                    self.write_buffer.appendleft(data)
        if self.write_buffer:
            self.sock.shutdown(socket.SHUT_WR)
            self.sock.close()
            
    def write(self, data):
        """This assumes correct sized blocks to be send"""
        self.write_buffer.append(data)
        #print "Appending:", len(data)
        
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
        
    def close_buffer(self):
        self.buffer.close()
        
    def close(self):
        if self.closed:
            return
        try:
            self.buffer.close()
        except AttributeError:
            pass
        if self.write_buffer:
            pass#self.sock.shutdown(socket.SHUT_RD)
        else:
            #self.sock.shutdown(socket.SHUT_RDWR)
            pass#self.sock.close()
        self.closed = True