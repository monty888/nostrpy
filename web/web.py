from __future__ import annotations
from typing import TYPE_CHECKING

import beaker.middleware
import cryptography.x509

if TYPE_CHECKING:
    pass

import json
from json import JSONDecodeError
from bottle import request, Bottle, static_file, abort
from beaker import session

import logging
from pathlib import Path
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.handler import WebSocketHandler
from nostr.event.event import Event
from nostr.ident.profile import ProfileEventHandler, ProfileList, Profile, Contact
from nostr.ident.persist import SQLiteProfileStore, ProfileType
from nostr.event.persist import ClientEventStoreInterface, SQLiteEventStore
from nostr.encrypt import Keys

class StaticServer:
    """
        simple server that just deals with the static data html,js, css...
    """
    def __init__(self, file_root):
        self._app = Bottle()
        self._file_root = file_root+'/'
        # if running in our own server, probably only suiatable for dev
        self._server = None

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

        # TODO make a static route that make it easier to add path, name , type or similiar
        @self._app.route('/images/<name>')
        def font(name):
            accept = set(['png', 'jpg'])
            splits = name.split('.')
            font_dir = self._file_root + 'images/'
            if len(splits) > 1 and splits[1] in accept:
                logging.debug('StaticServer::%s %s %s' % (splits[1],
                                                          font_dir,
                                                          name))

                ret = static_file(filename=name, root=font_dir)

            else:
                # TODO this should readlly be doing a ?501? Auth exception
                raise Exception('arrrgh image type not accepted')
            return ret

        @self._app.route('/bootstrap_icons/<name>')
        def font(name):
            accept = set(['svg'])
            splits = name.split('.')
            # font_dir = self._file_root + 'bootstrap-icons-1.5.0/'
            file_dir = self._file_root + 'bootstrap-icons-1.8.3/'
            if len(splits) > 1 and splits[1] in accept:
                logging.debug('StaticServer::%s %s %s' % (splits[1],
                                                          file_dir,
                                                          name))

                ret = static_file(filename=name, root=file_dir)

            else:
                # TODO this should readlly be doing a ?501? Auth exception
                raise Exception('arrrgh icon type not accepted')
            return ret


    def start(self, host='localhost', port=8080):
        logging.debug('started web server at %s port=%s' % (host, port))
        self._server = WSGIServer((host, port), self._app, handler_class=WebSocketHandler)
        self._server.serve_forever()

    def stop(self):
        self._server.stop()

    @property
    def app(self):
        return self._app

    @app.setter
    def app(self, app):
        self._app = app

class NostrWebException(Exception):
    pass


