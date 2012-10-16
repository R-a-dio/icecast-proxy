import unittest
from .. import client
from .. import server
import time
import socket
import hashlib


test_port = 10000
test_file = "F:/animetitles.dat.gz"
#test_file = __file__

class TestClient(unittest.TestCase):
    def setUp(self):
        self.server = server.JerichoServer(port=test_port)
        self.server.start()
        self.addCleanup(self.clean)
        
    def test_client_connect_to_server(self):
        self.client = client.JerichoClient(socket.gethostname(), port=test_port)
        
        self.assertEqual(self.client, self.client.connect())
        time.sleep(10)
        self.client.close()
        
    def test_client_send_file(self):
        print
        self.client = client.JerichoClient(socket.gethostname(), port=test_port)
        self.client.connect()
        time.sleep(5)
        self.server_block = self.server.blocks[self.client.uid]
        with open(test_file, 'rb') as f:
            contents = f.read()
        self.client.write(contents)
        self.client.close()
        data = []
        timeout = 0
        while timeout < 30:
            try:
                #data.append(self.server_block.read())
                pass
            except client.JerichoError as err:
                if not str(err) == 'Not enough data available.':
                    raise
            time.sleep(1.0)
            timeout += 1
        total_received = 0
        for sock in self.server_block.sockets:
            total_received += sock.buffer.length
            print "S:Socket buffer", sock.index, sock.buffer.length
        print "S:Total:", total_received
        total_received = 0
        for sock in self.client.sockets:
            length = len("".join(sock.write_buffer))
            total_received += length
            print "C:Socket buffer", sock.index, length
        print "C:Total:", total_received
        #print len("".join(data))
        #print client.JerichoBlock.blocks
        self.assertEqual(hashlib.sha1(contents), hashlib.sha1("".join(data)))
        
    def clean(self):
        self.server.close()
        time.sleep(3)
        