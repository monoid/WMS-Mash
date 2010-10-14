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
    
    def __init__(self, dbrec, layersDict=None):
        self.id = dbrec[0]
        self.name = dbrec[1]
        self.title = dbrec[2]
        self.abstract = dbrec[3]
        self.keywords = dbrec[4]
        self.remote_name = dbrec[5]
        self.remote_url = dbrec[6]
        if layersDict and layersDict.key_exists(dbrec[7]):
            self.parent = layersDict[dbrec[7]]
            self.parent.addChild(self)
        self.order = dbrec[8]

        self.children = []

        if layersDict:
            layersDict[self.id] = self

    def getOrder(self):
        return self.order

    def addChild(self, child):
        self.children.append(child).sort(None, Layer.getOrder)

    @staticmethod
    def buildTree(records):
        layerDict = {}
        layers = []
        root = Layer((0, '', '', '', '', '', '', -1, 0))
        for rec in records:
            layers.append(Layer(rec))
        return (root, layers, layerDict)
            
