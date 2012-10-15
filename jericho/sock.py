import ssl
from .block import JerichoBlock
from .buffer import ChunkBuffer


class JerichoSocket(object):
    """Simple wrapper around a socket object to supply client information
    with a socket.
    
    """
    def __init__(self, manager, sock):
        self.sock = sock
        self.manager = manager
        self.ssl = isinstance(sock, ssl.SSLSocket)
        self.block = None
        self.state = None
        
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
        data = self.sock_read(1024)
        if data == '':
            pass # handle EOF
        self.buffer.write(data)
    
    def handle_write(self):
        """
        Method that is called whenever the socket returns positive on a
        `select.select` call for writing.
        
        NOTE: This is after handshaking is finished.
        """
        pass
    
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