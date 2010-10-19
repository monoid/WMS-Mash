# -*- coding: utf-8 -*-
"""
WMS proxy.  Kind of.

"""
import urlparse
from xml.sax import saxutils

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory

from txpostgres import txpostgres
import cStringIO

from nrcgit.wmsmash.core import Wms
import nrcgit.wmsmash.core

DBPOOL = None # TODO Global variables are BAD!

class WmsHandler:
    pass

class GetCapabilitiesHandler(WmsHandler):
    FORMATS = [ 'text/xml' ]
    # Common required params like SERVICE and REQUEST are checked separately
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

    def ensureWms(self, params):
        if (not params.has_key('SERVICE') or params['SERVICE'] != 'WMS'):
            return False
	if (not params.has_key('REQUEST')):
	    return False
        # 1. Version number negotiation
        # 2. VERSION parameter is mandatory in requests other 
        #    than GetCapabilities
#         if (not params.has_key('VERSION') or params['VERSION'][0:2] != '1.'):
#             return False
        return True

    def reportWmsError(self, errorMessage, code):
        xml = Wms.wmsErrorXmlString(errorMessage, code)
        self.setHeader('Content-type', 'application/vnd.ogc.se_xml')
        self.setHeader('Length', str(len(xml)))
        self.write(xml)
        self.finish()

    def handleGetCapabilities(self, layerset, qs):
        def gotLayersetData(layersetData):
            if len(layersetData) > 0:
                layerData = DBPOOL.runQuery(
"""SELECT layertree.id, layertree.name, layers.title, layers.abstract,
          layers.name, servers.url, layertree.parent_id, layertree.parent_id,
          layertree.ord, layers.latlngbb, layers.capabilites
  FROM layertree JOIN layerset ON layertree.lset_id = layerset.id
    LEFT JOIN layers ON layertree.layer_id = layers.id
    LEFT JOIN servers ON layers.server_id = servers.id
  WHERE layerset.name = %s ORDER BY parent_id ASC, ord ASC""", (qs['SET'],))
                layerData.addCallback(lambda (layerDat): (layersetData, layerDat))
                return layerData
            else:
                self.setResponseCode(404, "Layerset %s not found" % saxutils.escape(qs['SET']))
                self.finish()
                return None

        layersetData = DBPOOL.runQuery(
"""SELECT layerset.name, title, abstract, users.username FROM layerset JOIN users ON users.id = layerset.author_id WHERE layerset.name = %s
""", (qs['SET'],))
        layersetData.addCallback(gotLayersetData)
            
        def reportCapabilites(data):
            if (data is None): return

            self.setHeader('Content-type', 'application/vnd.ogc.wms_xml')
            self.write("""<?xml version="1.0" encoding="UTF-8"?>
<WMT_MS_Capabilities version="1.1.1" updateSequence="70">
  <Service>
    <Name>OGC:WMS</Name>
    <Title>%s</Title>
    <Abstract>TODO_FROM_CONFIG</Abstract>
    <KeywordList>
      <Keyword>WMS</Keyword>
    </KeywordList>
    <ContactInformation>
      <ContactPersonPrimary>
        <ContactPerson>TODO_FROM_CONFIG</ContactPerson>
        <ContactOrganization>TODO_FROM_CONFIG</ContactOrganization>
      </ContactPersonPrimary>
      <ContactPosition>TODO_FROM_CONFIG</ContactPosition>
      <ContactAddress>
        <AddressType>TODO_FROM_CONFIG</AddressType>
        <Address>TODO_FROM_CONFIG</Address>
        <City>TODO FROM CONFIG</City>
        <StateOrProvince/>
        <PostCode>TOOD_FROM_CONFIG</PostCode>
        <Country>TODO_FROM_CONFIG</Country>
      </ContactAddress>
      <ContactVoiceTelephone>TODO_FROM_CONFIG</ContactVoiceTelephone>
      <ContactFacsimileTelephone/>
      <ContactElectronicMailAddress>TODO_FROM_CONFIG</ContactElectronicMailAddress>
    </ContactInformation>
    <Fees>None</Fees>
    <AccessConstraints>None</AccessConstraints>
  </Service>
  <Capability>
    <Request>
      <GetCapabilities>
        <Format>application/vnd.ogc.wms_xml</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost:8080/virtual?SET=Academgorodok&amp;SERVICE=WMS&amp;"/>
            </Get>
          </HTTP>
        </DCPType>
      </GetCapabilities>
      <GetMap>
        <Format>image/png</Format>
        <Format>image/gif</Format>
        <Format>image/jpeg</Format>
        <Format>image/png8</Format>
        <Format>image/tiff</Format>
        <Format>image/tiff8</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost:8080/virtual?SET=Academgorodok&amp;SERVICE=WMS&amp;"/>
            </Get>
          </HTTP>
        </DCPType>
      </GetMap>
      <GetFeatureInfo>
        <Format>text/plain</Format>
        <Format>text/html</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost:8080/virtual?SET=Academgorodok&amp;SERVICE=WMS&amp;"/>
            </Get>
          </HTTP>
        </DCPType>
      </GetFeatureInfo>
    </Request>
""" % saxutils.escape(qs['SET']))
            buf = cStringIO.StringIO()
            (r, lrs, ld) = nrcgit.wmsmash.core.Layer.buildTree(reversed(data[1]))
            r.dump(buf)
            self.write(buf.getvalue())
            buf.close()
#             self.write("<Layer><Title>Root layer</Title>")
#             for (id, name, parent, layer_id) in data[1]:
#                 if parent is None:
#                     self.write("<Layer>")
#                     if layer_id is None:
#                         self.write("<Title>%s</Title>" % name)
#                     else:
#                         self.write("<Name>%s</Name>" % name)
#                     self.write("</Layer>")
#             self.write("""</Layer>""");
            self.write("""</Capability></WMT_MS_Capabilities>""")
            self.finish()
        
        layersetData.addCallbacks(reportCapabilites, lambda x: self.reportWmsError("DB error"+str(x), "DbError"))
        
    def process(self):
        """ TODO: parsing request
        0. Traslate params to canonic form
        1. Is it a WMS? (SERVICE=WMS, VERSION=1.x)
        2. Check type (REQUEST=GetMap etc)
        3. Create an appropriate handler.
        4. Handler gets data from database and remote servers.
        """

        try:
            parsed = urlparse.urlparse(self.uri)
            qs = Wms.wmsParseQuery(parsed[4])

            layerset = qs['SET'] # TODO: parse URL instead
            
            if self.ensureWms(qs):
                reqtype = qs['REQUEST'].upper()
                if reqtype == 'GETCAPABILITIES':
                    return self.handleGetCapabilities(layerset, qs)
                elif reqtype == 'GETMAP':
                    layers = qs['LAYERS']
                elif reqtype == 'GETFEATUREINFO':
                    layer = qs['LAYER']
                    req = qs.copy()
                    # TODO update req basing on database info
                    pass
            else:
                self.reportWmsError("Invalid WMS request", "InvalidRequest")
            self.reportWmsError("Sorry, not implemented yet.", "NotImplemented")
        except Exception as ex:
            self.reportWmsError("Internal error: %s %s" % (type(ex), ex), "InternalError")
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
        
