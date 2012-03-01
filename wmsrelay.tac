# -*- mode: python -*-
#
# You may run it as twistd -ny wmsrelay.tac

from twisted.application import service, internet

from txpostgres import txpostgres
from nrcgit.wmsmash.relay import WmsRelay


PORT = 8080
IFACE = 'localhost'

## All members are required, but some can be set to None
SETTINGS = {
    # Always include port into proxy URL
    'proxy': None,
    # 'proxy': 'http://localhost:8888',

    # Base URL format string.  %s is used for layerset name
    # Used in GetCapabilities handler
    'base_url_fmt': 'http://localhost:8080/wm/%s/%s?SERVICE=WMS',
}

WMS_CONFIG = {
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


application = service.Application("WMSMash Relay")

def startProxy(dbpool):
    factory = WmsRelay.WmsRelayFactory(dbpool, cfg=SETTINGS, wmscfg=WMS_CONFIG)
    server = internet.TCPServer(PORT, factory, interface=IFACE)

    server.setServiceParent(application)
    
dbpool = txpostgres.ConnectionPool('ignored',
                                   user='wms-manager',
                                   database='wmsman',
                                   # You think this is a real password,
                                   # don't you?  You are wrong.
                                   password='KlasckIbIp')
dbpool.start().addCallback(startProxy)
