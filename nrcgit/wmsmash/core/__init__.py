from xml.sax import saxutils
import lxml.etree as etree

def parseJuliaLatLngBB(str):
    elts = str.split()
    r = {}
    for e in elts:
        e = e.split('=')
        r[e[0]] = float(e[1])
    return BoundingBox(r)

class BoundingBox:
    bbox = None

    def __init__(self, bbox=None):
        self.bbox = bbox

    def extendBy(self, bb):
        if self.bbox:
            bbox = bb.bbox
            self.bbox['minx'] = min(self.bbox['minx'], bbox['minx'])
            self.bbox['miny'] = min(self.bbox['miny'], bbox['miny'])
            self.bbox['maxx'] = max(self.bbox['maxx'], bbox['maxx'])
            self.bbox['maxy'] = max(self.bbox['maxy'], bbox['maxy'])
        else:
            self.bbox = bb.bbox.copy()

NSMAP = { 'xlink': 'http://www.w3.org/1999/xlink' }

class Layer:
    id = None
    name = None
    title = None
    abstract = None
    keywords = None
    remote_name = None
    remote_url = None
    parent = None
    order = None
    children = None
    latlngbb = None
    cap = None
    
    def __init__(self, dbrec, layerDict=None):
        self.id = dbrec[0]
        self.name = unicode(dbrec[1] or '', 'utf-8') or None
        self.title = unicode(dbrec[2] or '', 'utf-8') or None
        self.abstract = unicode(dbrec[3] or '', 'utf-8')
        self.keywords = map(lambda s: unicode(s, 'utf-8'), dbrec[4] or [])
        self.remote_name = unicode(dbrec[5] or '', 'utf-8') or None
        self.remote_url = dbrec[6]
        self.order = dbrec[8]
        if dbrec[9] is not None:
            self.latlngbb = parseJuliaLatLngBB(dbrec[9])
        else:
            self.latlngbb = BoundingBox()
        if dbrec[10] is not None:
            self.cap = etree.XML(dbrec[10])
        else:
            self.cap = etree.Element("Layer")

        self.cleanCap()

        if layerDict is not None and layerDict.has_key(dbrec[7]):
            self.parent = layerDict[dbrec[7]]
            self.parent.addChild(self)

        self.children = []

        if layerDict is not None:
            layerDict[self.id] = self

    def cleanCap(self):
        layers = self.cap.xpath('/Layer/Layer')
        for l in layers:
            self.cap.remove(l)
        title = self.cap.xpath('/Layer/Title')
        for t in title:
            self.cap.remove(t)
        name = self.cap.xpath('/Layer/Name')
        for n in name:
            self.cap.remove(n)
        abs = self.cap.xpath('/Layer/Abstract')
        for a in abs:
            self.cap.remove(a)
        llbb = self.cap.xpath('/Layer/LatLonBoundingBox')
        for l in llbb:
            self.cap.remove(l)

    def getOrder(self):
        return self.order

    def addChild(self, child):
        self.children.append(child)
        self.children.sort(None, Layer.getOrder)
        if child.latlngbb.bbox:
            self.latlngbb.extendBy(child.latlngbb)

    def isGroup(self):
        return len(self.children) > 0

    def dump(self):
        if self.remote_name is None:
            etree.SubElement(self.cap, 'Title').text = self.name
        else:
            etree.SubElement(self.cap, 'Name').text = self.name
            etree.SubElement(self.cap, 'Title').text = self.title or ""
        etree.SubElement(self.cap, 'Abstract').text = self.abstract or ""
        bb = etree.SubElement(self.cap, 'LatLonBoundingBox')
        for key, val in self.latlngbb.bbox.items():
            bb.attrib[key] = str(val)
        for c in self.children:
            self.cap.append(c.dump())
        return self.cap
#         if self.cap is not None and self.cap.attrib.has_key('cascade'):
#             cascade = int(self.cap.attrib)+1
#         else:
#             cascade = 1
#         if (self.isGroup()):
#             buf.write("<Layer>")
#         else:
#             buf.write("<Layer cascade='%d'>" % cascade)
            
#         if (self.remote_name is None):
#             buf.write("<Title>%s</Title>" % (self.name,))
#         else:
#             buf.write("<Name>%s</Name>" % (self.name,))
#             if (self.title is not None):
#                 buf.write("<Title>%s</Title>" % (self.title,))

#         if (self.abstract is not None):
#             buf.write("<Abstract>%s</Abstract>" % saxutils.escape(self.abstract))
#         # TODO: compute common LatLngBoundingBox for groups
#         if (self.latlngbb.bbox is not None):
#             buf.write('<LatLonBoundingBox minx="%(minx)f" maxx="%(maxx)f" miny="%(miny)f" maxy="%(maxy)f" />' % self.latlngbb.bbox)

