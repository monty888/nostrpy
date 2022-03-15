import rel
from bottle import request, Bottle, abort
import logging
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocket
from gevent.lock import BoundedSemaphore
import json
from json import JSONDecodeError
from nostr.event import Event
from nostr.persist import RelayStore
from sqlite3 import IntegrityError
from datetime import datetime
from nostr.util import util_funcs
from enum import Enum

class NostrCommandException(Exception):
    # define elsewhere so easier to import...
    pass


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
    def __init__(self, max=10, min=0, descriptive_msg=True):
        """
        :param max: accept no longer then this
        :param min: - would this ever be useful? Probably not
        """
        self._min = min
        self._max = max
        super().__init__(descriptive_msg)

    def accept_post(self, ws: WebSocket, evt: Event):
        msg_len = len(evt.content)
        if msg_len < self._min:
            self.raise_err('REQ content < accepted min %s got %s' % (self._min, msg_len))
        elif msg_len > self._max:
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


class DeleteMode(Enum):
    # what will the relay do on receiving delete event

    # delete any events we can from db
    DEL_DELETE = 1
    # mark as deleted any events from db - to client this would look exactly same as DEL_DELETE
    DEL_FLAG = 2
    # nothing, ref events will still be returned to clients
    DEL_NO_ACTION = 3

