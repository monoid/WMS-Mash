from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from twisted.web.resource import Resource
from twisted.web.http import HTTPClient, Request, HTTPChannel, HTTPFactory

from PIL import Image

from nrcgit.wmsmash.core import Wms
import nrcgit.wmsmash.core as core

SERVER_AGENT = 'WMS-Mash/0-dev'

class WmsQuery:
    def __init__(self, parent, query, dbpool):
        self.parent = parent
        self.query = query
        self.dbpool = dbpool

    def isValid(self):
        for k in self.REQUIRED:
            if k not in self.query:
                return False
        return True

    def run(self):
        pass


class GetCapabilities(WmsQuery):
    FORMATS = [ 'text/xml' ]
    # Common required params like SERVICE and REQUEST are checked separately
    REQUIRED = []

    def __init__(self, parent, query, dbpool):
        WmsQuery.__init__(self, parent, query, dbpool)


class GetFeatureInfo(WmsQuery):
    # These are formats that can be concatenated
    # TODO: GML too?
    FORMATS = [ 'text/xml', 'text/plain' ]

    REQUIRED = [ 'version', 'layers', 'styles', 'crs', 'bbox', \
                 'width', 'height', 'query_layers', 'info_format', \
		 'i', 'j' ]
    
    def __init__(self, parent, query, dbpool):
        WmsQuery.__init__(self, parent, query, dbpool)


class GetMap(WmsQuery):
    FORMATS = [ 'image/png', 'image/png8', 'image/gif', 'image/jpeg', \
                'image/tiff', 'image/tiff8' ]
    REQUIRED = [ 'version', 'layers', 'styles', 'crs', 'bbox', \
                 'width', 'height', 'format' ]

    def __init__(self, parent, query, dbpool):
        WmsQuery.__init__(self, parent, query, dbpool)


class MultiServerGetMapFetcher:
    pass


class SimpleGetMapFetcher:
    pass

