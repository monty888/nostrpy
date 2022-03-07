import rel
from bottle import request, Bottle, abort
import logging
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocket
import json
from json import JSONDecodeError

class NostrCommandException(Exception):
    pass

class Relay:
    """
        implements nostr relay protocol
        NIPs....
    """
    VALID_CMDS = ['EVENT', 'REQ', 'CLOSE']

    def __init__(self):
        self._app = Bottle()
        self._app.route('/websocket', callback=self._handle_websocket)
        self._web_sockets = {}

    def start(self, host='localhost', port=8080):
        logging.debug('Relay::start host=%s port=%s' % (host, port))
        server = WSGIServer((host, port), self._app, handler_class=WebSocketHandler)
        server.serve_forever()

    def _handle_websocket(self):
        logging.debug('Websocket opened')
        ws = request.environ.get('wsgi.websocket')

        if not ws:
            abort(400, 'Expected WebSocket request.')

        self._web_sockets[str(ws)] = ws
        while True:
            try:
                self._do_request(ws, ws.receive())
            except WebSocketError:
                break

    def _do_request(self, ws: WebSocket, req_str):
        try:
            as_json = json.loads(req_str)
            if not as_json:
                raise NostrCommandException('No command received')
            cmd = as_json[0]
            if cmd not in Relay.VALID_CMDS:
                raise NostrCommandException('unsupported command %s' % cmd)

            ws.send('ONWARDS')

        except JSONDecodeError as je:
            err = ['NOTICE','unable to decode command string']
            ws.send(json.dumps(err))
        except NostrCommandException as ne:
            err = ['NOTICE', str(ne)]
            ws.send(json.dumps(err))


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