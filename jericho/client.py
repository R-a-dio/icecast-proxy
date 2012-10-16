from __future__ import unicode_literals
import socket
import hashlib
import math
import threading
import random
import select
import ssl
from . import JerichoError, chunks
from .buffer import ChunkBuffer
from .block import JerichoBlock
from .sock import JerichoSocket
import handshake

import logging
logger = logging.getLogger(__name__)


handshakes = {
              1: "ix{ix:0=4d}_id{id:0=8d}_pw{pw:s}_bc{bc:0=6d}_am{am:0=4d}"
              }

class JerichoClient(JerichoBlock):
    def __init__(self, host, port=9555, passwd='',
                 amount=4, block_size=1024,
                 ssl=False, version=1):
        if not isinstance(amount, int):
            raise JerichoError("'amount' has to be an integer.")
        uid = random.getrandbits(24)
        super(JerichoClient, self).__init__(uid=uid, amount=amount)

        self.host = host
        self.port = port
        self.ssl = ssl
        self.version = version
        self.amount = 4
        
        self.block_size = block_size
        self.write_buffer = ChunkBuffer(block_size)

        self.passwd = hashlib.sha256(passwd).hexdigest()

        self.running = threading.Event()
        
    def connect(self):
        for index in xrange(self.amount):
            try:
                sock = socket.create_connection((self.host, self.port),
                                            30.0)
            except socket.timeout as err:
                raise JerichoError("Could not connect to host. Socket timeout.")
            else:
                if self.ssl:
                    sock = ssl.wrap_socket(sock)
                sock = JerichoSocket(sock)
                sock.index = index
                self.add(sock, block_size=self.block_size, index=index)
        
        waiting_write = self.sockets[:]
        waiting_read = self.sockets[:]
        while True:
            try:
                readable, writeable, erroring = select.select(waiting_read,
                                                          waiting_write,
                                                          [], 5.0)
            except socket.error as err:
                for sock in waiting_read[:]:
                    try:
                        select.select([sock], [], [], 0)
                    except socket.error as err:
                        waiting_read.remove(sock)
                continue
            for sock in writeable:
                if sock.state in (handshake.SEND, None):
                    if handshake.client_handshake(self, sock):
                        waiting_write.remove(sock)
                        
            for sock in readable:
                if sock.state == handshake.CHECK:
                    logging.debug("Checking")
                    try:
                        ret = handshake.client_handshake(self, sock)
                    except JerichoError:
                        self.close()
                        raise
                    else:
                        if ret:
                            logging.debug("Accepted handshake")
                            waiting_read.remove(sock)
                            
            if (not waiting_read) and (not waiting_write):
                print "Done handshake"
                break
        self.start()
        return self
    
    def run(self):
        read_sockets = self.sockets[:]
        write_sockets = self.sockets[:]
        while not self.running.is_set():
            try:
                readable, writeable, erroring = select.select(read_sockets,
                                                          write_sockets,
                                                          read_sockets + write_sockets,
                                                          5.0)
            except socket.error as err:
                pass
            for sock in readable:
                print "Client", sock
                if sock.handle_read():
                    print "EOF in client socket", getattr(sock, 'index', None)
                    read_sockets.remove(sock)
                
            for sock in writeable:
                sock.handle_write()
                
            for sock in erroring:
                print sock
                
    def start(self):
        self.thread = threading.Thread(target=self.run,
                                       name="JerichoClient {:d}".format(self.uid))
        self.thread.daemon = True
        self.thread.start()
        
    def close(self):
        super(JerichoClient, self).close()
        self.running.set()
        self.thread.join(3.0)
        
