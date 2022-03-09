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

# define elsewhere so easier to import...
class NostrCommandException(Exception):
    pass

class Relay:
    """
        implements nostr relay protocol
        NIPs....
    """
    VALID_CMDS = ['EVENT', 'REQ', 'CLOSE']

    def __init__(self, store: RelayStore):
        self._app = Bottle()
        self._app.route('/websocket', callback=self._handle_websocket)
        # self._web_sockets = {}

        # single lock for accessing shared resource
        self._lock = BoundedSemaphore()
        # corrently connected ws
        self._ws = {}
        self._store = store

    def start(self, host='localhost', port=8080):
        logging.debug('Relay::start host=%s port=%s' % (host, port))
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
        # other checks, prob we'll allow creator to pass check method in
        # e.g. so could decline certain types, or only allow set pubkeys

        try:
            self._store.add_event(evt.event_data())
            logging.debug('Relay::_do_event persisted event - %s' % evt.id)
            # now post to any interested subscribers
            self._check_subs(evt)
        except IntegrityError as ie:
            msg = str(ie)
            if 'events.event_id' in msg and 'UNIQUE' in msg:
                raise NostrCommandException('event already exists %s' % evt.id)

    def _clean_ws(self):
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
                if self._check_evt_filter(evt, the_sub['filter']):
                    self._send_event(ws, c_sub_id, evt)

    def _check_evt_filter(self, evt, filter):
        """
        returns True if event passes the filter, filter can be multiple, if it is the filters
        are OR'd so we can exit on first filter that is ok

        :param evt: nostr event
        :param filter: [] of nostr filters
        :return: True if event passes the filter
        """
        return True

    def _do_sub(self, req_json, ws: WebSocket):
        logging.debug('subscription requested')
        if len(req_json) <= 1:
            raise NostrCommandException('REQ command missing sub_id')
        if len(req_json) <= 2:
            raise NostrCommandException('REQ command missing filter')

        sub_id = req_json[1]
        # TODO: needs to deal with multiple filtere that are OR'd so we'll make list event when it isn't
        filter = req_json[2]
        if sub_id in self._ws[ws]['subs']:
            raise NostrCommandException('REQ command for sub_id that already exists - %s' % sub_id)

        self._ws[ws]['subs'][sub_id] = {
            'id': sub_id,
            'filter': filter
        }
        logging.debug('Relay::_do_sub subscription added %s (%s)' % (sub_id, filter))

        # post back the pre existing
        evts = self._store.get_filter(filter)
        for c_evt in evts:
            self._send_event(ws, sub_id, c_evt)

    def _send_event(self, ws: WebSocket, sub_id, evt):
        try:
            to_send = [
                'EVENT',
                sub_id,
                evt.event_data()
            ]
            ws.send(json.dumps(to_send))
        except Exception as e:
            logging.debug('Relay::_send_event %s' % e)

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