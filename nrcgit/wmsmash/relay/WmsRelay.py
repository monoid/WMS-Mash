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

SERVER_AGENT = 'WMS-Mash/0-dev'

###
### Database interaction
###

DBPOOL = None # TODO Global variables are BAD!

def getCapabilitiesData(set):
    # Having a layersetData, fetch layerset
    def gotLayersetData(lset):
        if lset:
            layerDataDeferred = DBPOOL.runQuery(
"""SELECT layertree.id, layertree.name, layers.title, layers.abstract,
          layers.name, servers.url, layertree.parent_id, layertree.parent_id,
          layertree.ord, layers.latlngbb, layers.capabilites
  FROM layertree JOIN layerset ON layertree.lset_id = layerset.id
    LEFT JOIN layers ON layertree.layer_id = layers.id
    LEFT JOIN servers ON layers.server_id = servers.id
  WHERE layerset.name = %s ORDER BY parent_id ASC, ord ASC""", (set,))
            # Return tuple
            layerDataDeferred.addCallback(lambda (layers): (lset[0], layers))
            return layerDataDeferred
        else:
            # Layerset does not exist, return None
            return None

    # Get layerset info: name, title, abastract, author name
    layersetDataDeferred = DBPOOL.runQuery(
"""SELECT layerset.name, title, abstract, users.username FROM layerset JOIN users ON users.id = layerset.author_id WHERE layerset.name = %s
""", (set,))
    # Fetch layers in the layerset and return a tuple (layersetData, layerdata)
    layersetDataDeferred.addCallback(gotLayersetData)
    return layersetDataDeferred


# TODO: handle multiple layers
def getLayerData(set, layer):
    """Return Deferred for information on the layer from the set
fetched from database."""
    layerData = DBPOOL.runQuery(
"""SELECT layers.name, servers.url
  FROM layertree JOIN layerset ON layertree.lset_id = layerset.id
    LEFT JOIN layers ON layertree.layer_id = layers.id
    LEFT JOIN servers ON layers.server_id = servers.id
  WHERE layerset.name = %s AND layertree.name = %s LIMIT 1""", (set, layer))
    return layerData
    

###
### Handling requests etc
###
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

class WmsSimpleClient(HTTPClient):
    """
    Very simple WMS GetMap/GetFeatureInfo query: no composing, no SLD.

    The class may be used for querying multiple layers if they
    originate from single server and have not SLD.  Otherwise more
    complex composing client has to be used.
    """
    def __init__(self, remote, params, father):
        parsed = urlparse.urlparse(remote)

        self.father = father
        self.remote = remote
        self.params = params
	del params['SET']
        # TODO: this should be handled carefully
        self.rest = parsed.path+'?'+Wms.wmsBuildQuery(params)
        self.host = parsed.netloc.split(':')[0]
        self._fatherFinished = False

        def notifyFinishErr(e):
            self._fatherFinished = True
            self.transport.loseConnection()

        self.father.setHeader('Server', SERVER_AGENT)
        self.father.notifyFinish().addErrback(notifyFinishErr)

    def connectionMade(self):
        self.sendCommand('GET', self.rest)
        self.sendHeader('Host', self.host)
        self.sendHeader('User-Agent', SERVER_AGENT)
        self.endHeaders()

    def handleStatus(self, versio, code, message):
        self.father.setResponseCode(int(code), message)

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


class WmsRelayClientFactory(ClientFactory):
    """
    Used by ProxyRequest to implement a simple web proxy.
    """

    # Param list will be extended, because different types of request
    # have different arguments (complex GetMap and GetFeatureInfo have
    # list of urls and list of layers).  You may think this is a stub
    def __init__(self, url, params, father, proto):
        self.url = url
        self.params = params
        self.father = father
        self.protocol = proto

    def buildProtocol(self, addr):
        return self.protocol(self.url, self.params, self.father)

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
        def reportCapabilites(data):
            if (data is None):
                self.setResponseCode(404, "Layerset %s not found" % saxutils.escape(qs['SET']))
                self.finish()
                return

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
    <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="%s"/>
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
""" % (saxutils.escape(qs['SET']),
       saxutils.escape("http://localhost:8080/virtual?Set=Academgorodok"), # TODO
       ))
            buf = cStringIO.StringIO()
            (r, lrs, ld) = nrcgit.wmsmash.core.Layer.buildTree(reversed(data[1]))
            r.dump(buf)
            self.write(buf.getvalue())
            buf.close()
            self.write("""</Capability></WMT_MS_Capabilities>""")
            self.finish()
        
        layersetDataDeferred = getCapabilitiesData(qs['SET'])
        layersetDataDeferred.addCallbacks(
            reportCapabilites,
            lambda x: self.reportWmsError("DB error"+str(x), "DbError"))

    def handleGetMap(self, layerset, qs):
        layers = qs['LAYERS']
        if len(layers) == 1:
            layerDataDeferred = getLayerData(qs['SET'], qs['LAYERS'][0])
            def getData(data):
                # TODO: check data is not empty
                data = data[0]
                url = data[1]
                parsed = urlparse.urlparse(url)
                rest = urlparse.urlunparse(('', '') + parsed[2:])
                qs['LAYERS'] = data[0]
                if not rest:
                    rest = rest + '/'
                class_ = WmsRelayClientFactory
                host_split = parsed.netloc.split(':')
                host = host_split[0]
                port = 80 # TODO STUB parse, parse, parse
                clientFactory = class_(url, qs, self, WmsSimpleClient)
                
                self.reactor.connectTCP(host, port, clientFactory)
            layerDataDeferred.addCallback(getData)
        
        
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
                    return self.handleGetMap(layerset, qs)
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
        
