import unittest
from .. import chunks

class TestChunks(unittest.TestCase):
    def test_leftover_chunks(self):
        string = "aaaabb"
        expect = ('aaaa', 'bb')
        
        self.assertItemsEqual(expect, chunks(string, 4))
        
    def test_chunks(self):
        string = 'a'*1024+'b'*1024+'c'*1024
        expect = ('a'*1024, 'b'*1024, 'c'*1024)
        
        self.assertItemsEqual(expect, chunks(string, 1024))