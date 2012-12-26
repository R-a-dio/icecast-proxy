#!/usr/bin/python

import cgi
from cgi import escape as esc

class HTMLTag(object):
    base_string =        "<{tag} {attr}>{content}</{tag}>\n"
    base_string_nocont = "<{tag} {attr} />"
    attr_string =        "{attr}=\"{val}\""
    def __init__(self, tag, text=None, **kwargs):
        self.tag = tag
        self.attributes = kwargs;
        self.content = []
        if text is not None:
            self.content.append(text)
    def append(self, value):
        self.content.append(value)
        return self
    def generate(self):
        gen_content = []
        attrs = []
        
        for c in self.content:
            if type(c) is str:
                gen_content.append(cgi.escape(c))
            elif type(c) is unicode:
                gen_content.append(cgi.escape(c.encode('utf-8')))
            elif isinstance(c, HTMLTag):
                gen_content.append(c.generate())
        for attr in self.attributes:
            if self.attributes[attr]:
                attrs.append(HTMLTag.attr_string.format(attr=attr, val=cgi.escape(self.attributes[attr], True)))
        
        gen_content = "".join(gen_content)
        attrs = " ".join(attrs)
        
        if len(gen_content) > 0:
            return HTMLTag.base_string.format(tag=self.tag, attr=attrs, content=gen_content)
        else:
            return HTMLTag.base_string_nocont.format(tag=self.tag, attr=attrs)
        
        
basic_css = u"""
table{border: 1px solid #999;border-right:0;border-bottom:0;margin-top:4px;}
td, th{border-bottom:1px solid #ccc;border-right:1px solid #eee;padding: .2em .5em;}
form{margin:0;padding:0;}
"""

server_header = u"""
<html>\n<head>\n<title>Icecast Proxy</title>
<style type="text/css">
table{border: 1px solid #999;border-right:0;border-bottom:0;margin-top:4px;}
td, th{border-bottom:1px solid #ccc;border-right:1px solid #eee;padding: .2em .5em;}
form{margin:0;padding:0;}
</style>\n</head>\n<body>
<h3>Icecast Proxy</h3>

"""

mount_header = u"""
<table width="800px" cellspacing="0" cellpadding="2">
<tr>\n<th align="left" colspan="5">{mount}</th>\n</tr>
<tr>\n<th width="80px">Username</th>
<th>Metadata</th>
<th width="150px">Useragent</th>
<th width="150px">Stream name</th>
<th width="50px">Kick</th>\n</tr>

"""

client_html = u"""
<tr>
<td>{user}</td>
<td>{meta}</td>
<td>{agent}</td>
<td>{stream_name}</td>
<td>
<form action="" method="GET">
<input type="hidden" name="mount" value="{mount}" />
<input type="hidden" name="num" value="{num}" />
<input type="submit" value="Kick" {disabled} />
</form>
</td>
</tr>

"""

def test():
    
    class Data(object):
        def __init__(self, client):
            self.info = client
    
    class TestContext(object):
        def __init__(self):
            self.sources = []
            self.saved_metadata = {}
    
    class IcyClient(object):
        def __init__(self, buffer, mount, user=None, useragent=None, stream_name=None):
            self.user = user
            self.useragent = useragent
            self.mount = mount
            self.buffer = buffer
            self.stream_name = stream_name
    
    context = {}
    
    main = TestContext()
    test = TestContext()
    empt = TestContext()
    
    kuma = Data(IcyClient(None, '/main.mp3', 'kumakun', 'BASS/2.2.1', 'Kuma\'s Friday Stream'))
    skye = Data(IcyClient(None, '/main.mp3', 'skye', 'WinAmpMPEG/3.2 System', 'Skyejack'))
    
    main.sources.append(kuma)
    main.sources.append(skye)
    main.saved_metadata[kuma] = u'yana - \u30aa\u30ba\u30cd\u30a4\u30fb\u30cf\u30de\u30f3\u306f\u3082\u3046\u3044\u3089\u306a\u3044'
    main.saved_metadata[skye] = u'Fukkireta & helping? <lel>'
    
    vin = Data(IcyClient(None, '/test.mp3', 'Vin', 'Stemekdk', 'Vin\'s Stream'))
    
    test.sources.append(vin)
    test.saved_metadata[vin] = u'Testing testing - testing'
    
    context['/main.mp3'] = main
    context['/test.mp3'] = test
    context['/empty.mp3'] = empt
    
    
    send_buf = []
    send_buf.append(server_header)
    
    for mount in context:
        if context[mount].sources: # only include if there is a source on there
            send_buf.append(mount_header.format(mount=esc(mount)))
            for i, source in enumerate(context[mount].sources):
                metadata = context[mount].saved_metadata.get(source, u'')
                send_buf.append(client_html.format(\
                    user=esc(source.info.user),
                    meta=esc(metadata),
                    agent=esc(source.info.useragent),
                    stream_name=esc(source.info.stream_name),
                    mount=esc(mount, True),
                    num=i,
                    disabled='disabled'))
            send_buf.append('</table>\n')
    send_buf.append('</body>\n</html>')
    send_buf = u''.join(send_buf)
    send_buf = send_buf.encode('utf-8', 'replace')
    
    
    f = open('abc.html', 'w')
    f.write(send_buf)
