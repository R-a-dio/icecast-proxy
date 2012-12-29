#!/usr/bin/python

import socket
from BaseHTTPandICEServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn, BaseServer
import urlparse
import logging
import manager
import threading
from jericho.buffer import Buffer
import config
import urllib2
import signal
import collections
from htmltemplate import HTMLTag


socket.setdefaulttimeout(5.0)
MAX_BUFFER = 10488
MAX_DEQUES = 4
logger = logging.getLogger('server')


class IcyClient(object):
    def __init__(self, buffer, mount, user=None, useragent=None, stream_name=None):
        self.user = user
        self.useragent = useragent
        self.mount = mount
        self.buffer = buffer
        self.stream_name = stream_name
        
    def __repr__(self):
        return "IcyClient(mount={:s}, useragent={:s}, user={:s}, streamname={:s})".format(
                                                            self.mount,
                                                            self.useragent,
                                                            self.user,
                                                            self.stream_name)
IcyClient = collections.namedtuple('IcyClient', 
                                   ('buffer', 'mount', 'user', 'useragent', 'stream_name'))

basic_css = u"""
table{border: 1px solid #999;border-right:0;border-bottom:0;margin-top:4px;}
td, th{border-bottom:1px solid #ccc;border-right:1px solid #eee;padding: .2em .5em;}
form{margin:0;padding:0;}
"""


class IcyRequestHandler(BaseHTTPRequestHandler):
    manager = manager.IcyManager()
    def _get_login(self):
        try:
            login = self.headers['Authorization'].split()[1]
        except (IndexError, KeyError):
            return (None, None)
        else:
            return login.decode("base64").split(":", 1)
    
    def _serve_admin(self, url, query, user, password):
        # admin is 4 and higher
        is_admin = self.manager.login(user=user, password=password, privilege=3)
        #disabled = u'disabled' if not is_admin else None
        disabled = u'disabled'
        #TODO kicking. maybe.
        html = HTMLTag('html')
        head = HTMLTag('head')
        body = HTMLTag('body')
        html.append(head)\
            .append(body)
        
        head.append(HTMLTag('title', 'Icecast Proxy'))\
            .append(HTMLTag('style', basic_css, type='text/css'))
        
        body.append(HTMLTag('h3', 'Icecast Proxy'))
        
        for mount in self.manager.context:
            table = HTMLTag('table', width='800px', cellspacing='0', cellpadding='2')
            body.append(table)
            # mount header
            table.append(HTMLTag('tr').append(HTMLTag('th', mount, colspan='5', align='left')))
            # subtitle header
            tr_sh = HTMLTag('tr')\
                 .append(HTMLTag('th', 'Username', width='80px'))\
                 .append(HTMLTag('th', 'Metadata'))\
                 .append(HTMLTag('th', 'Useragent', width='150px'))\
                 .append(HTMLTag('th', 'Stream name', width='150px'))\
                 .append(HTMLTag('th', 'Kick', width='50px'))
            table.append(tr_sh)
            for i, source in enumerate(self.manager.context[mount].sources):
                metadata = self.manager.context[mount].saved_metadata.get(source, u'')
                tr = HTMLTag('tr')\
                    .append(HTMLTag('td', source.info.user))\
                    .append(HTMLTag('td', metadata))\
                    .append(HTMLTag('td', source.info.useragent))\
                    .append(HTMLTag('td', source.info.stream_name))\
                    .append(HTMLTag('td')\
                        .append(HTMLTag('form', action='', method='GET')\
                            .append(HTMLTag('input', type='hidden', name='mount', value=mount))\
                            .append(HTMLTag('input', type='hidden', name='num', value=str(i)))\
                            .append(HTMLTag('input', type='submit', value='Kick', disabled=disabled))))
                table.append(tr)
        send_buf = html.generate()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(send_buf))
            self.end_headers()
            
            self.wfile.write(send_buf)
        except IOError as err:
            logger.exception("Error in request handler")
    
    def do_SOURCE(self):
        self.useragent = self.headers.get('User-Agent', None)
        self.mount = self.path # oh so simple
        self.stream_name = self.headers.get('ice-name', '<Unknown>')
        user, password = self._get_login()
        if (self.login(user=user, password=password)):
            if user == 'source':
                # No need to try; except because the self.login makes sure
                # we can split it.
                user, password = password.split('|')
            logger.info("source: User '%s' logged in correctly.", user)
            self.send_response(200)
            self.end_headers()
        else:
            if user == 'source':
                # We need to try; except here because we can't be certain
                # it contains a | at all.
                try:
                    user, password = password.split('|')
                except ValueError as err:
                    logger.info("source: Failed login, no separator found "
                                "from %s.", str(self.client_address))
                else:
                    logger.info("source: User '%s' failed to login from %s.", 
                                user, str(self.client_address))
            self.send_response(401)
            self.end_headers()
            return

        self.audio_buffer = Buffer(max_size=MAX_BUFFER,
                                 deques=MAX_DEQUES)
        self.icy_client = IcyClient(self.audio_buffer,
                                   self.mount,
                                   user=user,
                                   useragent=self.useragent,
                                   stream_name=self.stream_name)
        self.manager.register_source(self.icy_client)
        try:
            while True:
                data = self.rfile.read(1024)
                if data == '':
                    break
                self.audio_buffer.write(data)
        finally:
            logger.info("source: User '%s' logged off.", user)
            self.manager.remove_source(self.icy_client)
        
    def do_GET(self):
        self.useragent = self.headers.get('User-Agent', None)
        parsed_url = urlparse.urlparse(self.path)
        parsed_query = urlparse.parse_qs(parsed_url.query)
        user, password = self._get_login()
        if user is None and password is None:
            if 'pass' in parsed_query:
                try:
                    user, password = parsed_query['pass'][0].split('|', 1)
                except (ValueError, IndexError, KeyError):
                    user, password = (None, None)
        if (self.login(user=user, password=password)):
            # Since the user and password are raw at this point we fix them up
            # If user is 'source' it means the actual user is still in the
            # password field.
            if user == 'source':
                # No need to try; except because the self.login makes sure
                # we can split it.
                user, password = password.split('|')
            if parsed_url.path == "/proxy":
                self._serve_admin(parsed_url, parsed_query, user, password)
            elif parsed_url.path == "/admin/metadata":
                try:
                    mount = parsed_query['mount'][0]
                except KeyError, IndexError:
                    mount = ''
                self.client = IcyClient(None, mount,
                                        user, self.useragent, None)
                
                song = parsed_query.get('song', None)
                encoding = parsed_query.get('charset', ['latin1'])
                if not song is None:
                    metadata = fix_encoding(song[0], encoding[0])
                    self.manager.send_metadata(metadata=metadata, client=self.client)
                
                # Send a response... although most clients just ignore this.
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/xml")
                    self.send_header("Content-Length", "113")
                    self.end_headers()
        
                    self.wfile.write('<?xml version="1.0"?>\n<iceresponse><message>Metadata update successful</message><return>1</return></iceresponse>')
                except IOError as err:
                    if hasattr(err, 'errno') and err.errno == 32:
                        logger.warning("Broken pipe exception, ignoring")
                    else:
                        logger.exception("Error in request handler")
            elif parsed_url.path == "/admin/listclients":
                auth = "{:s}:{:s}".format('source', config.icecast_pass)
                auth = auth.encode('base64')
                url = urlparse.urlparse('http://{:s}:{:d}/'.format(
                                                                   config.icecast_host,
                                                                   config.icecast_port)
                                        )
                url = url[:2] + parsed_url[2:]
                url = urlparse.urlunparse(url)
                
                request = urllib2.Request(url)
                request.add_header('User-Agent', self.useragent)
                request.add_header('Authorization', 'Basic {:s}'.format(auth))
                
                try:
                    result = urllib2.urlopen(request).read()
                except urllib2.HTTPError as err:
                    self.send_response(err.code)
                    self.end_headers()
                    return
                except urllib2.URLError as err:
                    self.send_reponse(501)
                    self.end_headers()
                    return
                
                result_length = len(result)
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/xml')
                self.send_header('Content-Length', str(result_length))
                self.end_headers()
                
                self.wfile.write(result)
        else:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Icecast2 Proxy"')
            self.end_headers()
            #return
            
    def login(self, user=None, password=None):
        return self.manager.login(user, password)
    
    def log_message(self, *args, **kwargs):
        """Disable logging, we don't need it"""
        pass


