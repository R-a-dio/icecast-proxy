

class JerichoError(Exception):
    def __init__(self, message):
        super(JerichoError, self).__init__()
        self.message = message
    def __repr__(self):
        return "<JerichoError: {:s}>".format(self.message)
    def __str__(self):
        return self.message
    
def chunks(iterator, size):
    s = "".join(iterator)
    return [s[i:i+size] for i in xrange(0, len(s), size)]