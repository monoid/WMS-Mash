#!/usr/bin/env python
# -*- coding: utf-8 -*-

#from twisted.internet import epollreactor
#epollreactor.install()

from txpostgres import txpostgres
from twisted.internet import reactor

import nrcgit.wmsmash.relay as relay
from nrcgit.wmsmash.relay import WmsRelay

from twisted.python import log
import sys
log.startLogging(sys.stdout)

if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except:
        PORT = 8080
else:
    PORT = 8080

IFACE='localhost'

def startProxy(db):
    reactor.listenTCP(PORT, WmsRelay.WmsRelayFactory(), interface=IFACE)

relay.DBPOOL = txpostgres.ConnectionPool('ignored',
                                   user='wms-manager',
                                   database='wmsman',
                                   # You think this is a real password,
                                   # don't you?  You are wrong.
                                   password='KlasckIbIp')

# start() returns Deferred for pool initialization
relay.DBPOOL.start().addCallback(startProxy)

reactor.run()
