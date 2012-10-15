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
from .sock import JerichoSocket
import handshake

import logging
logger = logging.getLogger(__name__)


class JerichoServer(threading.Thread):
    def __init__(self, host=None, port=9555, ssl=False, certfile=None):
        super(JerichoServer, self).__init__()
        self.host = host or socket.gethostname()
        self.port = port
        self.ssl = ssl
        if ssl and not certfile:
            raise JerichoError("SSL Mode requires a certificate file.")
        self.certfile = certfile
        
        self.reading_clients = []
        self.writing_clients = []
        
        self.blocks = []
        
        self.daemon = True
        self.name = "JerichoServer"
        self.running = threading.Event()
        
    def start(self):
        """Start the server.
        
        Creating a socket, binding it to given address and port.
        
        Listening to socket and starting the server Thread.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(10)
        if self.ssl:
            self.socket = ssl.wrap_socket(self.socket, certfile=self.certfile)
        self.reading_clients.append(self.socket)
        super(JerichoServer, self).start()
        return self
    
    def run(self):
        print "running"
        while not self.running.is_set():
            readable, writeable, erroring = select.select(
                                                 self.reading_clients,
                                                 self.writing_clients,
                                                 self.reading_clients + self.writing_clients,
                                                 1.0)
            for sock in readable:
                if sock == self.socket:
                    try:
                        (clientsocket, address) = self.socket.accept()
                    except ssl.SSLError as err:
                        logging.exception("SSL Error.")
                    self.register_socket(clientsocket)
                    logging.debug("Accepting socket.")
                elif sock.state == handshake.READY:
                    if sock.handle_read():
                        print "EOF in server socket"
                        self.reading_clients.remove(sock)
                else:
                    logging.debug("Attempting handshake")
                    if handshake.server_handshake(sock, self.login):
                        logging.debug("Handshake read, going to write.")
                        self.reading_clients.remove(sock)
                        self.writing_clients.append(sock)
                        
            for sock in writeable:
                if sock.state == handshake.READY:
                    sock.handle_write()
                else:
                    response = handshake.server_handshake(sock, kind='write')
                    logging.debug(response)
                    if not response:
                        logging.debug("Not all of our response has been sent.")
                        continue
                    sock.handle_headers(response)
                    self.reading_clients.append(sock)
                    self.register_block(sock.block)
                    
            for sock in erroring:
                print sock
                
    def register_socket(self, sock):
        #sock.setblocking(0)
        self.reading_clients.append(JerichoSocket(sock))

    def register_block(self, block):
        logging.debug("Registering new block: {:s}".format(repr(block)))
        if not block in self.blocks:
            self.blocks.append(block)
        
    def login(self, pw):
        logging.debug("Checking login.")
        return hashlib.sha256('').hexdigest() == pw
    
    def close(self):
        self.running.set()
        self.join(3.0)
        self.socket.close()
    