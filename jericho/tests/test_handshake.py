import unittest
import socket
from .. import handshake
from .. import sock

try:
    socketpair = socket.socketpair
except AttributeError:
    def socketpair():
        listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen.bind(('localhost', 60000))
        listen.listen(1)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('localhost', 60000))
        server, address = listen.accept()
        return client, server
    
class TestClientHandshake(unittest.TestCase):
    pass

class TestServerHandshake(unittest.TestCase):
    def setUp(self):
        self.client, self.server = socketpair()
        self.client = sock.JerichoSocket(self.client)
        self.server = sock.JerichoSocket(self.server)
        self.addCleanup(self.clean)
        
    def test_handshake_partial_length(self):
        self.client.sock_write('{0:0=20d}'.format(0))
        
        self.assertEqual(False, handshake.server_handshake(self.server))
        
    def test_handshake_partial_header(self):
        string = self.generate_handshake()
        string = string[:len(string)/2]
        
        self.client.sock_write(string)
        
        self.assertEqual(False, handshake.server_handshake(self.server))
        
    def test_handshake_full_header(self):
        string = self.generate_handshake()
        
        self.client.sock_write(string)
        
        self.assertEqual(True, handshake.server_handshake(self.server))
        
    def test_handshake_wrong_password(self):
        string = self.generate_handshake()
        
        self.client.sock_write(string)
        
        handshake.server_handshake(self.server, login=lambda x: x == 'world')
        
        self.assertEqual(handshake.DECLINED, self.server.state)
        self.assertEqual(u"Invalid password used.",
                         str(self.server._handshake['error']))
        
    def test_handshake_decline_send(self):
        self.test_handshake_full_header()
        
        self.server._handshake['error'] = handshake.JerichoError("Testing.")
        self.server.state = handshake.DECLINED
        
        self.assertTrue(handshake.server_handshake(self.server,
                                                   kind='write'))

    def test_handshake_accept_send(self):
        self.test_handshake_full_header()
        
        self.assertEqual(handshake.ACCEPTED, self.server.state)
        self.assertTrue(handshake.server_handshake(self.server,
                                                   kind='write'))
        self.assertEqual(handshake.READY, self.server.state)
        
    def generate_handshake(self):
        string = handshake.handshakes[1]
        string = string.format(ix=0,
                               id=0,
                               pw='hello',
                               bc=0,
                               am=4)
        string = '{0:0=24d}'.format(len(string)) + string
        return string
    
    def clean(self):
        self.client.close()
        self.server.close()
        
if __name__ == '__main__':
    unittest.main()