import urlparse
import cStringIO
import base64

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory
from twisted.internet.defer import Deferred

from PIL import Image
from PIL import ImageFile

from nrcgit.wmsmash.core import Wms
import nrcgit.wmsmash.core as core
import nrcgit.wmsmash.relay as relay

SERVER_AGENT = 'WMS-Mash/0-dev'

class WmsQuery:
    def __init__(self, parent, query):
        self.parent = parent
        self.query = query

    def isValid(self):
        for k in self.REQUIRED:
            if k not in self.query:
                return False
        return True

    def run(self):
        pass

##
## GetCapabilities
##
class GetCapabilities(WmsQuery):
    FORMATS = [ 'text/xml' ]
    # Common required params like SERVICE and REQUEST are checked separately
    REQUIRED = []

    def __init__(self, parent, query, dbpool):
        WmsQuery.__init__(self, parent, query)
        self.dbpool = dbpool

    def run(self):
        qs = self.query
        layerset = qs['SET'] # TODO: parse URL instead
        def reportCapabilites(data):
            if (data is None):
                self.parent.setResponseCode(404, "Layerset %s not found" % saxutils.escape(qs['SET']))
                self.parent.finish()
                return

            desc, layers = data
            self.parent.setHeader('Content-type', 'application/vnd.ogc.wms_xml')
            buf = cStringIO.StringIO()
            (r, lrs, ld) = core.Layer.buildTree(reversed(layers), desc[1])
            self.parent.write(core.capCapabilitiesString(r, relay.CONFIG, {
                        'title': desc[1],
                        'abstract': desc[2],
                        'keywords': [],
                        'url': 'http://localhost:8080/virtual?Set=%s&SERVICE=WMS' % desc[0]
                        }))
            self.parent.finish()
        
        layersetDataDeferred = relay.getCapabilitiesData(self.dbpool, qs['SET'])
        layersetDataDeferred.addCallbacks(
            reportCapabilites,
            lambda x: self.parent.reportWmsError("DB error"+str(x), "DbError"))
        

class RemoteDataRequest(WmsQuery):
    """Request that fetches data from remote servers, e.g. GetCapabilities
and GetMap.  If single layer is queried or multiple layers from same servers
(not implemented yet), data is just transmitted to client.

If multiple servers are queried, data is fetched from all servers and 
then combined.  In this case, methoid init is called, and then all elements
are combined with combine method sequentially.  If single server is used,
init and combine are not called.
"""
    layers = None

    def __init__(self, parent, query, dbpool):
        WmsQuery.__init__(self, parent, query)
        self.dbpool = dbpool

    def connectRemoteUrl(self, data, qs, layers, clientFactoryClass):
        url = data[2]
        parsed = urlparse.urlparse(url)
        rest = urlparse.urlunparse(('', '') + parsed[2:])
        qs['LAYERS'] = ','.join(layers)
        if not rest:
            rest = '/'
        host_split = parsed.netloc.split(':')
        host = host_split[0]
        port = (host_split[1] and int(host_split[1])) or 80 # TODO: https
        clientFactory = clientFactoryClass(url, qs, self.parent, data, self)
        reactor.connectTCP(host, port, clientFactory)
        return clientFactory.deferred

    def run(self):
        layers = self.query['LAYERS']
        qs = self.query
        if layers:
            layerDataDeferred = relay.getLayerData(self.dbpool, qs['SET'], layers)

            # TODO: group sequence of layers

            # Actually, we have to check number of QUERY_LAYERS in
            # GetFeatureInfo.  Current implementation works too, but
            # negligibly suboptimal.
            #
            if len(layers) == 1:
                layerDataDeferred.addCallback(self._handleSigleServerRequest)
            else:
                layerDataDeferred.addCallback(self._handleMultipleServerRequest)

    def _handleSigleServerRequest(self, data):
        layers = self.query['LAYERS']
        qs = self.query.copy()
        if data:
            data = data[0]
            self.connectRemoteUrl(data, qs, [data[1]], ProxyClientFactory)
        else:
            self.parent.reportWmsError("Layer %s not found." % qs['LAYERS'][0],
                                       "LayerNotDefined")

    def _handleMultipleServerRequest(self, data):
        layers = self.query['LAYERS']
        layer_dict = {}
        # Fill dict with data
        for d in data:
            layer_dict[d[0]] = d
        # Check if all layers are available
        for name in layers:
            if name not in layer_dict:
                self.parent.reportWmsError("Layer %s not found." % name,
                                           "LayerNotDefined")
                return

        self.data = data
        self.init(layer_dict)
        
    def init(self, layer_dict):
        pass

    def combine(self, newData):
        pass

    def getData(self):
        pass

    def handleError(self, err):
        self.parent.reportWmsError("Remote error", "RemoteError")

##
## GetFeatureInfo
##

