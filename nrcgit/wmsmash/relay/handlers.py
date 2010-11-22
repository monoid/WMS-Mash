import urlparse
import cStringIO
import base64

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory
from twisted.internet.defer import Deferred

from PIL import Image

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

    def __init__(self, parent, query):
        WmsQuery.__init__(self, parent, query)

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
                        'title': "Academgorodok",
                        'abstract': "Layers for Academgorodok (Novosibirsk)",
                        'keywords': ["Academgorodok", "ecology"],
                        'url': 'http://localhost:8080/virtual?Set=Academgorodok&SERVICE=WMS'
                        }))
            self.parent.finish()
        
        layersetDataDeferred = relay.getCapabilitiesData(qs['SET'])
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

    def __init__(self, parent, query):
        WmsQuery.__init__(self, parent, query)

    def connectRemoteUrl(self, data, qs, layers, clientFactoryClass):
        url = data[1]
        parsed = urlparse.urlparse(url)
        rest = urlparse.urlunparse(('', '') + parsed[2:])
        qs['LAYERS'] = ','.join(layers)
        if not rest:
            rest = '/'
        host_split = parsed.netloc.split(':')
        host = host_split[0]
        port = (host_split[1] and int(host_split[1])) or 80 # TODO: https
        clientFactory = clientFactoryClass(url, qs, self.parent, data)
        reactor.connectTCP(host, port, clientFactory)
        return clientFactory

    def run(self):
        layers = self.query['LAYERS']
        qs = self.query
        if layers:
            layerDataDeferred = relay.getLayerData(qs['SET'], layers)
            def getSingleData(data):
                pass
            def getMultipleData(data):
                layer_dict = {}
                # Fill dict with data
                for d in data:
                    lset[d[0]] = d
                # Check if all layers are available
                for name in layers:
                    if name not in lset:
                        self.reportWmsError("Layer %s not found." % name,
                                            "LayerNotDefined")
                        return

                width = int(qs['WIDTH'])
                height = int(qs['HEIGHT'])

                if width > MAX_IMG_SIZE or height > MAX_IMG_SIZE:
                    self.reportWmsError("Requested image too large (max %d)" % MAX_IMG_SIZE,
                                        "ImageTooLarge")
                    return

                image = Image.new("RGB", (width, height))
                first = True

                # This loop have to be made asynchronous
                for name in layers:
                    params = qs.copy()
                    if not first:
                        params['TRANSPARENT'] = 'TRUE'
                    first = False
                    params['LAYERS'] = [layer_dict[name][0]]

            if len(layers) == 1:
                layerDataDeferred.addCallback(self._handleSigleServerRequest)
            else:
                layerDataDeferred.addCallback(getMultipleData)

    def _handleSigleServerRequest(self, data):
        layers = self.query['LAYERS']
        qs = self.query
        if data:
            data = data[0]
            self.connectRemoteUrl(data, qs, [data[0]], ProxyClientFactory)
        else:
            self.parent.reportWmsError("Layer %s not found." % qs['LAYERS'][0],
                                       "LayerNotDefined")

    def init(self):
        pass

    def combine(self, newData):
        pass

    def getData(self):
        pass


##
## GetFeatureInfo
##

class GetFeatureInfo(RemoteDataRequest):
    # These are formats that can be concatenated
    # TODO: GML too?
    FORMATS = [ 'text/xml', 'text/plain' ]

    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'QUERY_LAYERS', 'INFO_FORMAT', \
		 'I', 'J' ]

    text = ""
    
    def __init__(self, parent, query):
        RemoteDataRequest.__init__(self, parent, query)

    def init(self):
        self.text = text

    def combine(self, newData):
        self.text += newData

    def getData(self):
        return self.text

##
## GetMap
##
class GetMap(RemoteDataRequest):
    FORMATS = [ 'image/png', 'image/png8', 'image/gif', 'image/jpeg', \
                'image/tiff', 'image/tiff8' ]
    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'FORMAT' ]

    def __init__(self, parent, query):
        RemoteDataRequest.__init__(self, parent, query)


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

    def __init__(self, url, params, father, data):
        self.deferred = Deferred()
        self.url = url
        self.params = params
        self.father = father
        self.data = data
        self.login = self.data[3]
        self.password = self.data[4]
        print data
        self.remote = data[1]

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
                value == 'application/vnd.ogc.wms_xml':
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
    def __init__(self, url, params, father, data):
        DumbHTTPClientFactory.__init__(self, url, params, father, data)
     
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
        self.father.finish()
        return True
                           
