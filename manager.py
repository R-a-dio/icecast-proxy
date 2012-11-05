import MySQLdb
import MySQLdb.cursors
from threading import current_thread
import config
import collections
from jericho.buffer import Buffer


def generate_info(mount):
    return {'host': config.icecast_host,
            'port': config.icecast_port,
            'password': config.icecast_pass,
            'format': config.icecast_format,
            'protocol': config.icecast_protocol,
            'name': config.meta_name,
            'url': config.meta_url,
            'genre': config.meta_genre,
            'mount': mount}
    

class MySQLCursor:
    """Return a connected MySQLdb cursor object"""
    counter = 0
    cache = {}
    def __init__(self, cursortype=MySQLdb.cursors.DictCursor, lock=None):
        threadid = current_thread().ident
        if (threadid in self.cache):
            self.conn = self.cache[threadid]
            self.conn.ping(True)
        else:
            self.conn = MySQLdb.connect(host=config.dbhost,
                                user=config.dbuser,
                                passwd=config.dbpassword,
                                db=config.dbtable,
                                charset='utf8',
                                use_unicode=True)
            self.cache[threadid] = self.conn
        self.curtype = cursortype
        self.lock = lock
    def __enter__(self):
        if (self.lock != None):
            self.lock.acquire()
        self.cur = self.conn.cursor(self.curtype)
        return self.cur
        
    def __exit__(self, type, value, traceback):
        self.cur.close()
        self.conn.commit()
        if (self.lock != None):
            self.lock.release()
        return
    

class IcyManager(object):
    def __init__(self):
        super(IcyManager, self).__init__()
        
        self.context = {}
        
    def login(self, user=None, password=None):
        print "LOGIN", user, password
        if user is None or password is None:
            return False
        if user == 'source':
            try:
                user, password = password.split('|')
            except ValueError as err:
                return False
        with MySQLCursor() as cur:
            cur.execute(("SELECT * FROM users WHERE user=%s "
                         "AND pass=SHA1(%s) AND privileges>2;"),
                        (user, password))
            for row in cur:
                return True
            return False
            
    def register_source(self, mount, source):
        try:
            context = self.context[mount]
        except KeyError:
            context = IcyContext(mount)
            self.context[mount] = context
        context.append(source)
        if not context.icecast.connected():
            self.context.start_icecast()
            
    def remove_source(self, mount, source):
        try:
            context = self.context[mount]
        except KeyError:
            # We can be sure there is no source when the mount is unknown
            pass
        else:
            try:
                context.remove(source)
            except ValueError:
                # Source isn't in the sources list?
                print "UNKNOWN SOURCE TRIED TO BE REMOVED"
            finally:
                if not context.sources:
                    context.stop_icecast()
        
        
class IcyContext(object):
    """A class that is the context of a single icecast mountpoint."""
    def __init__(self, mount):
        super(IcyContext, self).__init__()
        # Create a buffer that always returns an empty string (EOF)
        self.eof_buffer = Buffer()
        self.eof_buffer.close()
        
        self.mount = mount
        self.sources = collections.deque()
        
        self.icecast_info = generate_info(mount)
        self.icecast = icecast.Icecast(self, self.icecast_info)
        
    def append(self, source):
        """Append a source client to the list of sources for this context."""
        self.sources.append(source)
        
    def remove(self, source):
        """Remove a source client of the list of sources for this context."""
        self.sources.remove(source)
        
    @property
    def source(self):
        """Returns the first source in the :attr:`sources`: deque."""
        try:
            return self.sources[0]
        except IndexError:
            return self.eof_buffer
        
    def read(self, size=4096, timeout=None):
        """Reads at most :obj:`size`: of bytes from the first source in the
        :attr:`sources`: deque. 
        
        :obj:`timeout`: is unused in this implementation."""
        return self.source.read(size)
    
    def start_icecast(self):
        """Calls the :class:`icecast.Icecast`: :meth:`icecast.Icecast.start`:
        method of this context."""
        self.icecast.start()
        
    def stop_icecast(self):
        """Calls the :class:`icecast.Icecast`: :meth:`icecast.Icecast.close`:
        method of this context."""
        self.icecast.close()