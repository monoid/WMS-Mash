# -*- coding: utf-8 -*-

from twisted.web.http import HTTPClient
from exml import etree
from twisted.internet import defer

def WmsFetcher(HTTPClient):
    parser = None
    url = None
    tree = None
    deferred = None

    def __init__(self, url):
        self.url = url
        self.deferred = defer.Deferred()

    def getTree(self):
        """Return Deferred for parsed GetCapabilities."""
        return self.deferred

    def connectionMade(self):
        self.parser = etree.XMLParser()

    def handleStatus(self, version, code, message):
        self.deferred.errback((version, code, message))

    def handleResponsePart(self, buffer):
        try:
            parser.feed(buffer)
        except Exception as e:
            self.deferred.errback(e)
            pass

    def handleResponseEnd(self):
        self.tree = self.parser.close()
        self.deferred.callback(self.tree)
        
