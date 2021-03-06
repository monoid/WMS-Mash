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

NSMAP = {'xlink': 'http://www.w3.org/1999/xlink'}


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

    def __init__(self, id, name, title, abstract, keywords, remote_name,
                 remote_url, parent, first_id, next_id, latlngbb, cap, layerDict=None):
        self.id = id
        self.name = unicode(name or '', 'utf-8') or None
        self.title = unicode(title or '', 'utf-8') or None
        self.abstract = unicode(abstract or '', 'utf-8')
        self.keywords = map(lambda s: unicode(s, 'utf-8'), keywords or [])
        self.remote_name = unicode(remote_name or '', 'utf-8') or None
        self.remote_url = remote_url
        self.first_id = first_id
        self.next_id = next_id
        if latlngbb is not None:
            self.latlngbb = parseJuliaLatLngBB(latlngbb)
        else:
            self.latlngbb = BoundingBox()
        if cap is None:
            self.cap = etree.Element("Layer")
        else:
            self.cap = etree.XML(cap)

        self.cleanCap()

        #parent = parent or 0
        if layerDict is not None and parent in layerDict:
            self.parent = layerDict[parent]
        else:
            self.parent = None

        self.children = []

        if layerDict is not None:
            layerDict[self.id] = self

        self.linked = False

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

    def addChild(self, child):
        self.children.append(child)

        if child.latlngbb.bbox:
            self.latlngbb.extendBy(child.latlngbb)

    def linkTree(self, layerDict):
        # Prevent looping if incorrect structure is created
        if self.linked:
            return

        self.linked = True

        # Link children recursively
        if self.first_id is not None:
            self.first = layerDict.get(self.first_id, None)
            node = self.first
            while node:
                self.addChild(node)
                node.linkTree(layerDict)
                node = layerDict.get(node.next_id, None)

    def isGroup(self):
        return len(self.children) > 0

    def dump(self):
        if (self.remote_url):
            try:
                cascade = int(self.cap.attrib.get('cascade', 0))
            except ValueError:
                cascade = 0
            self.cap.attrib['cascade'] = str(cascade + 1)

        etree.SubElement(self.cap, 'Title').text = self.title or ""
        if self.remote_name:
            etree.SubElement(self.cap, 'Name').text = self.name

        etree.SubElement(self.cap, 'Abstract').text = self.abstract or ""
        if self.latlngbb.bbox:
            bb = etree.SubElement(self.cap, 'LatLonBoundingBox')
            for key, val in self.latlngbb.bbox.items():
                bb.attrib[key] = str(val)
        for c in self.children:
            self.cap.append(c.dump())
        # DEBUG: add common SRS before we compute list of SRS correctly
        etree.SubElement(self.cap, 'SRS').text = 'EPSG:4326'
        return self.cap

    @staticmethod
    def buildTree(records, root_title='Root'):
        layerDict = {}
        layers = []
        ldParam = {'layerDict': layerDict}
        # root = Layer(0, root_title, '', '', [], '', '', None,
        #              0, None, None,
        #              layerDict=layerDict)

        # Create Layer objects 
        for rec in records:
            l = Layer(*rec, **ldParam)
            layers.append(l)

        # Build a tree structure
        # Lookup for node without a parent
        for l in layers:
            if l.parent is None:
                root = l
                # And link nodes recursively
                root.linkTree(layerDict)
                break
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
        onlr.set('{http://www.w3.org/1999/xlink}href', url)
        sub(sub(sub(node, 'DCPType'), 'HTTP'), 'Get').append(onlr)

    capRequest(req, 'GetCapabilities',
               ['application/vnd.ogc.wms_xml'],
               lset_cfg['url'])
    capRequest(req, 'GetMap',
               ['image/png', 'image/jpeg', 'image/tiff'],
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
    etree.SubElement(service, 'Title').text = lset_cfg['title'].decode('utf-8')
    etree.SubElement(service, 'Abstract').text = lset_cfg['abstract'].decode('utf-8')

    kwl = etree.SubElement(service, 'KeywordList')
    for kw in lset_cfg['keywords']:
        etree.SubElement(kwl, 'Keyword').text = kw.decode('utf-8')

    onlr = etree.SubElement(service, 'OnlineResource', nsmap=NSMAP)
    onlr.set('{http://www.w3.org/1999/xlink}type', 'simple')
    onlr.set('{http://www.w3.org/1999/xlink}href', lset_cfg['url'])

    service.append(capContactInformation(config))

    etree.SubElement(service, 'Fees').text = 'none'

    # TODO: 'authentication' for restricted sets?
    etree.SubElement(service, 'AccessConstraints').text = 'none'

    root.append(capGetCapability(layers, config, lset_cfg))

    return etree.tostring(root, encoding='utf-8', xml_declaration=True)