def fix_encoding(metadata, encoding):
    """We get passed a byte string and an encoding and have to figure
    out what to do with it in regards to 'fixing' it.
    
    when the encoding = latin1 we can safely assume the client send no
    explicit encoding and we apply the old ugly fix.
    
    when the encoding is anything but latin1 we can safely know the client send
    an explicit encoding and we decode it properly.
    """
    if encoding == 'latin1':
        try:
            try:
                return unicode(metadata, 'utf-8', 'strict').strip()
            except (UnicodeDecodeError):
                return unicode(metadata, 'shiftjis', 'replace').strip()
        except (TypeError):
            return metadata.strip()
    else:
        try:
            return unicode(metadata, encoding).strip()
        except (UnicodeDecodeError):
            # The encoding we got explicitely seems to be wrong
            # We call ourself again with latin1 encoding
            return fix_encoding(metadata, 'latin1')
        
        
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    timeout = 0.5
    def finish_request(self, request, client_address):
        """Finish one request by instantiating RequestHandlerClass."""
        try:
            BaseServer.finish_request(self, request, client_address)
        except (IOError) as err:
            if hasattr(err, 'errno') and err.errno == 32:
                logging.warning("Broken pipe exception, ignoring")
            else:
                logging.exception("Error in request handler")

def run(server=ThreadedHTTPServer,
        handler=IcyRequestHandler,
        continue_running=threading.Event()):
    address = (config.server_address, config.server_port)
    icy = server(address, handler)
    while not continue_running.is_set():
        icy.handle_request()
    icy.shutdown()
    
    
def start():
    global _server_event, _server_thread
    _server_event = threading.Event()
    _server_thread = threading.Thread(target=run, kwargs={'continue_running':
                                                          _server_event})
    _server_thread.daemon = True
    _server_thread.start()
    
def close():
    _server_event.set()
    _server_thread.join(10.0)

if __name__ == "__main__":
    # Setup logging
    stream = logging.StreamHandler()
    logfile = logging.FileHandler(os.path.expanduser('~/logs/proxy.log'),
                                  encoding='utf-8')
    
    formatter = logging.Formatter(
                      '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                      )
    
    # Add the formatters for timestamps
    stream.setFormatter(formatter)
    logfile.setFormatter(formatter)
    
    # And add the handlers to your logger
    logger.addHandler(stream)
    logger.addHandler(logfile)
    
    logger.setLevel(config.logging_level)
    
    import time
    killed = threading.Event()
    def signal_handler(signum, frame):
        close()
        killed.set()
    start()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    while not killed.is_set():
        time.sleep(5)
    
