#!/usr/bin/env python
# -*- coding: utf-8 -*-
from txpostgres import txpostgres
from twisted.internet import reactor

from nrcgit.wmsmash.relay import WmsRelay

from twisted.python import log
import sys
log.startLogging(sys.stdout)

def startProxy(db):
    reactor.listenTCP(8080, WmsRelay.WmsRelayFactory())
    
WmsRelay.DBPOOL = txpostgres.ConnectionPool('ignored',
                                   user='wms-manager',
                                   database='wmsman',
                                   # You think this is a real password,
                                   # don't you?  You are wrong.
                                   password='KlasckIbIp')

# start() returns Deferred for pool initialization
WmsRelay.DBPOOL.start().addCallback(startProxy)

reactor.run()
