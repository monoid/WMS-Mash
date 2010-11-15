# -*- coding: utf-8 -*-
"""
WMS proxy.  Kind of.

"""
import urlparse
from xml.sax import saxutils

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory

from txpostgres import txpostgres
import cStringIO
import base64

from PIL import Image

from nrcgit.wmsmash.core import Wms
import nrcgit.wmsmash.core as core
import nrcgit.wmsmash.relay as relay
import nrcgit.wmsmash.relay.handlers as handlers

SERVER_AGENT = 'WMS-Mash/0-dev'

CONFIG = {
    'contactperson': "Admin",
    'contactorganization': "Admin and sons",
    'contactposition': "CEO",
    'addresstype': "Work",
    'address': "Nowhere lane, 1",
    'city': 'Novosibirsk',
    'stateorprovince': 'Novosibirsk region',
    'postcode': '630090',
    'country': "Russia",
    'contactvoicetelephone': '',
    'contactfacsimiletelephone': '',
    'contactelectronicmailaddress': ''
}

class WmsRelayRequest(Request):
    """
    Used by Proxy to implement a simple web proxy.

    @ivar reactor: the reactor used to create connections.
    @type reactor: object providing L{twisted.internet.interfaces.IReactorTCP}
    """

    def __init__(self, channel, queued, reactor=reactor):
        Request.__init__(self, channel, queued)
        self.reactor = reactor

    def ensureWms(self, params):
        if ('SERVICE' not in params or params['SERVICE'] != 'WMS'):
            return False
	if ('REQUEST' not in params):
	    return False
        # 1. Version number negotiation
        # 2. VERSION parameter is mandatory in requests other 
        #    than GetCapabilities
#         if ('VERSION' not in params or params['VERSION'][0:2] != '1.'):
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

            desc, layers = data
            self.setHeader('Content-type', 'application/vnd.ogc.wms_xml')
            buf = cStringIO.StringIO()
            (r, lrs, ld) = core.Layer.buildTree(reversed(layers), desc[1])
            self.write(core.capCapabilitiesString(r, CONFIG, {
                        'title': "Academgorodok",
                        'abstract': "Layers for Academgorodok (Novosibirsk)",
                        'keywords': ["Academgorodok", "ecology"],
                        'url': 'http://localhost:8080/virtual?Set=Academgorodok&SERVICE=WMS'
                        }))
            self.finish()
        
        layersetDataDeferred = relay.getCapabilitiesData(qs['SET'])
        layersetDataDeferred.addCallbacks(
            reportCapabilites,
            lambda x: self.reportWmsError("DB error"+str(x), "DbError"))

    def handleGetMap(self, layerset, qs):
        handlers.GetMap(self, qs).run()
        
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
        