class NostrWeb(StaticServer):

    def __init__(self,
                 file_root,
                 event_store: ClientEventStoreInterface,
                 profile_store: SQLiteProfileStore,
                 profile_handler: ProfileEventHandler):

        self._event_store = event_store
        self._profile_store = profile_store
        self._profile_handler = profile_handler

        self._web_sockets = {}
        super(NostrWeb, self).__init__(file_root)

        self._add_routes()

        # to use when no limit given for queries
        self._default_query_limit = 100
        # queries will be limited to this even if caller asks for more, None unlimited
        self._max_query = None

    def _add_routes(self):
        # methods wrapped so that if they raise NostrException it'll be returned as json {error: text}
        def _get_err_wrapped(method):
            def _wrapped():
                try:
                    return method()
                except NostrWebException as ne:
                    return ne.args[0]
            return _wrapped

        # this is used if method didn't raise nostrexception, do something better in static server
        def my_internal(e):
            return str(e).replace(',', '<br>')

        self._app.error_handler = {
            500: my_internal
        }

        self._app.route('/profile', callback=self._profile)
        self._app.route('/profiles', callback=self._profiles_list)
        self._app.route('/local_profiles', callback=_get_err_wrapped(self._local_profiles))
        self._app.route('/set_profile', method='POST', callback=_get_err_wrapped(self._set_profile))
        self._app.route('/current_profile', callback=_get_err_wrapped(self._get_profile))
        self._app.route('/state/js', callback=_get_err_wrapped(self._state))

        # self._app.route('/contact_list',callback=self._contact_list)
        self._app.route('/events', method='POST', callback=_get_err_wrapped(self._events_route))
        self._app.route('/events_text_search', callback=_get_err_wrapped(self._events_text_search_route))
        self._app.route('/text_events', callback=self._text_events_route)
        self._app.route('/text_events_for_profile', callback=self._text_events_for_profile)
        self._app.route('/websocket', callback=self._handle_websocket)


    def _check_pub_key(self, pub_k):
        if not pub_k:
            raise Exception('pub_k is required')
        if not Keys.is_valid_pubkey(pub_k):
            raise Exception('value - %s doesn\'t look like a valid nostr pub key' % pub_k)

    def _get_all_contacts_profile(self, pub_k):
        ret = set([])
        # shortcut, nothing asked for
        if pub_k == '':
            return ret

        # add ourself
        ret.add(pub_k)

        the_profile: Profile
        c_contact: Contact

        self._check_pub_key(pub_k)
        the_profile = self._profile_handler.profiles.get_profile(pub_k)
        if the_profile is None:
            raise Exception('no profile found for pub_k - %s' % pub_k)

        # add contacts
        for c_contact in the_profile.load_contacts(self._profile_store):
            ret.add(c_contact.contact_public_key)

        # add followers
        for c_contact in the_profile.load_followers(self._profile_store):
            ret.add(c_contact.owner_public_key)

        return ret


    def _profiles_list(self):
        # , list of pub_ks we want profiles for
        pub_k = request.query.pub_k
        all_keys = set([])
        if pub_k:
            all_keys = set(pub_k.split(','))

        # alternative to listing pub_k can supply for_profile and all that profiles contacts/followers will be loaded
        # currently just sigular but i guess could be comma seperated list of profiles
        for_profile = self._get_all_contacts_profile(request.query.for_profile)

        # we combine so a profile plus some other p_keys can be requested
        all_keys = all_keys.union(for_profile)

        the_profile: Profile
        ret = {
            'profiles': []
        }
        # pub_k, or pub_ks, seperated by ,
        # possibly this will /profile and /profiles methods merged
        # note we don't check the pub_ks, if they're incorrect then nothing will be returned for that pk anyhow
        if all_keys:
            for c_pub_k in all_keys:
                the_profile = self._profile_handler.profiles.get_profile(c_pub_k)
                # we could easily add in here contact and profile whci would replace the
                # profiles method, though obviously loading per profile wouldn't be great with a very long list of
                # pks
                if the_profile:
                    ret['profiles'].append(the_profile.as_dict())

        # eventually this full list will probably have to go
        else:
            ret['profiles'] = self._profile_handler.profiles.as_arr()

        return ret

    def _profile(self):
        the_profile: Profile
        pub_k = request.query.pub_k
        include_contacts: str = request.query.include_contacts
        include_followers: str = request.query.include_followers

        # will throw if we don't think valid pub_k
        self._check_pub_key(pub_k)
        the_profile = self._profile_handler.profiles.get_profile(pub_k)
        if the_profile is None:
            raise Exception('no profile found for pub_k - %s' % pub_k)

        ret = the_profile.as_dict()

        c: Contact
        # add in contacts if asked for
        if include_contacts.lower() == 'true':
            the_profile.load_contacts(self._profile_store)
            ret['contacts'] = [c.contact_public_key for c in the_profile.contacts]

        # add in follows if asked for
        if include_followers.lower() == 'true':
            the_profile.load_followers(self._profile_store)
            ret['followed_by'] = [c.owner_public_key for c in the_profile.followed_by]

        return ret

    def _local_profiles(self):
        """
        :return: profiles that we have priv_k for
        """
        profiles = self._profile_store.select(profile_type=ProfileType.LOCAL)
        c_p: Profile

        ret = {
            'profiles': [c_p.as_dict() for c_p in profiles]
        }
        return ret

    @property
    def session(self):
        return request.environ.get('beaker.session')

    def _set_profile(self):
        """
        set the profile that will be used when perfoming any action,
            TODO: on some pages it will also change what the users sees and how its displayed
             note currently there is no authentication it assumed that if you can see the web server then it safe
             it could be served over tor and use their basic auth now I think...
             or we can add some sort of basic auth (if available over web you'd want to serve over SSL...)
        :return: profile if it was found
        """
        p_name = request.query.profile

        if p_name == '':
            raise Exception('profile not supplied')

        profiles = self._profile_store.select({
            'private_key': p_name,
            'public_key': p_name,
            'profile_name': p_name
        }, profile_type=ProfileType.LOCAL)

        if not len(profiles):
            raise Exception('no profile found for key: %s' % p_name)

        c_p = profiles[0]
        self.session['profile'] = c_p.as_dict()
        self.session.save()

        return c_p.as_dict()

    def _get_profile(self):
        """
        :return: current profile or {} if not set
        """
        ret = {}
        if 'profile' in self.session:
            ret = self.session['profile']

        return ret

    def _state(self):
        """
        special route to return a js file that reflects some state on the server
        currently this is only current profile but probbaly include othere settings
        it should mainly things that we hold in the session var
        don't do too much here, for most things its better to make requests as needed
        :return:
        """

        c_profile = {}
        if 'profile' in self.session:
            c_profile = self.session['profile']

        ret = """
            APP.nostr.data.state = {
                'current_user' : %s
            };
        """ % c_profile

        return ret


    # def _contact_list(self):
    #     pub_k = request.query.pub_k
    #
    #     # will throw if we don't think valid pub_k
    #     self._check_pub_key(pub_k)
    #
    #     for_profile = self._profile_handler.profiles.get_profile(pub_k,
    #                                                              create_type=ProfileList.CREATE_PUBLIC)
    #     contacts = for_profile.load_contacts(self._profile_store)
    #
    #     return {
    #         'pub_k_owner': pub_k,
    #         'contacts': 'TODO'
    #     }

    def _get_events(self, filter):
        events = self._event_store.get_filter(filter)
        c_evt: Event
        ret = []
        for c_evt in events:
            ret.append(c_evt.event_data())
        return ret

    def _events_route(self):
        """
        returns events that match given nostr filter [{},...]
        :return:
        """

        try:
            filter = json.loads(request.forms['filter'])
        except KeyError as ke:
            raise NostrWebException({
                'error': 'filter is undefined?!'
            })
        except JSONDecodeError as je:
            raise NostrWebException({
                'error': 'unable to decode filter %s' % request.forms['filter']
            })

        if not hasattr(filter, '__iter__') or isinstance(filter, dict):
            filter = [filter]

        limit = self._get_query_limit()
        if limit is not None:
            if 'limit' not in filter[0] or filter[0]['limit']>limit:
                filter[0]['limit'] = limit


        return {
            'events': self._get_events(filter)
        }

    def _events_text_search_route(self):
        search_str = request.query.search_str
        limit = self._get_query_limit()
        evts = []
        if search_str != '':
            evts = [c_evt.event_data() for c_evt in self._event_store.get_text(search_str, limit)]

        return {
            'events': evts
        }


    def _get_query_limit(self):
        limit = self._default_query_limit
        try:
            limit = int(request.query.limit)
        except:
            pass

        if self._max_query and limit and limit > self._max_query:
            limit = self._max_query
        return limit

    def _text_events_route(self):
        """
        all the text notes for a given pub_key
        :return:
        """
        pub_k = request.query.pub_k

        # will throw if we don't think valid pub_k
        self._check_pub_key(pub_k)

        return {
            'events': self._get_events({
                'authors': [pub_k],
                'kinds': [Event.KIND_TEXT_NOTE],
                'limit': self._get_query_limit()
            })
        }

    def _text_events_for_profile(self):
        """
        get texts notes for pub_k or those we have as contacts
        :return:
        """
        pub_k = request.query.pub_k

        # will throw if we don't think valid pub_k
        self._check_pub_key(pub_k)

        limit = self._get_query_limit()

        for_profile = self._profile_handler.profiles.get_profile(pub_k,
                                                                 create_type=ProfileList.CREATE_PUBLIC)
        for_profile.load_contacts(self._profile_store)
        c: Contact

        return {
            'events': self._get_events({
                'authors': [pub_k] + [c.contact_public_key for c in for_profile.contacts],
                'kinds': [Event.KIND_TEXT_NOTE],
                'limit': limit
            })
        }

    def do_event(self, sub_id, evt:Event, relay):
        for c_sock in self._web_sockets:
            ws = self._web_sockets[c_sock]
            try:
                ws.send(json.dumps(evt.event_data()))
            except WebSocketError as we:
                print(we, ws)
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

