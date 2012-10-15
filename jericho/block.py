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
    def create_block(cls, uid, sock_amount=4):
        """Factory function to either create the block and returning it or
        just returning an already existing copy."""
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
        self.chunk_size = block_size*len(self.sockets)
        self.sockets[index] = sock
        
    def read(self):
        data = []
        if all([sock.readable() for sock in self.sockets]):
            for sock in self.sockets:
                data.append(sock.read())
            return "".join(data)
        else:
            raise JerichoError("Not enough data available.")
    
    def readable(self):
        return all([sock.readable() for sock in self.sockets])
    
    def write(self, data):
        if not self.write_buffer:
            self.write_buffer = ChunkBuffer(chunk_size=self.block_size)
        self.write_buffer.write(data)
        if len(self.write_buffer) >= self.chunk_size:
            self.handle_write()
    
    def handle_write(self):
        for sock, data in zip(self.sockets, self.write_buffer):
            sock.write(data)
            
    def close(self):
        for sock in self.sockets:
            sock.close()
            