from xml.sax import saxutils

def wmsBoolean(val):
    """ Convert WMS boolean value to Python boolean. """
    return val == '1' or str(val).lower() == 'true'

def wmsErrorXmlString(errorMessage, code, locator=None):
    args = ""
    if code:
        args += "code='%s' " % saxutils.escape(code)
    if locator:
        args += "locator='%s'" % saxutils.escape(locator)
    return """<?xml version='1.0' encoding='utf-8'?>
<ServiceExceptionReport version="1.1.1"><ServiceException %s>%s</ServiceException></ServiceExceptionReport>
""" % (args, saxutils.escape(errorMessage))
