import unittest
from .. import client
from .. import server
import time
import socket
import hashlib


test_port = 10000
test_file = __file__

class TestClient(unittest.TestCase):
    def setUp(self):
        self.server = server.JerichoServer(port=test_port)
        self.server.start()
        self.addCleanup(self.clean)
        
    def test_client_connect_to_server(self):
        self.client = client.JerichoClient(socket.gethostname(), port=test_port)
        
        self.assertEqual(self.client, self.client.connect())
        self.client.close()
        
    def test_client_send_file(self):
        print
        self.test_client_connect_to_server()
        time.sleep(5)
        self.server_block = self.server.blocks[0]
        with open(test_file, 'rb') as f:
            contents = f.read()
        self.client.write(contents)
        #self.client.close()
        data = []
        timeout = 0
        while timeout < 10:
            try:
                data.append(self.server_block.read())
            except client.JerichoError as err:
                if not str(err) == 'Not enough data available.':
                    raise
            time.sleep(1.0)
            timeout += 1
        print data
        self.assertEqual(hashlib.sha1(contents), hashlib.sha1("".join(data)))
        
    def clean(self):
        self.server.close()
        time.sleep(3)
        