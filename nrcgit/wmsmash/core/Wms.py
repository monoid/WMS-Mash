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
        print key, key in [ "LAYERS", "STYLES", "BBOX", "QUERY_LAYERS" ]
        val = keyval[1]
        if key in [ "LAYERS", "STYLES" ]:
            params[key] = map(urllib.unquote, val.split(","))
        else:
            params[key] = urllib.unquote(val)
        
    return params
