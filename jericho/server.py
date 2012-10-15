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
        
        self.reading_clients = []
        self.writing_clients = []
        
        self.blocks = []
        
        self.daemon = True
        self.name = "JerichoManager"
        self.start()
        
    def run(self):
        while True:
            readable, writeable, erroring = select.select(
                                                self.reading_clients,
                                                self.writing_clients,
                                                [], 1.0)
            for sock in readable:
                if sock.state == handshake.READY:
                    sock.handle_read()
                else:
                    if handshake.server_handshake(sock, self.login):
                        self.reading_clients.remove(sock)
                        self.writing_clients.append(sock)
                        
            for sock in writeable:
                if sock.state == handshake.READY:
                    sock.handle_write()
                else:
                    response = handshake.server_handshake(sock, kind='write')
                    if not response:
                        continue
                    sock.handle_headers(response)
                    self.writing_clients.remove(sock)
                    self.reading_clients.append(sock)
                        
    def register_socket(self, sock):
        self.reading_clients.append(JerichoSocket(self, sock))

    def register_block(self, block):
        if not block in self.blocks:
            self.blocks.append(block)
        
    def login(self, pw):
        logging.debug("Checking login.")
        return hashlib.sha256('').hexdigest() == pw
    