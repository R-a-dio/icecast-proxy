import threading
import config
import collections
import logging
import bcrypt
from buffers import Buffer
from audio import icecast
from database import MySQLCursor


logger = logging.getLogger('server.manager')
STuple = collections.namedtuple('STuple', ['buffer', 'info'])
ITuple = collections.namedtuple('ITuple', ['user', 'useragent', 'stream_name'])


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



class IcyManager(object):
    def __init__(self):
        super(IcyManager, self).__init__()

        # : Lock to acquire when fetching a context object.
        self.context_lock = threading.RLock()
        self.context = {}

    def login(self, user=None, password=None, privilege=1):
        if user is None or password is None:
            return False
        if user == 'source':
            try:
                user, password = password.split('|')
            except ValueError as err:
                return False
        with MySQLCursor() as cur:
            cur.execute(("SELECT * FROM users WHERE user=%s "
                         "AND privileges>%s LIMIT 1;"),
                        (user, privilege))
            for row in cur:
                hash = row['pass']
                if bcrypt.hashpw(password, hash) == hash:
                    return True
            return False

    def register_source(self, client):
        """Register a connected icecast source to be used for streaming to
        the main server."""
        with self.context_lock:
            try:
                context = self.context[client.mount]
            except KeyError:
                context = IcyContext(client.mount)
                self.context[client.mount] = context
        with context:
            context.append(client)
            if not context.icecast.connected():
                context.start_icecast()

    def remove_source(self, client):
        """Removes a connected icecast source from the list of tracked
        sources to be used for streaming."""
        with self.context_lock:
            try:
                context = self.context[client.mount]
            except KeyError:
                # We can be sure there is no source when the mount is unknown
                return
        with context:
            try:
                context.remove(client)
            except ValueError:
                # Source isn't in the sources list?
                logger.warning('An unknown source tried to be removed. Logic error')
            finally:
                if not context.sources:
                    context.stop_icecast()

    def send_metadata(self, metadata, client):
        """Sends a metadata command to the underlying correct
        :class:`IcyContext`: class."""
        try:
            self.context[client.mount].send_metadata(metadata, client)
        except KeyError:
            logger.info("Received metadata for non-existant mountpoint %s",
                        client.mount)


class IcyContext(object):
    """A class that is the context of a single icecast mountpoint."""
    def __init__(self, mount):
        super(IcyContext, self).__init__()
        # : Set to last value returned by :attr:`source`:
        self.current_source = None

        # Threading sync lock
        self.lock = threading.RLock()

        # Create a buffer that always returns an empty string (EOF)
        self.eof_buffer = Buffer(1)
        self.eof_buffer.close()

        self.mount = mount
        # : Deque of tuples of the format STuple(source, ITuple(user, useragent, stream_name))
        self.sources = collections.deque()

        self.icecast_info = generate_info(mount)
        self.icecast = icecast.Icecast(self, self.icecast_info)

        self.saved_metadata = {}

    def __enter__(self):
        self.lock.acquire()

    def __exit__(self, type, value, traceback):
        self.lock.release()

    def __repr__(self):
        return "IcyContext(mount={:s}, user count={:d})".format(
                                                                self.mount,
                                                                len(self.sources)
                                                                )

    def append(self, source):
        """Append a source client to the list of sources for this context."""
        source_tuple = STuple(source.buffer, ITuple(source.user,
                                                    source.useragent,
                                                    source.stream_name))
        logger.debug("Adding source '{source:s}' from '{context:s}'".format(
                                           source=repr(source_tuple),
                                           context=repr(self),
                                           ))
        self.sources.append(source_tuple)
        logger.debug("Current sources are '{sources:s}'.".format(
                                              sources=repr(self.sources))
                                              )

    def remove(self, source):
        """Remove a source client of the list of sources for this context."""
        source_tuple = STuple(source.buffer, ITuple(source.user,
                                                    source.useragent,
                                                    source.stream_name))
        logger.debug("Removing source '{source:s}' from '{context:s}'".format(
                                           source=repr(source_tuple),
                                           context=repr(self),
                                           ))
        self.sources.remove(source_tuple)
        logger.debug("Current sources are '{sources:s}'.".format(
                                              sources=repr(self.sources))
                                              )
        # Close our buffer to make sure we EOF
        source_tuple.buffer.close()


    @property
    def source(self):
        """Returns the first source in the :attr:`sources` deque.
        
        If :attr:`sources` is empty it returns :const:`None` instead
        """
        try:
            source = self.sources[0]
        except IndexError:
            logger.debug("Returning EOF in source acquiring.")
            return None
        else:
            if not self.current_source is source:
                logger.info("%s: Changing source from '%s' to '%s'.",
                            self.mount, 'None' if self.current_source is None \
                                        else self.current_source.info.user,
                            source.info.user)
                # We changed source sir. Send saved metadata if any.
                if source in self.saved_metadata:
                    metadata = self.saved_metadata[source]
                    self.icecast.set_metadata(metadata)
                else:
                    # No saved metadata, send an empty one
                    self.icecast.set_metadata(u'')
            self.current_source = source
            return source.buffer

    def read(self, size=4096, timeout=None):
        """Reads at most :obj:`size`: of bytes from the first source in the
        :attr:`sources`: deque. 
        
        :obj:`timeout`: is unused in this implementation."""

        # Acquire source once, then use that one return everywhere else.
        # Classic example of not-being-thread-safe in the old method.
        source = self.source
        while source:
            # Read data from the returned buffer
            data = source.read(size)
            # Refresh our source variable to point to the top source
            source = self.source

            if data == b'':
                # If we got an EOF from the read it means we should check if
                # there is another source available and continue the loop.
                continue
            else:
                # Else we can just return the data we found from the source.
                return data
        # If we got here it means `self.source` returned None and we have no
        # more sources left to read from. So we can return an EOF.
        return b''

    def start_icecast(self):
        """Calls the :class:`icecast.Icecast`: :meth:`icecast.Icecast.start`:
        method of this context."""
        self.icecast.start()

    def stop_icecast(self):
        """Calls the :class:`icecast.Icecast`: :meth:`icecast.Icecast.close`:
        method of this context."""
        self.icecast.close()
        self.current_source = None

    def send_metadata(self, metadata, client):
        """Checks if client is the currently active source on this mountpoint
        and then sends the metadata. If the client is not the active source
        the metadata is saved for if the current source drops out."""
        try:
            source = self.sources[0]
        except IndexError:
            # No source, why are we even getting metadata ignore it
            # By Vin:
            # Some clients send meta slightly before connecting; save the
            # data for a second and attribute it to the next source?
            logger.warning("%s: Received metadata while we have no source.",
                           self.mount)
            return
        if (source.info.user == client.user):
            # Current source send metadata to us! yay
            logger.info("%s:metadata.update: %s", self.mount, metadata)
            self.saved_metadata[source] = metadata
            self.icecast.set_metadata(metadata)  # Lol consistent naming (not)
        else:
            for source in self.sources:
                if (source.info.user == client.user):
                    # Save the metadata
                    logger.info("%s:metadata.save: %s", self.mount, metadata)
                    self.saved_metadata[source] = metadata
