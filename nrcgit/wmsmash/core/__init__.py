from xml.sax import saxutils

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
    
    def __init__(self, dbrec, layerDict=None):
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
        for c in self.children:
            c.dump(buf)
        buf.write("</Layer>")

    @staticmethod
    def buildTree(records):
        layerDict = {}
        layers = []
        root = Layer((None, 'Root', '', '', '', '', '', None, 0), layerDict)
        for rec in records:
            l = Layer(rec, layerDict)
            layers.append(l)
        print layerDict
        return (root, layers, layerDict)
            
