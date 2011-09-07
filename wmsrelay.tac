# -*- mode: python -*-
#
# You may run it as twistd -ny wmsrelay.tac

from twisted.application import service, internet

from txpostgres import txpostgres
from nrcgit.wmsmash.relay import WmsRelay


PORT = 8080
IFACE = 'localhost'

application = service.Application("WMSMash Relay")

def startProxy(dbpool):
    factory = WmsRelay.WmsRelayFactory(dbpool)
    server = internet.TCPServer(PORT, factory, interface=IFACE)

    server.setServiceParent(application)
    
dbpool = txpostgres.ConnectionPool('ignored',
                                   user='wms-manager',
                                   database='wmsman',
                                   # You think this is a real password,
                                   # don't you?  You are wrong.
                                   password='KlasckIbIp')
dbpool.start().addCallback(startProxy)
