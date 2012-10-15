import re
from . import JerichoError

INIT = 0 # We haven't done anything yet
READ = 1 # We are reading the handshake
PARSE = 2 # We are parsing the handshake
DECLINED = 3 # We declined the handshake
ACCEPTED = 4 # We accepted the handshake
READY = 5 # We are ready for other data
handshake_regex = re.compile(r'(.{2})(.+?)(?:_|$)')
DECLINE_FORMAT = u'DECLINED\n{reason:s}\n'
ACCEPT_FORMAT = u'ACCEPT\n'


def dummy_login(pw):
    """Simple dummy login method, always returns True"""
    return True


def handshake_parser(handshake):
    return handshake_regex.findall(handshake)


def server_handshake(sock, login=dummy_login, kind='read'):
    """Handshake handler for server side sockets. 
    
    Returns False till the whole handshake is read from the other end. 
    
    Returns a header dictionary when successfull.
    """ 
    if not hasattr(sock, '_handshake'):
        sock._handshake = {'buffer': '',
                           'send_bytes': 0}
        sock.state = INIT
    state = sock._handshake
    
    if kind == 'read':
        data = sock.sock_read(1024)
        state['buffer'] += data
        
        if sock.state == INIT:
            if not len(state['buffer']) >= 24:
                return False
            
            state['length'] = int(state['buffer'][:24])
            
            sock.state = READ
                
        if sock.state == READ:
            if not (len(state['buffer']) - 24) >= state['length']:
                return False
            
            headers = handshake_parser(state['buffer'][24:24 + state['length']])
            state['headers'] = dict(headers)
            
            sock.state = PARSE
            
        error = None
        if sock.state == PARSE:
            headers = state['headers']
            
            if (not 'verified' in state) and (not login(headers['pw'])):
                error = JerichoError(u"Invalid password used.")
            else:
                state['verified'] = True
                
            if not 'ix' in headers:
                error = JerichoError(u"Invalid handshake, no index value found.")
            elif not 'id' in headers:
                error = JerichoError(u"Invalid handshake, no UID found.")
            elif not 'bc' in headers:
                error = JerichoError(u"Invalid handshake, no block size found.")
            elif not 'am' in headers:
                error = JerichoError(u"Invalid handshake, no block amount found.")
            else:
                state['uid'] = int(headers['id'])
                state['index'] = int(headers['ix'])
                state['block_size'] = int(headers['bc'])
                state['socket_amount'] = int(headers['am'])
                
                sock.state = ACCEPTED
        if error:
            sock.state = DECLINED
        return True
    else:
        if sock.state == ACCEPTED:
            full_send_data = ACCEPT_FORMAT.encode('utf8')
        elif sock.state == DECLINED:
            full_send_data = DECLINE_FORMAT.format(reason=error.message).encode('utf8')
    
        send_data = full_send_data[state['send_bytes']:]
    
        state['send_bytes'] += sock.sock_write(send_data)
        
        if not state['send_bytes'] >= len(full_send_data):
            return False
        del sock._handshake # Cleanup the dictionary (ha Python cleaning!)
        sock.state = READY
        return state