class GetFeatureInfo(RemoteDataRequest):
    # These are formats that can be concatenated
    # TODO: GML too?
    FORMATS = [ 'text/html', 'text/plain' ]

    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'QUERY_LAYERS', 'INFO_FORMAT', \
		 'I', 'J' ]

    text = ""
    
    def __init__(self, parent, query, dbpool):
        RemoteDataRequest.__init__(self, parent, query, dbpool)

    def init(self, layer_dict):
        def req_gen():
            first = True
            i = 0
            for ln in self.query['QUERY_LAYERS']:
                layer = layer_dict[ln]
                qs = self.query.copy()
                qs['LAYERS'] = layer[1]
                qs['QUERY_LAYERS'] = layer[1]
                # Look for proper style.
                # order and number of elements in QUERY_LAYERS
                # may be absoulutely different from LAYERS/STYLES field,
                # so we do sequential lookup.
                if 'STYLES' in self.query:
                    del qs['STYLES']  # clear old value
                    # len(qs['STYLES']) should be always less then
                    # len(qs['LAYERS']), but anyway...
                    for i in range(0, min(len(self.query['LAYERS']),
                                          len(self.query['STYLES']))):
                        if self.query['LAYERS'][i] == layer[0]:
                            qs['STYLES'] = self.query['STYLES'][i]
                            break # Found

                if not first:
                    qs['TRANSPARENT'] = 'TRUE'
                if ('STYLES' in self.query) and (i < len(self.query['STYLES'])):
                    qs['STYLES'] = self.query['STYLES'][i]

                yield self.connectRemoteUrl(layer, qs, [layer[1]], TextClientFactory)
                first = False
                i += 1
        self.generator = req_gen()
        self.generator.next().addCallbacks(self.combine, self.handleError)

    def combine(self, newData):
        self.text += newData
        try:
            d = self.generator.next()
            d.addCallbacks(self.combine, self.handleError)
            return d
        except StopIteration:
            self.finish()

    def finish(self):
        self.parent.write(self.text)
        self.parent.finish()

##
## GetMap
##

MAX_IMG_SIZE = 2048

class GetMap(RemoteDataRequest):
    FORMATS = [ 'image/png', 'image/gif', 'image/jpeg', 'image/tiff' ]
    OUTPUT_TYPE = {
        'image/png': 'PNG',
        'image/jpeg': 'JPEG',
        'image/tiff': 'TIFF',
    }
    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'FORMAT' ]

    def __init__(self, parent, query, dbpool):
        RemoteDataRequest.__init__(self, parent, query, dbpool)

    def init(self, layer_dict):
        qs = self.query
        width = int(qs['WIDTH'])
        height = int(qs['HEIGHT'])
        if width > MAX_IMG_SIZE or height > MAX_IMG_SIZE:
            self.parent.reportWmsError("Requested image too large (max %d)" % MAX_IMG_SIZE,
                                "ImageTooLarge")
            return

        self.image = Image.new("RGBA", (width, height))
        self.image.format = qs['FORMAT']

        def req_gen():
            first = True
            i = 0
            for l in self.query['LAYERS']:
                layer = layer_dict[l]
                qs = self.query.copy()
                if not first:
                    qs['TRANSPARENT'] = 'TRUE'
                    if qs['FORMAT'] == 'image/jpeg':
                        qs['FORMAT'] = 'image/png'
                    
                if ('STYLES' in self.query) and (i < len(self.query['STYLES'])):
                    qs['STYLES'] = self.query['STYLES'][i]
                yield self.connectRemoteUrl(layer, qs, [layer[1]], ImageClientFactory)
                first = False
                i += 1
        self.generator = req_gen()
        self.generator.next().addCallbacks(self.combine, self.handleError)

    def combine(self, newData):
        if newData.mode != 'RGBA':
            newData = newData.convert("RGBA")
        self.image.paste(newData, mask=newData)

        try:
            d = self.generator.next()
            d.addCallbacks(self.combine, self.handleError)
            return d
        except StopIteration:
            self.finish()

    def finish(self):
        io = cStringIO.StringIO()
        self.image.save(io, GetMap.OUTPUT_TYPE[self.query['FORMAT']])
        data = io.getvalue()
#         self.parent.father.responseHeaders.addRawHeader('Content-type', 'image/png')
#         self.parent.father.responseHeaders.addRawHeader('Content-length', str(len(data)))
        self.parent.write(data)
        self.parent.finish()

##
## Remote connection handling.
##

class DumbHTTPClient(HTTPClient):
    """HTTP client that redirects most calls to factory that should be
subclass of DumbHTTPClientFactory."""
    _fatherFinished = False
    
    def connectionMade(self):
        parsed = urlparse.urlparse(self.factory.remote)
        self._params = self.factory.params.copy()
        del self._params['SET']
        # TODO: this should be handled carefully
        rest = parsed.path+'?'+Wms.wmsBuildQuery(self._params)
        host = parsed.netloc.split(':')[0]
        login = self.factory.login
        password = self.factory.password

        self.sendCommand('GET', rest)
        self.sendHeader('Host', host)
        self.sendHeader('User-Agent', SERVER_AGENT)
        if login and password:
            b64str = base64.encodestring(login+':'+password)[:-1]
            self.sendHeader('Authorization', 'Basic ' + b64str)
        self.endHeaders()
        self.factory.connectionMade()

    def _ebNotifyFinish(self, e):
        self._fatherFinished = True
        self.transport.loseConnection()

    def handleStatus(self, version, code, message):
        code = int(code)
        self.factory.handleStatus(code, message)

    def handleHeader(self, key, value):
        self.factory.handleHeader(key, value)
            
    def handleResponsePart(self, buffer):
        self.factory.handleResponsePart(buffer)
    
    def handleResponseEnd(self):
        self.factory.handleResponseEnd()
        if not self._fatherFinished:
            self.transport.loseConnection()

