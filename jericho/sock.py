import ssl
import socket
from collections import deque
import errno
from buffer import ChunkBuffer, BufferError

class JerichoSocket(object):
    """A socket.socket wrapper"""
    def __init__(self, sock):
        super(JerichoSocket, self).__init__()
        self.sock = sock
        self.ssl = isinstance(sock, ssl.SSLSocket)
        
        self.write_buffer_open = True
        self.write_buffer = deque()
        self.write_bytes_send = 0
        
        # This is set to a ChunkBuffer after handshaking is finished and
        # we know the actual size needed for reading correctly.
        self.read_buffer = None
        
    def handle_read(self):
        """Called when the socket returns positive reading from
        a select() call. 
        
        This should return 'False' if EOF was detected, otherwise it 
        should return True or an exception if unhandled.
        """
        pass
    
    def handle_write(self):
        """Called when the socket returns positive writing from
        a select() call. 
        
        This should return 'False' if it wants to not be included in 
        any further select() calls. Such as when an exception is unhandled.
        """
        pass
    
    def write(self, data):
        """Called with correct sized chunks of data to be written to
        the socket at the earliest point possible."""
        if self.write_buffer_open:
            self.write_buffer.append(data)
        else:
            raise BufferError("Write buffer is already closed.")
    
    def read(self):
        """Called for reading correct sized chunks of data from the socket
        this should always returns the same sized chunks unless the socket
        got shutdown/closed."""
        if self.buffer is None:
            raise BufferError("Buffer is not yet created.")
        return self.buffer.read()
    
    def sock_read(self, size=4096):
        """Reads from the underlying socket object. Returns data that is at
        most of size `size`. The size can be less."""
        if self.ssl:
            return self.sock.read(size)
        else:
            return self.sock.recv(size)
        
    def sock_write(self, data):
        """Writes to the underlying socket object. Returns the value returned
        from either SSLSocket.write or socket.send. Which is the amount of
        bytes actually send."""
        if self.ssl:
            return self.sock.write(data)
        else:
            return self.sock.send(data)
        
    def fileno(self):
        """Returns the file number of the socket."""
        return self.sock.fileno()
    
    def close(self):
        """Closes any objects required. This is a very lazy close method.
        
        It only closes the read buffer and the write buffer. The actual
        socket is not closed in here."""
        if self.buffer is not None:
            self.buffer.close()
        self.write_buffer_open = False
    
class JerichoSocket(object):
    """Simple wrapper around a socket object to supply client information
    with a socket.
    
    """
    def __init__(self, sock):
        # Set ourself non-blocking right away
        sock.setblocking(0)
        self.sock = sock
        self.ssl = isinstance(sock, ssl.SSLSocket) # SSL used?
        
        self.block = None # Why do I care about a block? don't use this
        
        self.state = None # This is for handshaking purpose... should it be in the class?
        
        self.write_buffer = deque() # Pre-sized chunks of data to write
        self.write_bytes_send = 0 # How much bytes did we write last time
        
        self.closed = False # Did we call close? do we care?
        
    def handle_headers(self, headers, block_store=None):
        # Why is this a socket function
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