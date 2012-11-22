import MySQLdb
import MySQLdb.cursors
import config
from threading import current_thread

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
    
class Log(object):
    def __init__(self, client):
        super(Log, self).__init__()
        self.client = client

    def login(self):
        """Adds an entry for logon time of client."""
        pass
    

    def logout(self):
        """Updates logoff time on last logon entry."""
        pass
    
    def live_on(self):
        """Adds an entry on when client went live."""
        pass
    
    def live_off(self):
        """Updates end time of live entry"""
        pass
    
    def metadata(self, metadata):
        """Adds an entry for metadata."""
        pass