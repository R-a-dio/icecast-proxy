from . import JerichoError
from .buffer import ChunkBuffer
import logging
logger = logging.getLogger(__name__)

class JerichoBlock(object):
    """A block of several JerichoSockets that corrospond to the same UID"""
    blocks = {}
    def __init__(self, uid, amount):
        self.uid = uid
        self.blocks[uid] = self
        self.sockets = [None]*amount
        self.block_size = None
        self.write_buffer = None
        
    @classmethod
    def create_block(cls, uid, sock_amount=4, block_store=None):
        """Factory function to either create the block and returning it or
        just returning an already existing copy."""
        blocks = cls.blocks if block_store is None else block_store
        try:
            return blocks[uid]
        except KeyError:
            block = cls(uid, sock_amount)
            blocks[uid] = block
            return block
    
    def add(self, sock, block_size=1024, index=None):
        if index is None:
            raise JerichoError(u"Missing index on JerichoSocket.")
        if not self.block_size == block_size and self.block_size is not None:
            raise JerichoError(u"Block size invalid.")
        self.block_size = block_size
        self.chunk_size = block_size*len(self.sockets)
        sock.index = index
        self.sockets[index] = sock
        if not sock.block:
            sock.handle_headers({'uid': self.uid,
                                 'index': index,
                                 'socket_amount': len(self.sockets),
                                 'block_size': block_size})
    def read(self):
        data = []
        while all([sock.readable() for sock in self.sockets]):
            for sock in self.sockets:
                data.append(sock.read())
        if data:
            return "".join(data)
        else:
            raise JerichoError("Not enough data available.")
    
    def readable(self):
        return all([sock.readable() for sock in self.sockets])
    
    def write(self, data):
        if not self.write_buffer:
            self.write_buffer = ChunkBuffer(chunk_size=self.block_size)
        self.write_buffer.write(data)
        print "Writing to write buffer.", len(data)
        print "Buffer status", self.write_buffer.info()
        while len(self.write_buffer) >= self.chunk_size:
            self.handle_write()
        print "Finished calling handle:", len(self.write_buffer)
        
    def handle_write(self):
        #print "Handling write"
        for sock, data in zip(self.sockets, self.write_buffer):
            sock.write(data)
            
    def close(self):
        self.write_buffer.close()
        for sock in self.sockets:
            sock.close_buffer()
        while len(self.write_buffer) > 0:
            self.handle_write()
        print "Finished calling handle (close):", len(self.write_buffer)
        for sock in self.sockets:
            sock.close()
            