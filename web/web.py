import json

from bottle import request, Bottle, static_file, abort
import logging
from nostr.ident import ProfileList
from data.data import DataSet
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.handler import WebSocketHandler
from nostr.client.client import Client
from nostr.event import Event
from nostr.client.event_handlers import PersistEventHandler
from nostr.client.persist import Store
from db.db import SQLiteDatabase


class StaticServer():
    """
        simple server that just deals with the static data html,js, css...
    """
    def __init__(self, file_root):
        self._app = Bottle()
        self._file_root = file_root+'/'


        """
            basically or statics are the same just ext and name of sub dir and the route text that changes
            so each call this to get the method that'll be called by their route that defines sub_dir and ext for that 
            files type
        """
        def get_for_ftype(sub_dir, ext=None):
            # where not defined so e.g. sub_dir == /css and file ext == .css
            if ext is None:
                ext = sub_dir

            def for_type(name):
                my_root = self._file_root + '%s/' % sub_dir
                logging.debug('StaticServer:: root: %s sub_dir: %s name: %s ext: %s' % (self._file_root,
                                                                                        sub_dir,
                                                                                        name,
                                                                                        ext))

                # if ext not already included then we'll add it
                if not ('.%s' % ext) in name:
                    name = name + '.%s' % ext
                print(name, my_root)
                return static_file(filename=name, root=my_root)
            return for_type

        # html
        html_method = get_for_ftype('html')

        @self._app.route('/html/<name>')
        def html(name):
            return html_method(name)

        # js
        js_method = get_for_ftype('script','js')

        @self._app.route('/script/<name>')
        def js(name):
            return js_method(name)

        # css
        css_method = get_for_ftype('css','css')

        @self._app.route('/css/<name>')
        def css(name):
            return css_method(name)

        @self._app.route('/fonts/<name>')
        def font(name):
            accept = set(['woff2','woff','ttf','svg'])
            splits = name.split('.')
            font_dir = self._file_root + 'fonts/'
            if len(splits)>1 and splits[1] in accept:
                logging.debug('StaticServer::%s %s %s' % (splits[1],
                                                          font_dir,
                                                          name))

                ret = static_file(filename=name, root=font_dir)

            else:
                # TODO this should readlly be doing a ?501? Auth exception
                raise Exception('arrrgh font type not accepted')
            return ret

    def start(self, host='localhost', port=8080):
        server = WSGIServer((host, port), self._app, handler_class=WebSocketHandler)
        server.serve_forever()


class NostrWeb(StaticServer):

    def __init__(self, file_root, db_file):
        self._db = SQLiteDatabase(db_file)
        self._store = Store(db_file)
        self._persist_event = PersistEventHandler(db_file)

        # this should be passed in and probably will be a ClientPool

        def my_connect(the_client):
            nonlocal self
            the_client.subscribe('web', self, {
                'since': self._store.get_oldest() - 100000
            })
        self._nostr_client = Client('ws://localhost:8082/', on_connect=my_connect).start()

        self._web_sockets = {}
        # initial load of profiles, after that shoudl track events
        # obvs at some point keeping all profiles in mem might not work so well
        self._other_profiles = ProfileList.create_profiles_from_db(self._db).as_arr()

        super(NostrWeb, self).__init__(file_root)

        self._add_routes()

    def _add_routes(self):
        self._app.route('/profiles',callback=self._profiles_list)
        self._app.route('/contact_list',callback=self._contact_list)
        self._app.route('/notes', callback=self._notes)
        self._app.route('/websocket', callback=self._handle_websocket)

        # obvs improve this and probably move to StaticServer
        def my_internal(e):
            return str(e).replace(',','<br>')

        self._app.error_handler = {
            500 : my_internal
        }

    def _profiles_list(self):
        ret = {
            'profiles' : self._other_profiles
        }
        return ret

    def _contact_list(self):
        pub_k = request.query.pub_k
        # we only need information from contacts, we already have what we need to link to profile
        sql = 'select pub_k_contact, relay, petname, updated_at from contacts where pub_k_owner=?'

        # get the profile info too
        if request.query.include_profile.lower()=='true':
            sql = """
                select 
                    c.pub_k_contact, c.relay, c.petname, c.updated_at,
                    p.attrs, p.name, p.picture
                    
                    from contacts c
                    inner join profiles p on c.pub_k_contact = p.pub_k
                    where pub_k_owner=?
            """

        if not pub_k:
            raise Exception('pub_k is required')

        contacts = DataSet.from_db(self._db,
                                   sql=sql,
                                   args=[pub_k])
        return {
            'pub_k_owner' : pub_k,
            'contacts' : contacts.as_arr(dict_rows=True)
        }

    def _notes(self):
        pub_k = request.query.pub_k
        sql_arr = [
            'select',
            ' id,created_at,content,tags,pubkey',
            ' from events',
            ' where kind=?'
        ]
        args = [Event.KIND_TEXT_NOTE]
        if pub_k:
            sql_arr.append(' and pubkey=?')
            args.append(pub_k)
        sql_arr.append(' order by created_at desc limit 1000')
        sql = ''.join(sql_arr)

        # if not pub_k:
        #     raise Exception('pub_k is required')

        notes = DataSet.from_db(self._db,
                                sql=sql,
                                args=args)

        ret = {
            'notes': notes.as_arr(dict_rows=True)
        }

        # if pub_k was handed in then we strip from each row and give at top level
        if pub_k:
            ret = {'notes': notes.of_heads(['id', 'created_at', 'content', 'tags']).as_arr(dict_rows=True),
                   'pub_k_owner': pub_k}
        else:
            ret = {
                'notes': notes.as_arr(dict_rows=True)
            }


        return ret


    def do_event(self, sub_id, evt, relay):
        # store event to db, no err handling...
        self._persist_event.do_event(sub_id, evt, relay)

        for c_sock in self._web_sockets:
            ws = self._web_sockets[c_sock]
            try:
                ws.send(json.dumps(evt))
            except Exception as e:
                print(e, ws)
                print('kill this guy?')

    def _handle_websocket(self):
        logging.debug('Websocket opened')
        wsock = request.environ.get('wsgi.websocket')
        if not wsock:
            abort(400, 'Expected WebSocket request.')

        self._web_sockets[str(wsock)] = wsock
        while True:
            try:
                # this is just to keep alive, currently we're doing nothing with dead sockets....
                wsock.receive()
            except WebSocketError:
                break

    def stop(self):
        self._nostr_client.end()

def nostr_web():
    nostr_db_file = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
    my_server = NostrWeb(file_root='/home/shaun/PycharmProjects/nostrpy/web/static/',
                         db_file=nostr_db_file)

    # example clean exit... need to look into more though
    import signal
    import sys
    def sigint_handler(signal, frame):
        my_server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)


    my_server.start()




    # my_socket = NostrWebsocket()
    # my_socket.start()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)



    nostr_web()