import unittest
from .. import server
import socket
import time


test_port = 9999


class TestServer(unittest.TestCase):
    def setUp(self):
        self.server = server.JerichoServer(port=test_port)
        self.server.start()
        self.addCleanup(self.clean)
        
    def clean(self):
        self.server.close()
        time.sleep(3)
        
    def test_server_accept(self):
        #self.test_listen_normal()
        
        self.client = socket.create_connection((socket.gethostname(), test_port),
                                               30.0)
        
        time.sleep(1.0)
        self.assertTrue(len(self.server.reading_clients) == 2)
        