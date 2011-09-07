###
### Config
###

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

###
### Database interaction
###

def getCapabilitiesData(dbpool, set_name):
    """This function returns a Deferred that that returns data for
layerset's capabilities.  Data is a two-element tuple, first element
describes layerset, second one is a list of layers.

If layerset does not exists, None is returned."""
    # Having a layersetData, fetch layerset
    def gotLayersetData(lset):
        if lset:
            layerDataDeferred = dbpool.runQuery(
"""SELECT layertree.id, layertree.name, layers.title, layers.abstract,
          layers.name, servers.url, layertree.parent_id, layertree.parent_id,
          layertree.ord, layers.latlngbb, layers.capabilites
  FROM layertree JOIN layerset ON layertree.lset_id = layerset.id
    LEFT JOIN layers ON layertree.layer_id = layers.id
    LEFT JOIN servers ON layers.server_id = servers.id
  WHERE layerset.name = %s AND NOT layertree.hidden AND (layers.available OR layers.available IS NULL)
ORDER BY parent_id ASC, ord DESC""", (set_name,))
            # Return a tuple: lset info, layers info
            layerDataDeferred.addCallback(lambda (layers): (lset[0], layers))
            return layerDataDeferred
        else:
            # Layerset does not exist, return None
            return None

    # Get layerset info: name, title, abastract, author name
    layersetDataDeferred = dbpool.runQuery(
"""SELECT layerset.name, title, abstract, users.username FROM layerset JOIN users ON users.id = layerset.author_id WHERE layerset.name = %s
""", (set_name,))
    # Fetch layers in the layerset and return a tuple (layersetData, layerdata)
    layersetDataDeferred.addCallback(gotLayersetData)
    return layersetDataDeferred


def getLayerData(dbpool, set, layers):
    """Return Deferred for layers' information fetched from database."""
    layerData = dbpool.runQuery(
"""SELECT layertree.name, layers.name, servers.url, servers.id, servers.login, servers.passwd
  FROM layertree JOIN layerset ON layertree.lset_id = layerset.id
    LEFT JOIN layers ON layertree.layer_id = layers.id
    LEFT JOIN servers ON layers.server_id = servers.id
  WHERE layerset.name = %s AND layertree.name = ANY(%s)""", (set, layers))
    return layerData
    