class Relay:
    """
        implements nostr relay protocol
        NIPs....
    """
    VALID_CMDS = ['EVENT', 'REQ', 'CLOSE']

    def __init__(self, store: RelayStore, accept_req_handler=None, max_sub=3, delete_mode=DeleteMode.DEL_DELETE):
        self._app = Bottle()
        self._app.route('/websocket', callback=self._handle_websocket)
        # self._web_sockets = {}

        # single lock for accessing shared resource
        self._lock = BoundedSemaphore()
        # corrently connected ws
        self._ws = {}
        self._store = store

        # max subs allowed per websocket
        self._max_sub = max_sub

        # by default when we recieve requests as long as the event has a valid sig we accept
        # (Prob we should also have a future timestamp requirement, it'd probably have to be 12hr+ as
        # there is no timezone info with create_at)
        # but in real world relay will probably want to protect itself more e.g. set max length on
        # event content, restrict to set kinds or even only allow set pubkeys to posts
        # self._accept_req can be a single class or [] of handlers that are called and the event will
        # it'll throw and return a NOTICE evt if msg not accepted (maybe we'd want option to just drop and do nothing?)
        self._accept_req = accept_req_handler
        if self._accept_req is None:
            # accepts everything
            self._accept_req = [AcceptReqHandler()]
        # convert to array of only single class handed in
        if not hasattr(self._accept_req, '__iter__'):
            self._accept_req = [self._accept_req]

        self._delete_mode = delete_mode

        logging.info('Relay::__init__ maxsub=%s' % self._max_sub)

    def start(self, host='localhost', port=8080):
        logging.info('Relay::start host=%s port=%s' % (host, port))
        server = WSGIServer((host, port), self._app, handler_class=WebSocketHandler)
        server.serve_forever()

    def _handle_websocket(self):
        logging.debug('Websocket opened')
        ws = request.environ.get('wsgi.websocket')

        if not ws:
            abort(400, 'Expected WebSocket request.')

        # set up place to store subs for ws
        self._ws[ws] = {
            'subs': {}
        }

        while True:
            try:
                self._do_request(ws, ws.receive())
            except WebSocketError:
                break

    def _do_request(self, ws: WebSocket, req_str):
        # passed nothing? nothing to do
        if not req_str:
            return

        try:
            as_json = json.loads(req_str)
            if not as_json:
                raise NostrCommandException('No command received')
            cmd = as_json[0]
            if cmd not in Relay.VALID_CMDS:
                raise NostrCommandException('unsupported command %s' % cmd)

            # a post of an event
            if cmd == 'EVENT':
                self._do_event(as_json, ws)
            # register a subscription
            elif cmd == 'REQ':
                self._do_sub(as_json, ws)
            elif cmd == 'CLOSE':
                self._do_unsub(as_json, ws)

        except JSONDecodeError as je:
            err = ['NOTICE', 'unable to decode command string']
            ws.send(json.dumps(err))
        except NostrCommandException as ne:
            err = ['NOTICE', str(ne)]
            ws.send(json.dumps(err))

    def _do_event(self, req_json, ws: WebSocket):
        if len(req_json) <= 1:
            raise NostrCommandException('EVENT command missing event data')
        evt = Event.create_from_JSON(req_json[1])
        # check event sig matches pub_key
        if not evt.is_valid():
            raise NostrCommandException('invalid event, pubkey doesn\'t match sig')

        # pass evt through all AcceptReqHandlers, if any are not happy they'll raise
        # NostrCommandException otherwise we should be good to go
        for c_accept in self._accept_req:
            c_accept.accept_post(ws, evt)

        try:
            self._store.add_event(evt)
            logging.info('Relay::_do_event persisted event - %s - %s (%s)' % (evt.short_id,
                                                                             util_funcs.str_tails(evt.content, 6),
                                                                             # give str mapping of kind where we can in future
                                                                             evt.kind))
            if evt.kind == Event.KIND_DELETE:
                self._do_delete(evt)

            # now post to any interested subscribers
            self._check_subs(evt)
        except IntegrityError as ie:
            msg = str(ie)
            if 'events.event_id' in msg and 'UNIQUE' in msg:
                raise NostrCommandException('event already exists %s' % evt.id)

    def _do_delete(self, evt: Event):
        logging.debug('Relay::_do_delete - %s' % evt.tags)
        if evt.kind == DeleteMode.DEL_DELETE or DeleteMode.DEL_FLAG:
            e_tags = []
            for c_e in evt.tags:
                if len(c_e) >= 2 and c_e[0] == 'e' and len(c_e[1])==64:
                    e_tags.append(c_e[1])
            if e_tags:
                to_delete = self._store.get_filter({
                    'authors': evt.pub_key,
                    'ids': e_tags
                })
                self._store.delete_events(to_delete, self._delete_mode == DeleteMode.DEL_FLAG)

    def _clean_ws(self):
        """
            this cleans old websockets and thier subs
            TODO: add close handler to the web sockets we get so that we do the clean up then,
            when done this most likely can go...
        """
        to_rem = []
        for ws in self._ws:
            if ws.closed:
                to_rem.append(ws)

        with self._lock:
            for c_rem in to_rem:
                del self._ws[c_rem]

    def _check_subs(self, evt):
        """
        go through all our filters and send the event to any clients who have registered subs
        with filters that the new event passes.
        Note done sequentially through our subs, if we ever had a large numbers of subscribers
        this would probably be problematic, also likely a problem if one blocked or closed etc..
        TODO: convert the send to use ayncio - actually probably have to use threadpool
        see https://stackoverflow.com/questions/51050315/using-asyncio-for-non-async-functions-in-python
        or maybe look at gevent that websocket is already using

        :param evt:
        :return:
        """

        # this will remove any old sockets that already got closed
        self._clean_ws()

        # we should probably still catch websocket closed errs here, they can be clean next hit
        for ws in self._ws:
            for c_sub_id in self._ws[ws]['subs']:
                the_sub = self._ws[ws]['subs'][c_sub_id]

                # event passes sub filter
                if evt.test(the_sub['filter']):
                    self._send_event(ws, c_sub_id, evt)

    def _do_sub(self, req_json, ws: WebSocket):
        logging.info('subscription requested')
        if len(req_json) <= 1:
            raise NostrCommandException('REQ command missing sub_id')
        if len(req_json) <= 2:
            raise NostrCommandException('REQ command missing filter')

        # get sub_id and filter fro the json
        sub_id = req_json[1]
        filter = req_json[2]

        # this user already subscribed under same sub_id
        if sub_id in self._ws[ws]['subs']:
            raise NostrCommandException('REQ command for sub_id that already exists - %s' % sub_id)
        # this sub would put us over max for this socket
        sub_count = len(self._ws[ws]['subs'])
        if sub_count >= self._max_sub:
            raise NostrCommandException('REQ new sub_id %s not allowed, already at max subs=%s' % (sub_id, self._max_sub))

        self._ws[ws]['subs'][sub_id] = {
            'id': sub_id,
            'filter': filter
        }
        logging.info('Relay::_do_sub subscription added %s (%s)' % (sub_id, filter))

        # post back the pre existing
        evts = self._store.get_filter(filter)
        for c_evt in evts:
            self._send_event(ws, sub_id, c_evt)

    def _do_unsub(self, req_json, ws: WebSocket):
        logging.info('un-subscription requested')
        if len(req_json) <= 1:
            raise NostrCommandException('REQ command missing sub_id')

        # get sub_id from json
        sub_id = req_json[1]
        # user isn't subscribed anyhow, nothing to do
        if sub_id not in self._ws[ws]['subs']:
            raise NostrCommandException('CLOSE command for sub_id that not subscribed to, nothing to do - %s' % sub_id)

        # remove the sub
        del self._ws[ws]['subs'][sub_id]
        # not actual exception but this will send notice back that sub_id has been closed, might be useful to client?
        raise NostrCommandException('CLOSE command for sub_id %s - success' % sub_id)

    def _send_event(self, ws: WebSocket, sub_id, evt):
        try:
            to_send = [
                'EVENT',
                sub_id,
                evt.event_data()
            ]
            ws.send(json.dumps(to_send))
        except Exception as e:
            logging.info('Relay::_send_event error: %s' % e)

def start_relay():
    nostr_db_file = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
    my_server = Relay()
    my_server.start(port=8081)

    # my_socket = NostrWebsocket()
    # my_socket.start()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)

    # example clean exit... need to look into more though
    import signal
    import sys


    def sigint_handler(signal, frame):
        rel.abort()
        sys.exit(0)


    signal.signal(signal.SIGINT, sigint_handler)

    start_relay()