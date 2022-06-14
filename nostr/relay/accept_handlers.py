from datetime import datetime
from geventwebsocket.websocket import WebSocket
from nostr.exception import NostrCommandException
from nostr.event.event import Event
from nostr.util import util_funcs


class AcceptReqHandler:
    """
        request handler for relay, a request handler just has to have
        accept_post(self, ws: WebSocket, evt: Event) method that throws
        NostrCommandException if we don't want to accept message
    """
    def __init__(self, descriptive_msg=True):
        self._desc_msg = descriptive_msg

    def raise_err(self, err_msg):
        if self._desc_msg:
            raise NostrCommandException(err_msg)
        else:
            raise NostrCommandException('post not accepted')

    def accept_post(self, ws: WebSocket, evt: Event):
        pass


class LengthAcceptReqHandler(AcceptReqHandler):
    """
    use to only accept messages of set lengths, most likely upto a max size
    """
    def __init__(self, min=1, max=None, descriptive_msg=True):
        """
        :param max: accept no longer then this
        :param min: - could be used to stop 0 length messages but maybe should include kind?
        """
        self._min = min
        self._max = max
        super().__init__(descriptive_msg)

    def accept_post(self, ws: WebSocket, evt: Event):
        msg_len = len(evt.content)
        if self._min and msg_len < self._min:
            self.raise_err('REQ content < accepted min %s got %s' % (self._min, msg_len))
        elif self._max and msg_len > self._max:
            self.raise_err('REQ content > accepted max %s got %s' % (self._max, msg_len))

    def __str__(self):
        return 'LengthAcceptReqHandler (%s-%s)' % (self._min, self._max)


class ThrottleAcceptReqHandler(AcceptReqHandler):
    """
    keeps track of time of messages for each pub_key and only lets repost if enough time has passed since
    last post
    maybe secs is too long change to use dt.timestamp() directly and then can do decimal point for parts of sec?

    """
    def __init__(self, tick_min=1, descriptive_msg=True):
        """
        :param tick_min: secs before a post is allowed per pub key
        :param descriptive_msg:
        """
        self._tickmin = tick_min
        # pub_key to last eventtime, NOTE never cleaned down at the moment
        self._track = {}
        super().__init__(descriptive_msg)

    def accept_post(self, ws: WebSocket, evt: Event):
        # pubkey posted before
        if evt.pub_key in self._track:
            # time since last post
            dt = util_funcs.date_as_ticks(datetime.now())-self._track[evt.pub_key]
            # time since last event is not enough msg not accepted
            if dt<self._tickmin:
                # update time anyway, this means if keep posting will keep failing...
                self._track[evt.pub_key] = util_funcs.date_as_ticks(datetime.now())
                self.raise_err('REQ pubkey %s posted to recently, posts most be %ss apart' % (evt.pub_key, self._tickmin))

        # update last post for pubkey
        self._track[evt.pub_key] = util_funcs.date_as_ticks(datetime.now())
