import urlparse

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory

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

    def reportWmsError(self, errorMessage, code):
        xml = Wms.wmsErrorXmlString(errorMessage, code)
        self.parent.setHeader('Content-type', 'application/vnd.ogc.se_xml')
        self.parent.setHeader('Length', str(len(xml)))
        self.parent.write(xml)
        self.parent.finish()


class GetCapabilities(WmsQuery):
    FORMATS = [ 'text/xml' ]
    # Common required params like SERVICE and REQUEST are checked separately
    REQUIRED = []

    def __init__(self, parent, query):
        WmsQuery.__init__(self, parent, query)


class GetFeatureInfo(WmsQuery):
    # These are formats that can be concatenated
    # TODO: GML too?
    FORMATS = [ 'text/xml', 'text/plain' ]

    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'QUERY_LAYERS', 'INFO_FORMAT', \
		 'I', 'J' ]
    
    def __init__(self, parent, query):
        WmsQuery.__init__(self, parent, query)


class GetMap(WmsQuery):
    FORMATS = [ 'image/png', 'image/png8', 'image/gif', 'image/jpeg', \
                'image/tiff', 'image/tiff8' ]
    REQUIRED = [ 'VERSION', 'LAYERS', 'STYLES', 'CRS', 'BBOX', \
                 'WIDTH', 'HEIGHT', 'FORMAT' ]

    def __init__(self, parent, query):
        WmsQuery.__init__(self, parent, query)

    def run(self):
        layers = self.query['LAYERS']
        qs = self.query
        if layers:
            layerDataDeferred = relay.getLayerData(qs['SET'], qs['LAYERS'])
            def getSingleData(data):
                if data:
                    data = data[0]
                    url = data[1]
                    parsed = urlparse.urlparse(url)
                    rest = urlparse.urlunparse(('', '') + parsed[2:])
                    qs['LAYERS'] = data[0]
                    if not rest:
                        rest = rest + '/'
                    host_split = parsed.netloc.split(':')
                    host = host_split[0]
                    port = 80 # TODO STUB parse, parse, parse
                    clientFactory = GetMapClientFactory(url, qs, self.parent, GetMapClient, data)
                
                    reactor.connectTCP(host, port, clientFactory)
                else:
                    self.reportWmsError("Layer %s not found." % qs['LAYERS'][0],
                                        "LayerNotDefined")
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
                layerDataDeferred.addCallback(getSingleData)
            else:
                layerDataDeferred.addCallback(getMultipleData)


class MultiServerGetMapFetcher:
    pass


class SimpleGetMapFetcher:
    pass


class GetMapClientFactory(ClientFactory):
    """
    Used by ProxyRequest to implement a simple web proxy.
    """

    # Param list will be extended, because different types of request
    # have different arguments (complex GetMap and GetFeatureInfo have
    # list of urls and list of layers).  You may think this is a stub
    def __init__(self, url, params, father, proto, data):
        self.url = url
        self.params = params
        self.father = father
        self.protocol = proto
        self.data = data
        self.login = self.data[3]
        self.password = self.data[4]
        print data
        self.remote = data[1]

#     def buildProtocol(self, addr):
#         proto = self.protocol()
#         #proto.factory = self
#         return proto

    def clientConnectionFailed(self, connector, reason):
        """
        Report a connection failure in a response to the incoming request as
        an error.
        """
        # TODO: different error?
        self.father.setResponseCode(501, "Gateway error")
        self.father.responseHeaders.addRawHeader("Content-Type", "text/html")
        self.father.write("<H1>Could not connect</H1>")
        self.father.finish()


class GetMapClient(HTTPClient):
    _fatherFinished = False
    father = None
    login = None
    password = None
    _params = None

    def connectionMade(self):
        print self.factory.remote
        parsed = urlparse.urlparse(self.factory.remote)
        self._params = self.factory.params.copy()
        del self._params['SET']
        # TODO: this should be handled carefully
        rest = parsed.path+'?'+Wms.wmsBuildQuery(self._params)
        host = parsed.netloc.split(':')[0]
        login = self.factory.login
        password = self.factory.password

        self.father = self.factory.father
        self.father.setHeader('Server', SERVER_AGENT)
        self.father.notifyFinish().addErrback(self._ebNotifyFinish)

        self.sendCommand('GET', rest)
        self.sendHeader('Host', host)
        self.sendHeader('User-Agent', SERVER_AGENT)
        if login and password:
            b64str = base64.encodestring(login+':'+password)[:-1]
            self.sendHeader('Authorization', 'Basic ' + b64str)
        self.endHeaders()

    def _ebNotifyFinish(self, e):
        self._fatherFinished = True
        self.transport.loseConnection()

    def handleStatus(self, version, code, message):
        code = int(code)
        if code == 401:
            self.father.setResponseCode(403, "Remote access denied.")
        else:
            self.father.setResponseCode(code, message)

    def handleHeader(self, key, value):
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

    def handleResponsePart(self, buffer):
        self.father.write(buffer)
    
    def handleResponseEnd(self):
        if not self._fatherFinished:
            self.father.finish()
            self.transport.loseConnection()
