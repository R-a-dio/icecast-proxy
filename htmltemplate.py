#!/usr/bin/python

import cgi

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
table{border: 1px solid #999;border-right:0;border-bottom:0;}
td, th{border-bottom:1px solid #ccc;border-right:1px solid #eee;padding: .2em .5em;}
form{margin:0;padding:0;}
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
    
    kuma = Data(IcyClient(None, '/main.mp3', 'kumakun', 'BASS/2.2.1', 'Kuma\'s Friday Stream'))
    skye = Data(IcyClient(None, '/main.mp3', 'skye', 'WinAmpMPEG/3.2 System', 'Skyejack'))
    
    main.sources.append(kuma)
    main.sources.append(skye)
    main.saved_metadata[kuma] = u'yana - \u30aa\u30ba\u30cd\u30a4\u30fb\u30cf\u30de\u30f3\u306f\u3082\u3046\u3044\u3089\u306a\u3044'
    main.saved_metadata[skye] = u'Fukkireta'
    
    vin = Data(IcyClient(None, '/test.mp3', 'Vin', 'Stemekdk', 'Vin\'s Stream'))
    
    test.sources.append(vin)
    test.saved_metadata[vin] = u'Testing testing - testing'
    
    context['/main.mp3'] = main
    context['/test.mp3'] = test
    
    
    html = HTMLTag('html')
    head = HTMLTag('head')
    body = HTMLTag('body')
    html.append(head)\
        .append(body)
    
    head.append(HTMLTag('title', 'Icecast Proxy'))\
        .append(HTMLTag('style', basic_css, type='text/css'))
    
    body.append(HTMLTag('h3', 'Icecast Proxy'))
    
    for mount in context:
        table = HTMLTag('table', width='800px', cellspacing='0', cellpadding='2')
        body.append(table)
        # mount header
        table.append(HTMLTag('tr').append(HTMLTag('td', colspan='5').append(HTMLTag('b', mount))))
        # subtitle header
        tr_sh = HTMLTag('tr')\
             .append(HTMLTag('td').append(HTMLTag('b', 'Username')))\
             .append(HTMLTag('td').append(HTMLTag('b', 'Metadata')))\
             .append(HTMLTag('td').append(HTMLTag('b', 'Useragent')))\
             .append(HTMLTag('td').append(HTMLTag('b', 'Stream name')))\
             .append(HTMLTag('td', width='100px').append(HTMLTag('b', 'Kick')))
        table.append(tr_sh)
        for i, source in enumerate(context[mount].sources):
            metadata = context[mount].saved_metadata.get(source, u'')
            tr = HTMLTag('tr')\
                .append(HTMLTag('td', source.info.user))\
                .append(HTMLTag('td', metadata))\
                .append(HTMLTag('td', source.info.useragent))\
                .append(HTMLTag('td', source.info.stream_name))\
                .append(HTMLTag('td')\
                    .append(HTMLTag('form', action='', method='GET')\
                        .append(HTMLTag('input', type='hidden', name='mount', value=mount))\
                        .append(HTMLTag('input', type='hidden', name='num', value=str(i)))\
                        .append(HTMLTag('input', type='submit', value='Kick', disabled='disabled'))))
            table.append(tr)
            
    
    
    f = open('abc.html', 'w')
    f.write(html.generate())
