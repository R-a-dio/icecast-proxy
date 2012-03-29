from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn

class IcyRequestHandler(BaseHTTPRequestHandler):
    def do_SOURCE(self):
        print self.path
        print self.headers
        self.send_response(200)
        self.end_headers()

        while True:
            r = self.rfile.read(1024)
            if (len(r) == 0):
                break
            
    def do_GET(self):
        print self.path
        try:
            login = self.headers['Authorization'].split()[1]
        except (IndexError):
            login = None
        if (self.login(login)):
            print "Logged in correctly"
        else:
            print "Login failed"
            
    def login(self, info):
        if (info == None):
            return False
        user, password = info.decode("base64").split(":")
        
        # Do whatever you want with the info here
        # Return True if successfull else False
        if (user == "source") and (password == "diggernicks"):
            return True
        
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

def run(server=ThreadedHTTPServer,
        handler=IcyRequestHandler):
    address = ('', 4000)
    icy = server(address, handler)
    icy.serve_forever()