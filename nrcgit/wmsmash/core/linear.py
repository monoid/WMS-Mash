from twisted.internet.defer import Deferred
from collections import deque

class LinearDeferred(Deferred):
    actions = None
    func = None
    data = None
    index = 0

    def __init__(self, initial, actions, func):
        self.actions = deque(actions)
        self.func = func
        self.data = initial

        self._goToNext()
        
    def _goToNext(self):
        """Do next action."""
        if self.actions:
            next_elt = self.actions.popleft()
            deferred = self.func(next_elt, self.index)
            self.index += 1
            deferred.addCallbacks(self._handler, self._handler,
                                  callbackArgs=(next_elt, 1),
                                  errbackArgs=(next_elt, 0))
        else:
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