class JerichoClientOld(object):
    def __init__(self, host, port=9555, passwd='', amount=4, block_size=1024,
                 ssl=False, version=1):
        super(JerichoClient, self).__init__()
        if not isinstance(amount, int):
            raise JerichoError("'amount' has to be an integer.")
        # generate an UID for uniqueness (this isn't large scale anyway)
        self.uid = random.getrandbits(24)
        self.socket_amount = amount
        self.host = host
        self.port = port
        self.ssl = ssl
        self.version = version
        
        self.passwd = hashlib.sha256(passwd).hexdigest()
        self.chunk_size = block_size * amount
        self.block_size = block_size
        
        self.buffer = buffer.Buffer()
        self.sockets = []
        self.recv_buffer = {}
        
    def create_sockets(self):
        """Creates the required sockets"""
        for index in xrange(self.socket_amount):
            try:
                sock = socket.create_connection((self.host, self.port),
                                            30.0)
            except socket.timeout as err:
                raise JerichoError("Could not connect to host. Socket timeout.")
            else:
                if self.ssl:
                    sock = ssl.wrap_socket(sock)
                self.recv_buffer[sock] = b''
                self.sockets.append(sock)
            
    def write(self, data):
        """Write data to the client buffer and request a send if the length
        is above `self.buffer_size`"""
        self.buffer.write(data)
        if len(self.buffer) >= self.chunk_size:
            self.send_data()

    def create_handshake(self, index):
        """handshakes are encoded in UTF8 and all integer values are encoded
        to their ASCII counterpart unless otherwise noted.
        
        Version 1 of the protocol uses the following headers:
            `ix`: index of this socket in the stream. (4)*
            `id`: a semi-unique identifier this is the same for all sockets
                  of a particuler stream. (8)*
            `pw`: Password used for authentication. (64)*
            `bc`: Size of each chunk on the stream. (6)*
            
        * The number of characters used for this header value.
        """
        handshake = handshakes[self.version].format(
                                                    ix=index,
                                                    id=self.uid,
                                                    pw=self.passwd,
                                                    bc=self.block_size,
                                                    am=self.socket_amount
                                                    )
        handshake = handshake.encode('utf8')
        length = "{length:0=24d}".format(length=len(handshake))
        
        return length.encode('utf8') + handshake
    
    def send_handshake(self):
        """Sends a Jericho handshake over all sockets"""
        for index, sock in enumerate(self.sockets):
            handshake = self.create_handshake(index)
            if self.ssl:
                sock.write(handshake)
            else:
                sock.sendall(handshake)

    def check_handshake(self):
        """Checks if the handshake was accepted by the server."""
        waiting = self.sockets[:]
        timeout = 0
        while waiting and timeout <= self.socket_amount:
            readable, writeable, errors = select.select(waiting,
                                                        [],
                                                        [], 10.0)
            for sock in readable:
                self.recv_buffer[sock] += sock.recv(1024)
                if not self.recv_buffer[sock]:
                    # No data while it says it has some? assume error
                    raise JerichoError("Unexpected socket EOF.")
                else:
                    data = self.recv_buffer[sock]
                    try:
                        data = data.decode('utf8')
                    except UnicodeDecodeError:
                        # Assume incomplete buffer
                        continue
                    else:
                        if '\n' not in data:
                            continue
                        s = data.split('\n', 1)
                        if s[0] == b'ACCEPT':
                            waiting.remove(sock)
                        elif s[0] == b'DECLINED':
                            if '\n' not in s[1]:
                                continue
                            raise JerichoError("Declined from server"
                                               " reason: {:s}".format(s[1][:-1]))
            timeout += 1
        if waiting:
            raise JerichoError("Handshake response timed out.")
        
    def send_data(self):
        """
        Splits `self.buffer` into equal sized strings and sends them
        inverse multiplexed over the sockets.
        """
        data = self.buffer.read(self.chunk_size)
        for sock, chunk in zip(self.sockets, chunks(data, self.block_size)):
            if self.ssl:
                sock.write(chunk)
            else:
                sock.sendall(chunk)

    def connect(self):
        """
        Method to be called when you want to start the client.
        
        This is a simple short hand of several initialization method calls.
        There is rarely a need to call said initialization methods manually.
        
        This will raise a `JerichoError` if anything goes wrong.
        Else it will return `self`.
        """
        self.create_sockets()
        self.send_handshake()
        self.check_handshake()
        return self