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
        self.name = dbrec[1]
        self.title = dbrec[2]
        self.abstract = dbrec[3]
        self.keywords = dbrec[4]
        self.remote_name = dbrec[5]
        self.remote_url = dbrec[6]
        self.order = dbrec[8]
        if dbrec[9] is not None:
            self.latlngbb = parseJuliaLatLngBB(dbrec[9])
        else:
            self.latlngbb = BoundingBox()
        if dbrec[10] is not None:
            self.cap = etree.XML(dbrec[10])

        if layerDict is not None and layerDict.has_key(dbrec[7]):
            self.parent = layerDict[dbrec[7]]
            self.parent.addChild(self)

        self.children = []

        if layerDict is not None:
            layerDict[self.id] = self

    def getOrder(self):
        return self.order

    def addChild(self, child):
        self.children.append(child)
        self.children.sort(None, Layer.getOrder)
        if child.latlngbb.bbox:
            self.latlngbb.extendBy(child.latlngbb)

    def isGroup(self):
        return len(self.children) > 0

    def dump(self, buf):
        if self.cap is not None and self.cap.attrib.has_key('cascade'):
            cascade = int(self.cap.attrib)+1
        else:
            cascade = 1
        if (self.isGroup()):
            buf.write("<Layer>")
        else:
            buf.write("<Layer cascade='%d'>" % cascade)
            
        if (self.remote_name is None):
            buf.write("<Title>%s</Title>" % (self.name,))
        else:
            buf.write("<Name>%s</Name>" % (self.name,))
            if (self.title is not None):
                buf.write("<Title>%s</Title>" % (self.title,))

        if (self.abstract is not None):
            buf.write("<Abstract>%s</Abstract>" % saxutils.escape(self.abstract))
        # TODO: compute common LatLngBoundingBox for groups
        if (self.latlngbb.bbox is not None):
            buf.write('<LatLonBoundingBox minx="%(minx)f" maxx="%(maxx)f" miny="%(miny)f" maxy="%(maxy)f" />' % self.latlngbb.bbox)

        # TODO: compute common SRS list for groups
        if (self.cap is not None):
            for srs in self.cap.xpath('/Layer/SRS'):
                buf.write(etree.tostring(srs))
            for bb in self.cap.xpath('/Layer/BoundingBox'):
                buf.write(etree.tostring(bb))
            for style in self.cap.xpath('/Layer/Style'):
                buf.write(etree.tostring(style))

        for c in self.children:
            c.dump(buf)
        buf.write("</Layer>")

    @staticmethod
    def buildTree(records):
        layerDict = {}
        layers = []
        root = Layer((None, 'Root', '', '', '', '', '', None, 0, None, None), layerDict)
        for rec in records:
            l = Layer(rec, layerDict)
            layers.append(l)
        return (root, layers, layerDict)
            
###
### GetCapabilities
###

def capContactInformation(config):
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

    
