from BaseHTTPandICEServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn, BaseServer
import urlparse
import logging
import manager
import threading
from jericho.buffer import Buffer
import config
import urllib2


MAX_BUFFER = 10488
MAX_DEQUES = 4
logger = logging.getLogger('server')


class IcyClient(object):
    def __init__(self, buffer, mount, user=None, useragent=None):
        self.user = user
        self.useragent = useragent
        self.mount = mount
        self.buffer = buffer
        
    def __repr__(self):
        return "IcyClient(mount={:s}, useragent={:s}, user={:s})".format(
                                                            self.mount,
                                                            self.useragent,
                                                            self.user)
        
        
class IcyRequestHandler(BaseHTTPRequestHandler):
    manager = manager.IcyManager()
    def _get_login(self):
        try:
            login = self.headers['Authorization'].split()[1]
        except (IndexError, KeyError):
            return (None, None)
        else:
            return login.decode("base64").split(":", 1)
        
    def do_SOURCE(self):
        self.useragent = self.headers.get('User-Agent', None)
        self.mount = self.path # oh so simple
        user, password = self._get_login()
        if (self.login(user=user, password=password)):
            self.send_response(200)
        else:
            self.send_response(401)
            self.end_headers()
            return
        if user == 'source':
            # No need to try; except because the self.login makes sure
            # we can split it.
            user, password = password.split('|')
        self.mp3_buffer = Buffer(max_size=MAX_BUFFER,
                                 deques=MAX_DEQUES)
        self.icy_client = IcyClient(self.mp3_buffer,
                                   self.mount,
                                   user=user,
                                   useragent=self.useragent)
        self.manager.register_source(self.icy_client)
        try:
            while True:
                data = self.rfile.read(1024)
                if data == '':
                    break
                self.mp3_buffer.write(data)
        finally:
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
            if parsed_url.path == "/admin/metadata":
                try:
                    mount = parsed_query['mount'][0]
                except KeyError, IndexError:
                    mount = ''
                self.client = IcyClient(None, mount,
                                        user, self.useragent)
                
                song = parsed_query.get('song', None)
                if not song is None:
                    metadata = fix_encoding(song[0])
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
                        logging.warning("Broken pipe exception, ignoring")
                    else:
                        logging.exception("Error in request handler")
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


def fix_encoding(metadata):
    try:
        try:
            return unicode(metadata, 'utf-8', 'strict').strip()
        except (UnicodeDecodeError):
            return unicode(metadata, 'shiftjis', 'replace').strip()
    except (TypeError):
        return metadata.strip()
    
        
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