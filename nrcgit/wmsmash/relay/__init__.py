from twisted.internet import defer

###
### Database interaction
###

@defer.inlineCallbacks
def getCapabilitiesData(dbpool, user, set_name):
    """This function returns a Deferred that that returns data for
layerset's capabilities.  Data is a two-element tuple, first element
describes layerset, second one is a list of layers.

If layerset does not exists, None is returned."""
    # Get layerset info: name, title, abastract, author name
    lset = yield dbpool.runQuery(
"""SELECT editor_set.name, title, abstract, auth_user.username, editor_set.id FROM editor_set JOIN auth_user ON auth_user.id = editor_set.author_id WHERE auth_user.username = %s AND editor_set.name = %s
""", (user, set_name,))
    # Fetch layers in the layerset and return a tuple (layersetData, layerdata)
    if lset:
        # TODO visible and public fields too, as we need them to
        # reconstruct whole tree.
        layers = yield dbpool.runQuery(
"""SELECT editor_layertree.id, editor_namedlayertree.name,
          editor_layertree.title, editor_layer.abstract, editor_namedlayer.name,
          editor_server.url,
          editor_layertree.parent_id, editor_layertree.first_id, editor_layertree.nxt_id,
          editor_layer.latlngbb, editor_layer.capablilities
  FROM editor_layertree
    LEFT JOIN editor_layer ON editor_layertree.layer_id = editor_layer.id
    LEFT JOIN editor_server ON editor_layer.server_id = editor_server.id
    LEFT JOIN editor_namedlayertree ON editor_namedlayertree.id = editor_layertree.named_id
    LEFT JOIN editor_namedlayer ON editor_namedlayer.id = editor_layer.named_id
  WHERE editor_layertree.lset_id = %s 
ORDER BY parent_id ASC, nxt_id DESC""", (lset[0][4],))
        defer.returnValue((lset[0], layers))
    else:
        defer.returnValue(None)

def getLayerData(dbpool, user, lset, layers):
    """Return Deferred for layers' information fetched from database."""
    layerData = dbpool.runQuery(
"""SELECT editor_namedlayertree.name, editor_namedlayer.name, editor_server.url, editor_server.id, editor_server.login, editor_server.passwd
  FROM editor_layertree JOIN editor_set ON editor_layertree.lset_id = editor_set.id
    JOIN auth_user ON auth_user.id = editor_set.author_id
    LEFT JOIN editor_namedlayertree ON editor_namedlayertree.id = editor_layertree.named_id
    LEFT JOIN editor_layer ON editor_layertree.layer_id = editor_layer.id
    LEFT JOIN editor_namedlayer ON editor_namedlayer.id = editor_layer.named_id
    LEFT JOIN editor_server ON editor_layer.server_id = editor_server.id
  WHERE auth_user.username = %s AND editor_set.name = %s AND editor_namedlayertree.name = ANY(%s)""", (user, lset, layers))
    return layerData
    