#         # TODO: compute common SRS list for groups
#         if (self.cap is not None):
#             for srs in self.cap.xpath('/Layer/SRS'):
#                 buf.write(etree.tostring(srs))
#             for bb in self.cap.xpath('/Layer/BoundingBox'):
#                 buf.write(etree.tostring(bb))
#             for style in self.cap.xpath('/Layer/Style'):
#                 buf.write(etree.tostring(style))

#         for c in self.children:
#             c.dump(buf)
#         buf.write("</Layer>")

    @staticmethod
    def buildTree(records):
        layerDict = {}
        layers = []
        root = Layer((None, 'Root', '', '', [], '', '', None, 0, None, None), layerDict)
        for rec in records:
            l = Layer(rec, layerDict)
            layers.append(l)
        return (root, layers, layerDict)
            
###
### GetCapabilities
###

def capContactInformation(config, version='1.1.1'):
    ci = etree.Element('ContactInformation')

    # ContactPersonPrimary
    cpp = etree.SubElement(ci, 'ContactPersonPrimary')
    etree.SubElement(cpp, 'ContactPerson').text = config['contactperson']
    etree.SubElement(cpp, 'ContactOrganization').text = config['contactorganization']

    # ContactPosition
    etree.SubElement(ci, 'ContactPosition').text = config['contactposition']

    # ContactAddress
    ca = etree.SubElement(ci, 'ContactAddress')
    etree.SubElement(ca, 'AddressType').text = config['addresstype']
    etree.SubElement(ca, 'Address').text = config['address']
    etree.SubElement(ca, 'City').text = config['city']
    etree.SubElement(ca, 'StateOrProvince').text = config['stateorprovince']
    etree.SubElement(ca, 'PostCode').text = config['postcode']
    etree.SubElement(ca, 'Country').text = config['country']

    # ContactVoiceTelephone, ContactFacsimileTelephone,
    # ContactElectronicMailAddress
    etree.SubElement(ci, 'ContactVoiceTelephone').text = config['contactvoicetelephone']
    etree.SubElement(ci, 'ContactFacsimileTelephone').text = config['contactfacsimiletelephone']
    etree.SubElement(ci, 'ContactElectronicMailAddress').text = config['contactelectronicmailaddress']
    return ci

def capGetCapability(layers, config, lset_cfg, version='1.1.1'):
    sub = etree.SubElement
    cap = etree.Element('Capability')
    req = sub(cap, 'Request')
    def capRequest(req, name, formats, url):
        node = sub(req, name)
        for format in formats:
            sub(node, 'Format').text = format
        onlr = etree.Element('OnlineResource', nsmap=NSMAP)
        onlr.set('{http://www.w3.org/1999/xlink}type', 'simple')
        onlr.set('{http://www.w3.org/1999/xlink}href', url+"&") # TODO
        sub(sub(sub(node, 'DCPType'), 'HTTP'), 'Get').append(onlr)
    capRequest(req, 'GetCapabilities',
               ['application/vnd.ogc.wms_xml'],
               lset_cfg['url'])
    capRequest(req, 'GetMap',
               ['image/png', 'image/png8', 'image/gif', 'image/jpeg', 
                'image/tiff', 'image/tiff8'],
               lset_cfg['url'])
    capRequest(req, 'GetFeatureInfo',
               ['text/plain', 'text/html'],
               lset_cfg['url'])
    cap.append(layers.dump())
    return cap
        
    
def capCapabilitiesString(layers, config, lset_cfg, version='1.1.1'):
    root = etree.Element('WMT_MS_Capabilities', version=version)
    service = etree.SubElement(root, 'Service')
    etree.SubElement(service, 'Name').text = 'OGC:WMS'
    etree.SubElement(service, 'Title').text = lset_cfg['title']
    etree.SubElement(service, 'Abstract').text = lset_cfg['abstract']

    kwl = etree.SubElement(service, 'KeywordList')
    for kw in lset_cfg['keywords']:
        etree.SubElement(kwl, 'Keyword').text = kw

    onlr = etree.SubElement(service, 'OnlineResource', nsmap=NSMAP)
    onlr.set('{http://www.w3.org/1999/xlink}type', 'simple')
    onlr.set('{http://www.w3.org/1999/xlink}href', lset_cfg['url'])

    service.append(capContactInformation(config))

    etree.SubElement(service, 'Fees').text = 'none'

    # TODO: 'authentication' for restricted sets?
    etree.SubElement(service, 'AccessConstraints').text = 'none'

    root.append(capGetCapability(layers, config, lset_cfg))

    return etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=True)
