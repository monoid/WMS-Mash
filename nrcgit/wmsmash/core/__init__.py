from xml.sax import saxutils
import lxml.etree as etree

def parseJuliaLatLngBB(str):
    elts = str.split()
    r = {}
    for e in elts:
        print e
        e = e.split('=')
        r[e[0]] = float(e[1])
    return r

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
        print len(dbrec)
        self.id = dbrec[0]
        self.name = dbrec[1]
        self.title = dbrec[2]
        self.abstract = dbrec[3]
        self.keywords = dbrec[4]
        self.remote_name = dbrec[5]
        self.remote_url = dbrec[6]
        if layerDict is not None and layerDict.has_key(dbrec[7]):
            self.parent = layerDict[dbrec[7]]
            self.parent.addChild(self)
        self.order = dbrec[8]
        if dbrec[9] is not None:
            self.latlngbb = parseJuliaLatLngBB(dbrec[9])
        if dbrec[10] is not None:
            self.cap = etree.XML(dbrec[10])

        print "ID: %s " % self.id
        print "Name: %s " % self.name
        print "Parent: %s " % dbrec[7]
        self.children = []

        if layerDict is not None:
            layerDict[self.id] = self

    def getOrder(self):
        return self.order

    def addChild(self, child):
        self.children.append(child)
        self.children.sort(None, Layer.getOrder)

    def dump(self, buf):
        buf.write("<Layer>")
        if (self.remote_name is None):
            buf.write("<Title>%s</Title>" % (self.name,))
        else:
            buf.write("<Name>%s</Name>" % (self.name,))
            if (self.title is not None):
                buf.write("<Title>%s</Title>" % (self.title,))
        if (self.abstract is not None):
            buf.write("<Abstract>%s</Abstract>" % saxutils.escape(self.abstract))
        # TODO: compute common LatLngBoundingBox for groups
        if (self.latlngbb is not None):
            buf.write('<LatLngBoundingBox minx="%(minx)f" maxx="%(maxx)f" miny="%(miny)f" maxy="%(maxy)f" />' % self.latlngbb)
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
        print layerDict
        return (root, layers, layerDict)
            
