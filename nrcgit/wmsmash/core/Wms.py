from xml.sax import saxutils
import urllib

def wmsBoolean(val):
    """ Convert WMS boolean value to Python boolean. """
    return val == '1' or str(val).lower() == 'true'

def wmsErrorXmlString(errorMessage, code):
    args = ""
    if code:
        args += "code='%s' " % saxutils.escape(code)
    return """<?xml version='1.0' encoding='utf-8'?>
<ServiceExceptionReport version="1.1.1"><ServiceException %s>%s</ServiceException></ServiceExceptionReport>
""" % (args, saxutils.escape(errorMessage))

def wmsParseQuery(query_str):
    """Parse WMS HTTP query string."""
    elements = query_str.split("&")
    params = {}
    for el in elements:
        keyval = el.split("=", 1)
        key = keyval[0].upper()
        val = keyval[1]
        if key in [ "LAYERS", "STYLES" ]:
            params[key] = map(urllib.unquote, val.split(","))
        else:
            params[key] = urllib.unquote(val)
        
    return params

def wmsBuildQuery(params):
    """Compose HTTP query string from dictionary params.  If value is array,
it is converted to comma-separated list with elements that will be escaped
by this function.  Otherwise, value is converted to string that will be
escaped by this function.  Key values are escaped too.

Example:
wmsBuildQuery({'QUERY':'GetMap', 'LAYERS':['owl,box','academ'], 'STYLE':['',''] })
=> 'LAYERS=owl%2Cbox,academ&QUERY=GetMap&STYLE=,'
"""
    buf = []

    for key, val in params.items():
        if isinstance(val, list):
            valstr = ','.join(map(urllib.quote, val))
        else:
            valstr = urllib.quote(str(val))
        buf.append(urllib.quote(key)+'='+valstr)
    return '&'.join(buf)
        