def nostr_web():
    nostr_db_file = '%s/.nostrpy/nostr-client.db' % Path.home()

    from nostr.util import util_funcs
    event_store = util_funcs.create_sqlite_store(nostr_db_file, True)
    profile_store = SQLiteProfileStore(nostr_db_file)
    profile_handler = ProfileEventHandler(SQLiteProfileStore(nostr_db_file))

    my_server = NostrWeb(file_root='%s/PycharmProjects/nostrpy/web/static/' % Path.home(),
                         event_store=event_store,
                         profile_store=profile_store,
                         profile_handler=profile_handler)

    from nostr.client.client import ClientPool
    from datetime import datetime
    def my_connect(the_client):
        the_client.subscribe(handlers=my_server, filters={
            'since': util_funcs.date_as_ticks(datetime.now())
        })

    my_client = ClientPool(['ws://localhost:8081','wss://nostr-pub.wellorder.net'], on_connect=my_connect)
    my_client.start()

    # example clean exit... need to look into more though
    import signal
    import sys
    def sigint_handler(signal, frame):
        my_client.end()
        my_server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)
    # my_server.start(host='localhost')

    # set up the session middleware
    session_opts = {
        'session.type': 'file',
        'session.cookie_expires': 300,
        'session.data_dir': './data',
        'session.auto': True
    }
    my_server.app = beaker.middleware.SessionMiddleware(my_server.app, session_opts)

    my_server.start(host='192.168.0.14')

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    nostr_web()


    # from nostr.ident.persist import SQLiteProfileStore
    #
    # db_file = '%s/.nostrpy/nostr-client.db' % Path.home()
    # my_profile_store = SQLiteProfileStore(db_file)
    # my_event_store = SQLiteEventStore(db_file)
    # my_profile_store.import_contacts_from_events(my_event_store)