INIT = 0
DATA = 1
OGC_ERROR = 2
TRANSPORT_ERROR = 3

class DumbHTTPClientFactory(ClientFactory):
    protocol = DumbHTTPClient
    state = INIT
    ogc_buf = None

    deferred = None

    def __init__(self, url, params, father, data, req):
        self.deferred = Deferred()
        self.url = url
        self.params = params
        self.father = father
        self.data = data
        self.login = self.data[4]
        self.password = self.data[5]
        self.req = req
        self.remote = data[2]

    def clientConnectionFailed(self, connector, reason):
        """
        Report a connection failure in a response to the incoming request as
        an error.
        """
        deferred.error((connector, reason))
#         # TODO: different error?
#         self.father.setResponseCode(501, "Gateway error")
#         self.father.responseHeaders.addRawHeader("Content-Type", "text/html")
#         self.father.write("<H1>Could not connect</H1>")
#         self.father.finish()

    def connectionMade(self):
        pass

    def handleStatus(self, code, message):
        pass

    def handleHeader(self, key, value):
        if key.lower() == 'content-type' and \
                value.startswith('application/vnd.ogc.se_xml'):
            self.state = OGC_ERROR
            self.ogc_buf = cStringIO.StringIO()
        else:
            self.handleOtherHeader(key, value)

    def handleResponsePart(self, data):
        if self.state == OGC_ERROR:
            self.ogc_buf.write(data)
        else:
            self.state = DATA
            self.handleData(data)

    def handleData(self, data):
        pass

    def getResult(self):
        pass

    def handleOtherHeader(self, key, value):
        pass

    def handleResponseEnd(self):
        if self.state == OGC_ERROR:
            # TODO proper exception
            self.deferred.errback(self.ogc_buf.getvalue())
        else:
            self.deferred.callback(self.getResult())

##
## Simple proxy client
##

class ProxyClientFactory(DumbHTTPClientFactory):
    """Proxy client factory simply sends headers and data to client.
It works for both GetMap and GetFeatureInfo.
"""
    def __init__(self, url, params, father, data, req):
        DumbHTTPClientFactory.__init__(self, url, params, father, data, req)
    
    def buildProtocol(self, addr):
        proto = DumbHTTPClientFactory.buildProtocol(self, addr)
        self.father.registerProducer(proto, True)
        return proto

    def handleOtherHeader(self, key, value):
       # TODO: handle preset headers
       # t.web.server.Request sets default values for these headers in its
       # 'process' method. When these headers are received from the remote
       # server, they ought to override the defaults, rather than append to
       # them.
       if key.lower() == 'server':
           pass
       elif key.lower() in ['date', 'content-type']:
           self.father.responseHeaders.setRawHeaders(key, [value])
       else:
           self.father.responseHeaders.addRawHeader(key, value)

    def handleData(self, data):
        self.father.write(data)

    def getResult(self):
        self.father.unregisterProducer()
        self.father.finish()
        return True
    # TODO: unregisterProducer

##
## Image client
##

class ImageClientFactory(DumbHTTPClientFactory):
    def __init__(self, url, params, father, data, req):
        DumbHTTPClientFactory.__init__(self, url, params, father, data, req)
        self.img = ImageFile.Parser()

    def handleOtherHeader(self, key, value):
       # TODO: handle preset headers
       # t.web.server.Request sets default values for these headers in its
       # 'process' method. When these headers are received from the remote
       # server, they ought to override the defaults, rather than append to
       # them.
       if key.lower() == 'server':
           pass
       elif key.lower() in ['date', 'content-type']:
           self.father.responseHeaders.setRawHeaders(key, [value])
       else:
           self.father.responseHeaders.addRawHeader(key, value)
       pass

    def handleData(self, data):
        self.img.feed(data)

    def getResult(self):
        return self.img.close()

class TextClientFactory(DumbHTTPClientFactory):
    text = ''

    def handleOtherHeader(self, key, value):
       # TODO: handle preset headers
       # t.web.server.Request sets default values for these headers in its
       # 'process' method. When these headers are received from the remote
       # server, they ought to override the defaults, rather than append to
       # them.
       if key.lower() == 'server':
           pass
       elif key.lower() in ['date', 'content-type']:
           self.father.responseHeaders.setRawHeaders(key, [value])
       else:
           self.father.responseHeaders.addRawHeader(key, value)
       pass

    def handleData(self, data):
        self.text += data

    def getResult(self):
        return self.text
