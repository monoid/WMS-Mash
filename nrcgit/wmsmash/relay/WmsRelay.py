# -*- coding: utf-8 -*-
"""
WMS proxy.  Kind of.

"""
import urlparse

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory

from txpostgres import txpostgres

from nrcgit.wmsmash.core import Wms

DBPOOL = None # TODO Global variables are BAD!

class WmsHandler:
    pass

class GetCapabilitiesHandler(WmsHandler):
    FORMATS = [ 'text/xml' ]
    # Common required parameter SERVICE is excluded 
    REQUIRED = []

class GetDataHandler(WmsHandler):
    FORMATS = [ 'image/png', 'image/png8', 'image/gif', 'image/jpeg', \
                'image/tiff', 'image/tiff8' ]
    REQUIRED = [ 'version', 'layers', 'styles', 'crs', 'bbox', \
                 'width', 'height', 'format' ]

class GetFeatureInfo(WmsHandler):
    # These are formats that can be concatenated
    FORMATS = [ 'text/xml', 'text/plain' ]
    REQUIRED = [ 'version', 'layers', 'styles', 'crs', 'bbox', \
                 'width', 'height', 'query_layers', 'info_format', \
		 'i', 'j' ]

class WmsRelayClient(HTTPClient):
    """
    Used by ProxyClientFactory to implement a simple web proxy.

    @ivar _finished: A flag which indicates whether or not the original request
        has been finished yet.
    """
    _finished = False

    def __init__(self, command, rest, version, headers, data, father):
        self.father = father
        self.command = command
        self.rest = rest
        if "proxy-connection" in headers:
            del headers["proxy-connection"]
        headers["connection"] = "close"
        headers.pop('keep-alive', None)
        self.headers = headers
        self.data = data


    def connectionMade(self):
        self.sendCommand(self.command, self.rest)
        for header, value in self.headers.items():
            self.sendHeader(header, value)
        self.endHeaders()
        self.transport.write(self.data)


    def handleStatus(self, version, code, message):
        self.father.setResponseCode(int(code), message)


    def handleHeader(self, key, value):
        # t.web.server.Request sets default values for these headers in its
        # 'process' method. When these headers are received from the remote
        # server, they ought to override the defaults, rather than append to
        # them.
        if key.lower() in ['server', 'date', 'content-type']:
            self.father.responseHeaders.setRawHeaders(key, [value])
        else:
            self.father.responseHeaders.addRawHeader(key, value)


    def handleResponsePart(self, buffer):
        self.father.write(buffer)


    def handleResponseEnd(self):
        """
        Finish the original request, indicating that the response has been
        completely written to it, and disconnect the outgoing transport.
        """
        if not self._finished:
            self._finished = True
            self.father.finish()
            self.transport.loseConnection()



class WmsRelayClientFactory(ClientFactory):
    """
    Used by ProxyRequest to implement a simple web proxy.
    """

    protocol = WmsRelayClient

    def __init__(self, command, rest, version, headers, data, father):
        self.father = father
        self.command = command
        self.rest = rest
        self.headers = headers
        self.data = data
        self.version = version

    def buildProtocol(self, addr):
        print "addr=", addr
        return self.protocol(self.command, self.rest, self.version,
                             self.headers, self.data, self.father)

    def clientConnectionFailed(self, connector, reason):
        """
        Report a connection failure in a response to the incoming request as
        an error.
        """
        self.father.setResponseCode(501, "Gateway error")
        self.father.responseHeaders.addRawHeader("Content-Type", "text/html")
        self.father.write("<H1>Could not connect</H1>")
        self.father.finish()

class WmsRelayRequest(Request):
    """
    Used by Proxy to implement a simple web proxy.

    @ivar reactor: the reactor used to create connections.
    @type reactor: object providing L{twisted.internet.interfaces.IReactorTCP}
    """

    protocols = {'http': WmsRelayClientFactory}
    ports = {'http': 80}

    def __init__(self, channel, queued, reactor=reactor):
        Request.__init__(self, channel, queued)
        self.reactor = reactor

    @staticmethod
    def canonicializeParams(params):
        result = {}
        for k in params.keys():
            result[k.upper()] = params[k][0]
        return result

    def ensureWms(self, params):
        if (not params.has_key('SERVICE') or params['SERVICE'].upper() != 'WMS'):
            return False
        # 1. Version number negotiation
        # 2. VERSION parameter is mandatory in requests other 
        #    than GetCapabilities
#         if (not params.has_key('VERSION') or params['VERSION'][0:2] != '1.'):
#             return False
        return True

    def getLayers(self, params):
        return params['LAYERS'].split(',')

    def reportWmsError(self, errorMessage, code, locator=None):
        xml = Wms.wmsErrorXmlString(errorMessage, code, locator)
        self.setHeader('Content-type', 'application/vnd.ogc.se_xml')
        self.setHeader('Length', str(len(xml)))
        self.write(xml)
        self.finish()

    def handleGetCapabilities(self, layerset, qs):
        print 'GC'
        print layerset
        print DBPOOL
        pass
        
    def process(self):
        """ TODO: вот тут мы парсим входной запрос,
        0. Переводим запрос в каноническую форму: ключи в верхний регистр.
        1. Это вообще WMS? (SERVICE=WMS, VERSION=1.x)
        2. Определяем тип запроса (REQUEST=GetMap)
        3. Создаём соответсвующий обработчик
        4. Обработчик спрашивает у базы, куда лезть и т.п.
        """

        parsed = urlparse.urlparse(self.uri)
        qs = urlparse.parse_qs(parsed[4])
        qs = WmsRelayRequest.canonicializeParams(qs)

        print qs

        layerset = qs['SET'] # TODO: parse URL instead

        if self.ensureWms(qs):
#             type = qs['REQUEST'].upper()
#             if type == 'GETCAPABILITIES':
#                 return self.handleGetCapabilities(layerset, qs)
#             elif type == 'GETMAP':
#                 layers = self.getLayers(qs)
#             elif type == 'GETFEATUREINFO':
#                 layer = qs['LAYER']
#                 req = qs.copy()
#                 # TODO update req basing on database info
            pass
        else:
            self.reportWmsError("Invalid WMS request", "InvalidRequest")

        self.reportWmsError("Sorry, not implemented yet.", "NotImplemented")
#         protocol = parsed[0]
#         host = parsed[1]
        # Find port used for remote connection:
        # Use default value for protocol or explicitely defined port
#         port = self.ports[protocol]
#         if ':' in host:
#             host, port = host.split(':')
#             port = int(port)
        
#         rest = urlparse.urlunparse(('', '') + parsed[2:])
#         if not rest:
#             rest = rest + '/'
#         class_ = self.protocols[protocol]
#         headers = self.getAllHeaders().copy()
#         if 'host' not in headers:
#             headers['host'] = host
#         self.content.seek(0, 0)
#         s = self.content.read()
#         clientFactory = class_(self.method, rest, self.clientproto, headers,
#                                s, self)

#         self.reactor.connectTCP(host, port, clientFactory)


class WmsRelay(HTTPChannel):
    """
    This class implements a simple web proxy.

    Since it inherits from L{twisted.protocols.http.HTTPChannel}, to use it you
    should do something like this::

        from twisted.web import http
        f = http.HTTPFactory()
        f.protocol = Proxy

    Make the HTTPFactory a listener on a port as per usual, and you have
    a fully-functioning web proxy!
    """
    requestFactory = WmsRelayRequest

class WmsRelayFactory(HTTPFactory):
    protocol = WmsRelay

    def __init__(self):
        HTTPFactory.__init__(self)
        
