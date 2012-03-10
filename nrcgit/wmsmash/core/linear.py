from twisted.internet.defer import Deferred


class LinearDeferred(Deferred):
    actions = None
    gen = None
    data = None

    def __init__(self, initial, generator):
        self.gen = gen
        self.data = initial

        self._goToNext()

    def _goToNext(self):
        """Do next action."""
        try:
            deferred = self.gen.next()
            deferred.addCallbacks(self._handler, self._handler,
                                  callbackArgs=(next_elt, 1),
                                  errbackArgs=(next_elt, 0))
        except StopIteration:
            self.callback(self.data)

    def _handler(self, data, elt, status):
        """Handle completed deferred."""
        if status == 1:
            self.data = self.next(self.data, data, elt)
        else:
            self.err(data, elt)

        self._goToNext()

    def next(self, prevData, nextData, elt):
        """Consume next result.
Default implementation appends nextData to prevData (assuming it is a list)."""
        prevData.append(nextData)
        return prevData

    def err(self, prevData, info, elt):
        """Handle a error.
Default implementation does nothing."""
        pass
