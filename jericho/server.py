"""A Simple protocol implementation to split a payload over multiple sockets.
Also known as inverse multiplexing.

Supplies a client and server implementation."""
import socket
import re
import ssl
import threading
import hashlib
import buffer
import select
from . import JerichoError

import logging
logging.basicConfig(level=logging.DEBUG)


class JerichoServer(threading.Thread):
    def __init__(self, host=None, port=9555, ssl=False, certfile=None):
        super(JerichoServer, self).__init__()
        self.host = host or socket.gethostname()
        self.port = port
        self.ssl = ssl
        if not (ssl and certfile):
            raise JerichoError("SSL Mode requires a certificate file.")
        self.certfile = certfile
        
        self.manager = JerichoManager(self)
        
        self.daemon = True
        self.name = "JerichoServer"
        
    def start(self):
        """Start the server.
        
        Creating a socket, binding it to given address and port.
        
        Listening to socket and starting the server Thread.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.host, self.port))
        self.socket.listen(10)
        if self.ssl:
            self.socket = ssl.wrap_socket(self.socket, certfile=self.certfile)
        super(JerichoServer, self).start()
        return self
    
    def run(self):
        while True:
            try:
                (clientsocket, address) = self.socket.accept()
            except ssl.SSLError as err:
                logging.exception("Client tried to connect without SSL.")
            self.manager.register_socket(clientsocket)
            logging.debug("Accepting socket.")


class JerichoManager(threading.Thread):
    def __init__(self, parent):
        super(JerichoManager, self).__init__()
        self.parent = parent
        
        self.init_clients = []
        self.handshake_clients = []
        self.active_clients = []
        
        self.blocks = []
        
        self.daemon = True
        self.name = "JerichoManager"
        self.start()
        
    def run(self):
        while True:
            readable, writeable, erroring = select.select(
                                                self.init_clients + self.active_clients,
                                                self.handshake_clients,
                                                [], 1.0)
            for sock in readable:
                if sock.state == sock.INIT:
                    if sock.read_handshake():
                        self.init_clients.remove(sock)
                        self.handshake_clients.append(sock)
                elif sock.state == sock.ACCEPTED:
                    sock.handle_read()
                    
            for sock in writeable:
                try:
                    sock.verify_handshake()
                except JerichoError as err:
                    if sock.decline_handshake(err.message):
                        self.handshake_clients.remove(sock)
                else:
                    if sock.accept_handshake():
                        self.handshake_clients.remove(sock)
                        self.active_clients.append(sock)
                        
    def register_socket(self, sock):
        self.init_clients.append(JerichoSocket(self, sock))

    def register_block(self, block):
        if not block in self.blocks:
            self.blocks.append(block)
        
    def login(self, pw):
        logging.debug("Checking login.")
        return hashlib.sha256('').hexdigest() == pw
    
class JerichoBlock(object):
    """A block of several JerichoSockets that corrospond to the same UID"""
    blocks = {}
    def __init__(self, uid, amount):
        self.uid = uid
        self.blocks[uid] = self
        self.sockets = [None]*amount
        self.block_size = None
        
    @classmethod
    def create_block(cls, uid, sock_amount=4):
        try:
            return cls.blocks[uid]
        except KeyError:
            block = cls(uid, sock_amount)
            cls.blocks[uid] = block
            return block
    
    def add(self, sock, block_size=1024, index=None):
        if index is None:
            raise JerichoError(u"Missing index on JerichoSocket.")
        if not self.block_size == block_size and self.block_size is not None:
            raise JerichoError(u"Block size invalid.")
        self.block_size = block_size
        self.sockets[index] = sock
        
    def read(self):
        data = []
        if all([sock.readable() for sock in self.sockets]):
            for sock in self.sockets:
                data.append(sock.read())
            return "".join(data)
        else:
            raise JerichoError("Not enough data available.")
    
class JerichoSocket(object):
    """Simple wrapper around a socket object to supply client information
    with a socket.
    
    The following states are used and what they mean.
        INIT: Initializing of the socket. This means we didn't even read
              the handshake length.
        HANDSHAKE: We are waiting for the whole handshake to be send and
                   parsed.
        ACCEPTED: The socket is ready for processing data."""
    INIT = 0
    HANDSHAKE = 1
    ACCEPTED = 2
    DECLINED = 4
    VERIFY = 3
    siblings = {}
    header_parser = re.compile(r'(.{2})(.+?)(?:_|$)')
    def __init__(self, manager, sock):
        self.sock = sock
        self.manager = manager
        self.ssl = isinstance(sock, ssl.SSLSocket)
        self.uid = None
        self.state = self.INIT
        self.buffer = ''
        
    def read_handshake(self):
        """Read the handshake from the other end."""
        logging.debug("Reading handshake.")
        data = self.sock.recv(1024)
        self.buffer = self.buffer + data
        
        if self.state == self.INIT:
            if len(self.buffer) >= 24:
                # We get enough data in a single read for length
                self.handshake_length = int(self.buffer[:24])
            else:
                return False
            self.state = self.HANDSHAKE
        
        if self.state == self.HANDSHAKE:
            # We have the header length now, start handshaking it
            if len(self.buffer) - 24 >= self.handshake_length:
                # We have the whole header now lets parse it
                headers = self.header_parser.findall(
                                     self.buffer[24:24+self.handshake_length]
                                     )
                self.header = dict(headers)
            else:
                return False
            self.state = self.VERIFY
        return True
        
    def verify_handshake(self):
        """Verifies all the required handshake parts are there."""
        logging.debug("Verifying handshake.")
        if getattr(self, 'verified', False):
            return True
        if not self.manager.login(self.header['pw']):
            raise JerichoError(u"Invalid password used.")
        elif not 'ix' in self.header:
            raise JerichoError(u"Invalid handshake, no index value found.")
        elif not 'id' in self.header:
            raise JerichoError(u"Invalid handshake, no UID found.")
        elif not 'bc' in self.header:
            raise JerichoError(u"Invalid handshake, no block size found.")
        elif not 'am' in self.header:
            raise JerichoError(u"Invalid handshake, no block amount found.")
        self.parse_handshake()
        self.verified = True
        return True
    
    def parse_handshake(self):
        """Parses the handshake into attributes and add ourself to a Block"""
        logging.debug("Parsing handshake.")
        self.uid = int(self.header['id'])
        self.index = int(self.header['ix'])
        self.block_size = int(self.header['bc'])
        self.block_amount = int(self.header['am'])
        self.chunkbuffer = buffer.ChunkBuffer(self.block_size)
        self.block = JerichoBlock.create_block(self.uid, self.block_amount)
        self.manager.register_block(self.block)
        self.block.add(self, block_size=self.block_size,
                        index=self.index)
        
    def decline_handshake(self, reason):
        """Declines a handshake with reason `reason`"""
        logging.debug("Declining handshake reason: {:s}".format(reason))
        org_data = u'DECLINED\n{:s}\n'.format(reason).encode('utf8')
        if getattr(self, '_send_bytes', 0):
            data = org_data[self._send_bytes:]
        else:
            data = org_data
            self._send_bytes = 0
        self._send_bytes += self.write(data)
        if self._send_bytes >= len(data):
            del self._send_bytes
            self.state = self.DECLINED
        else:
            return False
        return True
    
    def accept_handshake(self):
        """Accepts a handshake."""
        logging.debug("Accepting handshake.")
        org_data = u'ACCEPT\n'.encode('utf8')
        
        if getattr(self, '_send_bytes', 0):
            data = org_data[self._send_bytes:]
        else:
            data = org_data
            self._send_bytes = 0
        self._send_bytes += self.write(data)
        if self._send_bytes >= len(org_data):
            del self._send_bytes
            self.state = self.ACCEPTED
        else:
            return False
        return True
    
    def handle_read(self):
        """Reads bytes into the chunk buffer from the underlying socket."""
        if self.ssl:
            data = self.sock.read(1024)
        else:
            data = self.sock.recv(1024)
        self.chunkbuffer.write(data)
        
    def write(self, data):
        """Write data to the underlying socket. This abstracts the SSL layer
        if applicable"""
        if self.ssl:
            return self.sock.write(data)
        else:
            return self.sock.send(data)
        
    def read(self):
        """Read data from the chunk buffer.
        
        NOTE: This does not read from the socket directly and will raise a
              `BufferError` if there is not enough data available.
        """
        return self.chunkbuffer.read()
    
    def fileno(self):
        """Returns the file number of the underlying socket object."""
        return self.sock.fileno()