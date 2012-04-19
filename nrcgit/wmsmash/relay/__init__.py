from twisted.internet import defer
import hashlib

def check_django_pwd(enc_pass, raw_pass):
    """ Compare raw pass' hash with encoded Django password
(SHA1-only) in enc_pass."""
    algo, salt, hsh = enc_pass.split('$')
    if algo == 'sha1':
        sha = hashlib.sha1()
        sha.update(salt+raw_pass)
        hx = sha.hexdigest()
        return hsh == hx
    else:
        return False

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
"""SELECT editor_set.name, title, abstract, auth_user.username, editor_set.id
     FROM editor_set JOIN auth_user ON auth_user.id = editor_set.author_id
   WHERE auth_user.username = %s AND editor_set.name = %s
""", (user, set_name))
    
    # Fetch layers in the layerset and return a tuple (layersetData, layerdata)
    if lset:
        # TODO visible and public fields too, as we need them to
        # reconstruct whole tree.
        layers = yield dbpool.runQuery(
"""SELECT editor_layertree.id, editor_namedlayertree.name,
          editor_layertree.title, editor_layer.abstract, editor_layer.keywords,
          editor_namedlayer.name, editor_server.url,
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


@defer.inlineCallbacks
def getLayerData(dbpool, user, lset_name, layers, auth_user=None, auth_pass=None):
    """Return Deferred both layers' information fetched from database."""

    lset = yield dbpool.runQuery(
"""SELECT editor_set.id, auth_user.username, auth_user.password
     FROM editor_set JOIN auth_user ON auth_user.id = editor_set.author_id
   WHERE auth_user.username = %s AND editor_set.name = %s LIMIT 1
""", (user, lset_name))

    auth = False

    if lset:
        # Authentification
        # Check if user is owner
        if (lset[0][1] == auth_user and check_django_pwd(lset[0][2], auth_pass)):
            auth = True
        else:
            # Check if user is in ACL
            acl = yield dbpool.runQuery(
    """ SELECT auth_user.password FROM auth_user JOIN editor_set_acl ON auth_user.id = editor_set_acl.user_id WHERE editor_set_acl.set_id = %s AND auth_user.username = %s
    """, (lset[0][0], auth_user))
            for (enc_pw,) in acl:
                if check_django_pwd(enc_pw, auth_pass):
                    auth = True
                    break

        layerData = yield dbpool.runQuery(
    """SELECT editor_namedlayertree.name, editor_namedlayer.name, editor_server.url, editor_server.id, editor_server.login, editor_server.passwd, editor_layertree.public <= %s AS auth
      FROM editor_layertree JOIN editor_set ON editor_layertree.lset_id = editor_set.id
        JOIN auth_user ON auth_user.id = editor_set.author_id
        LEFT JOIN editor_namedlayertree ON editor_namedlayertree.id = editor_layertree.named_id
        LEFT JOIN editor_layer ON editor_layertree.layer_id = editor_layer.id
        LEFT JOIN editor_namedlayer ON editor_namedlayer.id = editor_layer.named_id
        LEFT JOIN editor_server ON editor_layer.server_id = editor_server.id
      WHERE auth_user.username = %s AND editor_set.name = %s AND editor_namedlayertree.name = ANY(%s)""", (auth, user, lset_name, layers))
        defer.returnValue(layerData)
    else:
        defer.returnValue(None)
