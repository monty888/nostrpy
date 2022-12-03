from __future__ import annotations
from typing import TYPE_CHECKING

import beaker.middleware
import bottle

if TYPE_CHECKING:
    from nostr.ident.event_handlers import ProfileEventHandler
    from nostr.channels.event_handlers import ChannelEventHandler
    from nostr.event.event_handlers import EventHandler

import json
import time
from io import BytesIO
from json import JSONEncoder
from datetime import datetime
from copy import copy
import re
from json import JSONDecodeError
from bottle import request, Bottle, static_file, abort
from webpreview import webpreview
from beaker import session
from robohash import Robohash
from bottle import response
from functools import lru_cache
import logging
from pathlib import Path
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.websocket import WebSocket
from geventwebsocket.handler import WebSocketHandler
from nostr.event.event import Event, EventTags
from nostr.ident.profile import ProfileList, Profile, Contact, ContactList, ValidatedProfile
from nostr.ident.persist import SQLiteProfileStore
from nostr.event.persist import ClientEventStoreInterface, SQLiteEventStore
from nostr.encrypt import Keys
from nostr.client.client import ClientPool, Client
from nostr.client.event_handlers import DeduplicateAcceptor
from nostr.channels.channel import Channel, ChannelList
from nostr.util import util_funcs
from nostr.spam_handlers.spam_handlers import SpamHandlerInterface
from nostr.settings.handler import Settings
import beaker.middleware

class DateTimeEncoder(JSONEncoder):
    """
        dates aren't part of the standard python json encode so add here
        add as required, just datetime at the moment
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.timestamp()
        return super().default(obj)


class StaticServer:
    """
        simple server that just deals with the static data html,js, css...
    """
    def __init__(self, file_root):
        self._app = Bottle()
        self._file_root = file_root+'/'
        # if running in our own server, probably only suiatable for dev
        self._server = None

        # html
        html_method = self.get_static('html')

        @self._app.route('/html/<name>')
        def html(name):
            return html_method(name)

        # js
        js_method = self.get_static('script','js')

        @self._app.route('/script/<name>')
        def js(name):
            return js_method(name)

        # css
        css_method = self.get_static('css','css')

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

    def get_static(self, sub_dir, ext=None):
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



    def start(self, host='localhost', port=8080):
        logging.debug('started web server at %s port=%s' % (host, port))

        self._server = WSGIServer((host, port), self._app, handler_class=WebSocketHandler)
        self._server.serve_forever()

    def stop(self):
        if self._server:
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
                 profile_handler: ProfileEventHandler,
                 event_handler: EventHandler,
                 channel_handler: ChannelEventHandler,
                 client: ClientPool,
                 settings: Settings,
                 spam_handler: SpamHandlerInterface=None):

        # FIXME always use event handler rather than store
        #  look at standardising the interface for both, at the moment its event handler is actuall the persist handler
        #  ???
        self._event_store = event_handler.store
        self._event_handler = event_handler
        # FIXME - always use profile handler rather than store
        self._profile_store = profile_handler.store
        self._profile_handler = profile_handler

        self._channel_handler = channel_handler
        self._settings = settings
        self._spam_handler = spam_handler

        self._web_sockets = {}
        super(NostrWeb, self).__init__(file_root)

        self._add_routes()

        # to use when no limit given for queries
        self._default_query_limit = 100
        # queries will be limited to this even if caller asks for more, None unlimited
        self._max_query = None

        self._client = client

        self._dedup = DeduplicateAcceptor()

        self._started_at = util_funcs.date_as_ticks(datetime.now())

        # save the relays we attached to so will be the same on next start, this might change as
        # we may allow a forced relay that doesn't allow later changes relays
        self._save_relay_state()

        # session tracking
        session_opts = {
            'session.type': 'file',
            'session.cookie_expires': 60*60*24*365,
            'session.data_dir': './data',
            'session.auto': True
        }
        self._app = beaker.middleware.SessionMiddleware(self._app, session_opts)

    def _add_routes(self):
        # methods wrapped so that if they raise NostrException it'll be returned as json {error: text}
        def _get_err_wrapped(method):
            def _wrapped(**kargs):
                try:
                    return method(**kargs)
                except NostrWebException as ne:
                    return {
                        'error' : ne.args[0]
                    }
            return _wrapped

        # this is used if method didn't raise nostrexception, do something better in static server
        def my_internal(e):
            return str(e).replace(',', '<br>')

        self._app.error_handler = {
            500: my_internal
        }

        self._app.route('/', callback=_get_err_wrapped(self._home_route))
        self._app.route('/profile', callback=_get_err_wrapped(self._profile_route))
        self._app.route('/profiles', method=['POST', 'GET'], callback=_get_err_wrapped(self._profiles_list))

        self._app.route('/local_profiles', callback=_get_err_wrapped(self._local_profiles))
        self._app.route('/update_profile', method='POST', callback=_get_err_wrapped(self._do_profile_update))
        self._app.route('/export_profile', method='POST', callback=_get_err_wrapped(self._export_profile))
        self._app.route('/link_profile', method='POST', callback=_get_err_wrapped(self._link_profile))
        self._app.route('/update_follows',  callback=_get_err_wrapped(self._do_contact_update))

        self._app.route('/channel_for_id', method=['GET'], callback=_get_err_wrapped(self._get_channel_route))
        self._app.route('/channel_matches', method=['POST', 'GET'], callback=_get_err_wrapped(self._channels_list_route))

        # self._app.route('/set_profile', method='POST', callback=_get_err_wrapped(self._set_profile))
        # self._app.route('/current_profile', callback=_get_err_wrapped(self._get_profile))
        self._app.route('/state/js', callback=_get_err_wrapped(self._state))

        # self._app.route('/contact_list',callback=self._contact_list)
        self._app.route('/events', method='POST', callback=_get_err_wrapped(self._events_route))
        self._app.route('/messages', callback=_get_err_wrapped(self._messages))

        self._app.route('/events_text_search', callback=_get_err_wrapped(self._events_text_search_route))
        # self._app.route('/text_events', callback=self._text_events_route)
        self._app.route('/text_events_for_profile', callback=self._text_events_for_profile)
        self._app.route('/event_relay', callback=_get_err_wrapped(self._event_relay_route))

        # self._app.route('/post_text', method='POST', callback=_get_err_wrapped(self._do_post))
        self._app.route('/post_event', method='POST', callback=_get_err_wrapped(self._do_post))

        # current relay connection status
        self._app.route('/relay_status', callback=_get_err_wrapped(self._relay_status))
        # list of relays we can connect to, with some basic order of those we think are better at the top
        self._app.route('/relay_list', callback=_get_err_wrapped(self._relay_list))
        self._app.route('/relay_add', callback=_get_err_wrapped(self._add_relay_route))
        self._app.route('/relay_remove', callback=_get_err_wrapped(self._remove_relay_route))
        self._app.route('/relay_update_mode', callback=_get_err_wrapped(self._relay_mode_route))

        self._app.route('/profile_reactions', callback=_get_err_wrapped(self._reactions_route))
        self._app.route('/do_reaction', callback=_get_err_wrapped(self._do_reaction_route))

        self._app.route('/websocket', callback=self._handle_websocket)
        # self._app.route('/count', callback=self._count)
        self._app.route('/robo_images/<hash_str>', callback=_get_err_wrapped(self._get_robo_route))
        self._app.route('/web_preview', callback=_get_err_wrapped(self._get_web_preview_route))

    # def _count(self):
    #     if 'count' not in self.session:
    #         self.session['count'] = 0
    #
    #     self.session['count'] += 1
    #     return str(self.session['count'])


    def _home_route(self):

        return static_file(filename='home.html', root=self._file_root+'/html/')

    def _check_key(self, key, key_name='pub_k'):
        if not key:
            raise NostrWebException('%s is required' % key_name)
        if not Keys.is_key(key):
            raise NostrWebException('value - %s doesn\'t look like a valid nostr %s' % (key, key_name))

    def _check_event_id(self, event_id):
        if event_id == '':
            raise NostrWebException('event_id required')

        # looks like event id?
        if not Event.is_event_id(event_id):
            raise NostrWebException('%s doesn\'t look like a valid nostr event' % event_id)

    def _get_profile(self, key_field='pub_k', for_sign=False, create_empty=False) -> Profile:
        ret: Profile
        if key_field in request.query:
            p_k = request.query[key_field]
            if not p_k:
                return None
        else:
            return None

        self._check_key(p_k,
                        key_name=key_field)

        ret = self._profile_handler.profiles.lookup_pub_key(p_k)
        if ret is None:
            if create_empty:
                ret = Profile(pub_k=p_k)
            else:
                raise NostrWebException('couldn\'t create profile %s', p_k)
        if for_sign and not ret.private_key:
            raise NostrWebException('can\'t sign events with profile %s', p_k)

        return ret

    def _get_all_contacts_profile(self, pub_k):
        # shortcut, nothing asked for
        if pub_k == '':
            return set([])

        p: Profile
        c: Contact

        self._check_key(pub_k)
        p = self._profile_handler.profiles.get_profile(pub_k)
        if p is None:
            raise NostrWebException('no profile found for pub_k - %s' % pub_k)

        # make contacts
        self._profile_handler.load_contacts(p)
        cons = [c.contact_public_key for c in p.contacts]

        # make followers
        self._profile_handler.load_followers(p)
        fols = p.followed_by

        # finally create ret set with ourself included
        ret = set([pub_k])
        ret.update(cons)
        ret.update(fols)

        return ret

    # see https://stackoverflow.com/questions/31771286/python-in-memory-cache-with-time-to-live
    @staticmethod
    def get_ttl_hash(seconds=3600):
        """Return the same value withing `seconds` time period"""
        return round(time.time() / seconds)

    @lru_cache(maxsize=10)
    def _get_profile_matches(self, match_str, ttl_hash=None):
        return self._profile_handler.matches(match_str,
                                             max_match=None,
                                             search_about=True)

    def _profiles_list(self):
        c_p: Profile
        use_profile: Profile
        limit = self._get_query_limit()
        offset = self._get_query_offset()
        # , list of pub_ks we want profiles for
        pub_k = request.query.pub_k
        match = request.query.match
        # if given and we have include restriction then this is the profile its
        # based on i.e there followers/ follower of follows etc.
        use_pub_k = request.query.use_pub_k

        if request.method == 'POST':
            if 'pub_k' in request.forms:
                pub_k = request.forms['pub_k']

        all_keys = set([])
        if pub_k:
            all_keys = set(pub_k.split(','))

        # alternative to listing pub_k can supply for_profile and all that profiles contacts/followers will be loaded
        # currently just sigular but i guess could be comma seperated list of profiles
        for_profile = self._get_all_contacts_profile(request.query.for_profile)

        # we combine so a profile plus some other p_keys can be requested
        all_keys = all_keys.union(for_profile)

        # match style
        if match:
            for c_m in match.split(','):
                p_matches = self._get_profile_matches(c_m, ttl_hash=self.get_ttl_hash(60))
                p_matches = [c_p.public_key for c_p in p_matches]
                all_keys = all_keys.union(p_matches)

        # single pub_k, is there an include that restricts what we'll return?
        # e.g. profile search page
        if use_pub_k:
            self._check_key(use_pub_k)
            use_profile = self._profile_handler.get_pub_k(use_pub_k)
            for_keys = self._get_for_pub_keys(for_str=request.params.include,
                                              use_profile=use_profile)
            if for_keys is not None:
                if pub_k != '' or match != '':
                    all_keys = all_keys.intersection(set(for_keys))
                else:
                    all_keys = set(for_keys)
        the_profile: Profile
        ret = {
            'profiles': []
        }
        # pub_k, or pub_ks, seperated by ,
        # possibly this will /profile and /profiles methods merged
        # note we don't check the pub_ks, if they're incorrect then nothing will be returned for that pk anyhow
        if pub_k != '' or match != '' or all_keys:
            ret['profiles'] = [ValidatedProfile.from_profile(the_profile)
                               for the_profile in self._profile_handler.get_profiles(list(all_keys)[offset:offset+limit])]

            ProfileList.sort_profiles(ret['profiles'],
                                      inplace=True)

        # eventually this full list will probably have to go
        else:
            all_profiles = ProfileList.sort_profiles(self._profile_handler.profiles,
                                                     inplace=False)
            ret['profiles'] = [ValidatedProfile.from_profile(c_p) for c_p in all_profiles[offset:offset+limit]]

        # dict to send
        ret['profiles'] = [c_p.as_dict() for c_p in ret['profiles']]

        return ret

    def _profile_route(self):

        def get_others(key: str):
            key = 'include_%s' % key
            limit = None
            get_type = None
            types = ('full', 'keys', 'count')
            if key in request.query:
                v = request.query[key]
                if v in types:
                    get_type = v
                if key+'_limit' in request.query:
                    try:
                        limit = int(request.query[key+'_limit'])
                    except ValueError:
                        pass
            return get_type, limit

        the_profile: Profile
        p: Profile
        pub_k = request.query.pub_k
        priv_k = request.query.priv_k
        get_contact, contact_limit = get_others('contacts')
        get_follow, follow_limit = get_others('follows')

        # only used when checking priv_k, we just create a profile with the priv_k and
        # then turn that into pub_k. any supplied pub_k is ignored
        if priv_k:
            self._check_key(priv_k, key_name='priv_k')
            the_profile = Profile(priv_k=priv_k)
            pub_k = the_profile.public_key

        # will throw if we don't think valid pub_k
        self._check_key(pub_k)
        # the_profile = self._profile_handler.profiles.get_profile(pub_k)
        the_profile = self._profile_handler.get_pub_k(pub_k)

        if the_profile is None:
            # raise NostrWebException('no profile found for pub_k - %s' % pub_k)
            # create an adhoc profile
            the_profile = Profile(pub_k=pub_k)

        ret = the_profile.as_dict()

        c: Contact
        # add in contacts if asked for
        if get_contact is not None:
            self._profile_handler.load_contacts(the_profile)
            contact_keys = [c.contact_public_key for c in the_profile.contacts]
            ret['contact_count'] = len(contact_keys)

            # return either keys or profile info up to limit
            if get_contact != 'count':
                if contact_limit:
                    contact_keys = contact_keys[:contact_limit]
                # embed profile info
                if get_contact == 'full':
                    ret['contacts'] = [p.as_dict() for p in self._profile_handler.get_profiles(contact_keys)]
                # just the keys
                else:
                    ret['contacts'] = contact_keys

        # the same but for follows, we may need to think about this with our changed db structure
        # load contacts/follows should be changed to take profile helper
        if get_follow is not None:
            self._profile_handler.load_followers(the_profile)
            follow_keys = the_profile.followed_by
            ret['follow_count'] = len(follow_keys)
            # return either keys or profile info up to limit
            if get_follow != 'count':
                if follow_limit:
                    follow_keys = follow_keys[:follow_limit]
                if get_follow == 'full':
                    ret['followed_by'] = [p.as_dict() for p in self._profile_handler.get_profiles(follow_keys)]
                else:
                    ret['followed_by'] = follow_keys

        return ret

    def _link_profile(self):
        pub_k = request.query.pub_k
        priv_k = request.query.priv_k

        # make sure both keys are valid
        self._check_key(priv_k, key_name='priv_k')
        self._check_key(pub_k)

        the_profile = Profile(priv_k=priv_k)
        if the_profile.public_key != pub_k:
            raise NostrWebException('priv_k: %s doesn\'t match supplied pub_k: %s' % (priv_k, pub_k))

        the_profile = self._profile_handler.get_pub_k(pub_k)
        the_profile.update_at = datetime.now()

        if the_profile is None:
            raise NostrWebException('no profile found for pub_k - %s' % pub_k)

        the_profile = copy(the_profile)
        the_profile.private_key = priv_k
        self._profile_handler.do_update_local(the_profile)

        return {
            'success': True,
            'profile': the_profile.as_dict()
        }


    def _export_profile(self):
        """
            because we don't currently have any auth for the server don't want to allow show priv_key
            instead this method that'll save profile_info to csv for given profile_name
        """
        for_name = request.query.for_profile
        out_file = '%s/%s.csv' % (Path.home(), for_name)

        if for_name == '':
            raise NostrWebException('for_profile is expected')

        the_profile = self._profile_handler.profiles.lookup_profilename(for_name)
        if the_profile is None:
            raise NostrWebException('unable to find profile: %s' % for_name)

        self._profile_handler.store.export_file(out_file, [for_name])

        return {
            'success': True,
            'output': out_file
        }


    def _local_profiles(self):
        """
        :return: profiles that we have priv_k for
        """
        return {
            'profiles': [c_p.as_dict() for c_p in self._profile_handler.local_profiles()]
        }

    def _get_channel_matches(self, match_str, ttl_hash=None):
        return self._channel_handler.channels.matches(match_str,
                                                      max_match=None,
                                                      search_about=True)

    def _channels_filter(self, channels):
        pub_k = request.query.pub_k
        if pub_k:
            self._check_key(pub_k)
            use_profile = self._profile_handler.profiles.lookup_pub_key(pub_k)

            # channels created by these keys
            create_keys = request.params.include
            if create_keys:
                create_keys = self._get_for_pub_keys(for_str=create_keys,
                                                     use_profile=use_profile)
                if create_keys:
                    create_keys = set(create_keys)
                    channels = [c_c for c_c in channels if c_c.create_pub_k in create_keys]

            # channels with post by these keys
            post_keys = request.params.post_from
            if post_keys:
                post_keys = self._get_for_pub_keys(for_str=request.params.post_from,
                                                   use_profile=use_profile)
                if post_keys:
                    post_channels = self._channel_handler.store.channels_for_keys(post_keys)
                    channels = [c_c for c_c in channels if c_c.event_id in post_channels]

        return channels

    def _get_channel_route(self):
        """
        get a single channel via its id
        :return:
        """
        channel_id = request.query.id
        if not channel_id:
            raise NostrWebException('id is required')

        self._check_key(channel_id, 'id')
        the_channel = self._channel_handler.get_id(channel_id)
        # similar to profiles not having hte channel info doesn't mean there might not be messages for a given
        # channel key
        if the_channel is None:
            raise NostrWebException('channel info not found')

        match = request.query.match
        cl = ChannelList([the_channel])
        the_channel = self._channels_filter(cl.matches(match))

        if the_channel:
            return the_channel[0].as_dict()
        else:
            return {}

    def _channels_list_route(self):
        limit = self._get_query_limit()
        offset = self._get_query_offset()
        pub_k = request.query.pub_k
        match = request.query.match
        use_profile: Profile
        channels = []
        c_c: Channel

        # match style
        for c_m in match.split(','):
            channels = channels + self._get_channel_matches(c_m, self.get_ttl_hash(60))

        channels = self._channels_filter(channels)

        return {
            'channels': [c_c.as_dict() for c_c in channels[offset:offset+limit]]
        }

    @property
    def session(self):
        return request.environ.get('beaker.session')

    # def _do_post(self):
    #     pub_k = request.forms['pub_k']
    #     msg_text = request.forms['text']
    #
    #     self._check_key(pub_k)
    #     the_profile = self._profile_handler.profiles.get_profile(pub_k)
    #     if the_profile is None:
    #         raise Exception('no profile found for pub_k - %s' % pub_k)
    #     if the_profile.private_key is None:
    #         raise Exception('don\'t have private key for pub_k - %s' % pub_k)
    #
    #
    #     evt = Event(kind=Event.KIND_TEXT_NOTE,
    #                 content=msg_text,
    #                 pub_key=pub_k)
    #     evt.sign(the_profile.private_key)
    #
    #     self._client.publish(evt)
    #
    #     return evt.event_data()

    def _do_post(self):
        pub_k = request.query.pub_k
        event = json.loads(request.forms.getunicode('event'))
        # content = event['content']
        # content = request.forms.getunicode('content')

        tags = event['tags']
        kind = event['kind']
        content = event['content']
        if not pub_k:
            raise NostrWebException('pub_k is required')

        self._check_key(pub_k)
        profile = self._profile_handler.profiles.lookup_pub_key(pub_k)

        if profile is None:
            raise NostrWebException('no profile found for pub_k: %s', pub_k)
        if profile.private_key is None:
            raise NostrWebException('Need to be using a profile with private_key to make posts')

        evt = Event(kind=kind,
                    content=content,
                    pub_key=pub_k,
                    tags=tags)

        if kind == Event.KIND_ENCRYPT:
            to_pub = None
            for c_p in evt.p_tags:
                if c_p != pub_k:
                    to_pub = c_p
                    break

            if to_pub is None:
                raise NostrWebException('no to pub_k in tags for encrypted post?!')

            evt.content = evt.encrypt_content(profile.private_key, to_pub)

        evt.sign(profile.private_key)
        self._client.publish(evt)

        return evt.event_data()

    def _do_profile_update(self):
        """
            update and or save a profile
        """

        def create_new():
            n_p = Profile(priv_k=Keys.get_new_key_pair()['priv_k'],
                          profile_name=profile_name)

            self._profile_handler.do_update_local(n_p)

            return n_p.public_key

        def link_existing():
            self._check_key(private_k, 'private_key')
            n_p = Profile(priv_k=private_k,
                          profile_name=profile_name)
            self._profile_handler.do_update_local(n_p)
            return n_p.public_key

        profile = json.loads(request.forms['profile'])
        pub_k = profile['pub_k']
        picture = profile['picture']
        name = profile['name']
        about = profile['about']

        save = request.forms['save'] == 'true'
        publish = request.forms['publish'] == 'true'
        private_k = profile['private_key']
        profile_name = profile['profile_name']
        mode = request.forms['mode']

        # sometimes we're creating new profiles adding priv_k to
        # link to existing
        if mode == 'create':
            pub_k = create_new()
        elif mode == 'link':
            pub_k = link_existing()

        # edit a profile we already have or just created linked above

        self._check_key(pub_k)
        the_profile = self._profile_handler.get_pub_k(pub_k)
        if the_profile is None:
            raise Exception('no profile found for pub_k - %s' % pub_k)

        # you can't update someone elses profile and definetly can't publish it
        if the_profile.private_key is None:
            raise Exception('don\'t have private key for pub_k - %s' % pub_k)

        # ok all looks good lets do this
        ret = {}
        update_profile = Profile(priv_k=the_profile.private_key,
                                 pub_k=the_profile.public_key,
                                 attrs={
                                    'picture': picture,
                                    'name': name,
                                    'about': about
                                 },
                                 profile_name=profile_name,
                                 update_at=datetime.now())

        if save is True:
            # this will do the update for profile name
            self._profile_handler.do_update_local(update_profile)
            ret['save'] = True

        if publish is True:
            evt = update_profile.get_meta_event()
            evt.sign(update_profile.private_key)
            self._client.publish(evt)
            ret['publish'] = True

        ret['profile'] = update_profile.as_dict()

        return ret

    def _do_contact_update(self):
        pub_k = request.query.pub_k
        follow = request.query.to_follow
        unfollow = request.query.to_unfollow
        follow_list = []
        unfollow_list = []

        def check_keys(to_check):
            for c_key in to_check:
                if Keys.is_key(c_key) is not True:
                    raise NostrWebException('%s is not a valid nostr key' % c_key)

        self._check_key(pub_k)

        profile: Profile = self._profile_handler.get_pub_k(pub_k)

        if profile is None:
            raise NostrWebException('Profile not found for pub_k: %s' % pub_k)
        if not profile.private_key:
            raise NostrWebException('don\'t have the private key to sign for given pub_k: %s' % pub_k)

        if follow != '':
            follow_list = follow.split(',')

        if unfollow != '':
            unfollow_list = unfollow.split(',')

        if not follow_list and not unfollow_list:
            raise NostrWebException('follow or unfollow pks required')

        check_keys(follow_list)
        check_keys(unfollow_list)

        self._profile_handler.load_contacts(profile)
        my_contacts = profile.contacts

        con: Contact
        actually_followed = []
        actually_unfollowed = []

        # do the adds
        for pub_k in follow_list:
            con = Contact(owner_pub_k=profile.public_key,
                          updated_at=None,
                          contact_pub_k=pub_k)
            if my_contacts.add(con):
                actually_followed.append(pub_k)
        # do the rems
        for pub_k in unfollow_list:
            if my_contacts.remove(pub_k):
                actually_unfollowed.append(pub_k)

        # if actually_followed or actually_unfollowed:
        my_contacts.updated_at = util_funcs.date_as_ticks(datetime.now())

        # publish
        c_evt = my_contacts.get_contact_event()
        c_evt.sign(profile.private_key)
        self._client.publish(c_evt)

        ret_profile = profile.as_dict()
        ret_profile['contacts'] = my_contacts.follow_keys()

        return {
            'profile': ret_profile,
            'followed': actually_followed,
            'unfollowed': actually_unfollowed
        }

    # def _update_session_profile(self, p: Profile=None):
    #     if p is None:
    #         p = {}
    #     else:
    #         p.load_contacts(self._profile_store, reload=True)
    #         follows = p.contacts
    #         p = p.as_dict(with_private_key=True)
    #         c: Contact
    #         p['follows'] = [c.contact_public_key for c in follows]
    #
    #     self.session['profile'] = p
    #     self.session.save()
    #
    #     return p

    # def _set_profile(self):
    #     """
    #     set the profile that will be used when perfoming any action,
    #         TODO: on some pages it will also change what the users sees and how its displayed
    #          note currently there is no authentication it assumed that if you can see the web server then it safe
    #          it could be served over tor and use their basic auth now I think...
    #          or we can add some sort of basic auth (if available over web you'd want to serve over SSL...)
    #     :return: profile if it was found
    #     """
    #     p_name = request.query.profile
    #     # if no profile then assumed set to lurker profile
    #     p: Profile = None
    #     if p_name != '':
    #         profiles = self._profile_store.select({
    #             'private_key': p_name,
    #             'public_key': p_name,
    #             'profile_name': p_name
    #         }, profile_type=ProfileType.LOCAL)
    #
    #         if not len(profiles):
    #             raise Exception('no profile found for key: %s' % p_name)
    #
    #         p = profiles[0]
    #
    #     return self._update_session_profile(p)

    def _state(self):
        """
        special route to return a js file that reflects some state on the server
        currently this is only current profile but probbaly include othere settings
        it should mainly things that we hold in the session var
        don't do too much here, for most things its better to make requests as needed
        :return:
        """

        state = {
            'relay_status': DateTimeEncoder().encode(self._client.status),
            'profiles_url': self._settings.get('profiles_url', 'https://robohash.org/'),
            'enable_media': self._settings.get('enable_media', True) != '0',
        }

        return """
            APP.nostr.data.server_state = %s
        """ % (json.dumps(state))

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

    def _decrypt_event_content_as_user(self, evt, decrypt_p: Profile) -> str:
        ret = 'unable to decrypt...'
        if evt.kind == Event.KIND_ENCRYPT and decrypt_p and decrypt_p.private_key:

            try:
                use_pub = evt.pub_key
                if evt.pub_key == decrypt_p.public_key:
                    for c_p in evt.p_tags:
                        if c_p != decrypt_p.public_key:
                            use_pub = c_p
                            break
                ret = evt.decrypted_content(priv_key=decrypt_p.private_key,
                                            pub_key=use_pub)
            except Exception as e:
                pass

        return ret

    def _serialise_event(self, c_evt, use_profile: Profile = None):
        """
        converts {} to event and then back to {} so it'll be as front end expects
        extra fields not used by event also returned
        :param c_evt: event data, possible with extra filds that'll be added as is
        :param decrypt_p, use the profile for decrypting NIP4 content
        :return:
        """
        as_evt = Event.from_JSON(c_evt)
        ret = {**c_evt, **as_evt.event_data()}
        if use_profile and as_evt.kind == Event.KIND_ENCRYPT:
            ret['content'] = self._decrypt_event_content_as_user(as_evt, use_profile)

        if 'react_event' in ret:
            ret['react_event'] = self._serialise_event(c_evt['react_event'], use_profile)

        if 'reply_events' in ret:
            ret['reply_events'] = [self._serialise_event(c_evt, use_profile) for c_evt in ret['reply_events']]

        return ret

    def _get_events(self,
                    filter,
                    use_profile: Profile=None,
                    embed_reactions=True,
                    add_reactions_flag=True,
                    embed_replies=False) -> []:

        return [self._serialise_event(c_evt, use_profile) for
                c_evt in self._event_handler.get_events(filter=filter,
                                                        use_profile=use_profile,
                                                        embed_reactions=embed_reactions,
                                                        add_reactions_flag=add_reactions_flag,
                                                        embed_replies=embed_replies)]

    def _get_for_pub_keys(self, for_str, use_profile: Profile):
        """
        for where we're restricting to set pub keys i.e. filter on search events page
        :param for_str: followersplus, followers, self anything else is everyone/not applied
        :param use_profile: followers worked out from ths profile
        :return: None = everyone
        """
        ret = None
        for_str = for_str.lower()
        # restrict only to followers
        if for_str and use_profile:
            if for_str == 'followersplus':
                self._profile_handler.load_followers(use_profile)
                followers = use_profile.followed_by
                c_p: Profile
                all_follows = set(followers)
                for k in followers:
                    c_p = self._profile_handler.get_pub_k(k)
                    if c_p:
                        self._profile_handler.load_contacts(c_p)
                        all_follows = all_follows.union(set(c_p.contacts.follow_keys()))

                ret = list(all_follows)

            if for_str == 'followers':
                self._profile_handler.load_contacts(use_profile)
                ret = use_profile.contacts.follow_keys()
            elif for_str =='self':
                ret = [use_profile.public_key]

        return ret

    # @lru_cache(maxsize=100)
    # def _query_realy_fallback(self, filter):
    #     evt: Event
    #     filter = json.loads(filter)
    #     ret = [evt.event_data() for evt in self._client.query(filter)]
    #     return ret[:filter[0]['limit']]


    def _events_route(self):
        """
        returns events that match given nostr filter [{},...]
        :return:
        """
        pub_k = request.query.pub_k
        use_profile: Profile = None
        embed_replies = request.query.embed_replies.lower() == 'true'

        if pub_k:
            self._check_key(pub_k)
            use_profile = self._profile_handler.profiles.lookup_pub_key(pub_k)

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
            if 'limit' not in filter[0] or filter[0]['limit'] > limit:
                filter[0]['limit'] = limit

        # r_evts = self._get_events(filter,
        #                           use_profile=use_profile,
        #                           embed_replies=embed_replies)
        #
        # if len(r_evts) < limit:
        #     if r_evts:
        #         filter[0]['until'] = r_evts[-1]['created_at']
        #         filter[0]['limit'] = limit-len(r_evts)
        #
        #     r_evts = r_evts + self._query_realy_fallback(json.dumps(filter))

        return {
            'events': self._get_events(filter,
                                       use_profile=use_profile,
                                       embed_replies=embed_replies)
        }

    def _messages(self):
        pub_k = request.query.pub_k
        use_profile: Profile = None
        self._check_key(pub_k)
        use_profile = self._profile_handler.profiles.lookup_pub_key(pub_k)
        if use_profile is None:
            raise NostrWebException('unable to find profile for decryption pub_k: %s', pub_k)

        # get the top message for everyone we
        filter = {
            'ids': []
        }
        dms = self._event_store.direct_messages(pub_k)
        for c_dm in dms:
            filter['ids'].append(c_dm['event_id'])
        ret = []
        if dms:
            ret = self._get_events(filter,
                                   use_profile=use_profile)

        return {
            'events': ret
        }

    def _events_text_search_route(self):
        search_str = request.query.search_str

        use_profile: Profile = None
        pub_k = request.query.pub_k
        if pub_k:
            self._check_key(pub_k)
            use_profile = self._profile_handler.profiles.lookup_pub_key(pub_k)

        def extract_tag(tag_prefix, text, with_pat=None):
            if with_pat is None:
                with_pat = '\\%s(\w*)' % tag_prefix

            matches = re.findall(with_pat, text)
            for c_match in matches:
                text = text.replace(tag_prefix + c_match, '')

            return matches, text

        def find_authors(prefixes, search_profiles: ProfileList):
            c_p: Profile
            m_find = 100
            ret = []

            for c_pre in prefixes:
                auth_match = search_profiles.matches(c_pre, m_find)
                if auth_match:
                    ret = ret + [c_p.public_key for c_p in auth_match]
                    if len(ret) > m_find:
                        break

            return ret[:m_find-1]

        filter = {
            'limit': self._get_query_limit(),
            'kinds': [Event.KIND_TEXT_NOTE]
        }

        # pow is just events with leading 000s, user could manually do &000... if they want ot any q
        pow = request.params.pow.lower()
        if pow and pow != 'none':
            filter['ids'] = [pow]

        for_followers = self._get_for_pub_keys(for_str=request.params.include,
                                               use_profile=use_profile)
        if for_followers is not None:
            filter['authors'] = for_followers

        until = self._get_query_int('until', default_value='')
        if until != '':
            filter['until'] = until

        if search_str.replace(' ', ''):
            # add hash tags to filter
            hashtags, search_str = extract_tag('#', search_str)
            if hashtags:
                # filter['#hashtag'] = hashtagsnow
                filter['#t'] = hashtags

            # add authors to filter
            author_pres, search_str = extract_tag('@', search_str)
            if author_pres:
                search_profiles = self._profile_handler.profiles
                # filter on authors already so only search these
                if 'authors' in filter:
                    c_p: Profile
                    search_profiles = ProfileList([c_p for c_p in search_profiles if c_p.public_key in filter['authors']])

                authors = find_authors(author_pres, search_profiles)
                if authors:
                    filter['authors'] = authors
                else:
                    # nothing should match
                    return {
                        'events': []
                    }

            search_str = ' '.join(search_str.split())

            # subject search... note if present this is greeding and will take all the rest of the content
            subject, search_str = extract_tag('$', search_str, with_pat='\$([\s\w\-\.]*)')
            if subject:
                filter['#subject'] = subject

            # event id
            ids_pres, search_str = extract_tag('&', search_str)
            if ids_pres:
                if 'ids' not in filter:
                    filter['ids'] = ids_pres
                # where pow and & then the pow is added before user given prefix
                else:
                    filter['ids'] = [pow+pre for pre in ids_pres]

            if search_str:
                filter['content'] = search_str

            # this works but as tag search #e is only for full id have removed for now
            # because its confusing.... maybe add prefix search just for #e?(#p)
            # so event search looks both for events of that id and those that ref it
            # if 'ids' in filter:
            #     ref_copy = filter.copy()
            #     ref_copy['#e'] = ref_copy['ids']
            #     del ref_copy['ids']
            #     filter = [
            #         filter,
            #         ref_copy
            #     ]

        # this stops the network fetcher looking for addtional events even where we don't hit the limit
        # we do this because somethings just don't work over relay fetch e.g. content search
        # but also things like requesting to many authors are a problem and this just makes it easier to be consistant
        # search only searches local data
        filter['no-fetch'] = True
        evts = self._get_events(filter, use_profile)

        return {
            'events': evts
        }

    def _get_query_int(self, field, default_value=None):
        try:
            ret = int(request.query[field])
        except:
            if default_value is not None:
                ret = default_value
            else:
                raise NostrWebException('error getting query int %s and no default value given' % field)
        return ret

    def _get_query_limit(self):
        ret = self._get_query_int('limit', default_value=self._default_query_limit)

        if self._max_query and ret > self._max_query:
            ret = self._max_query
        return ret

    def _get_query_offset(self):
        return self._get_query_int('offset', default_value=0)

    def _text_events_route(self):
        """
        all the text notes for a given pub_key
        :return:
        """
        pub_k = request.query.pub_k

        # will throw if we don't think valid pub_k
        self._check_key(pub_k)

        return {
            'events': self._get_events({
                'authors': [pub_k],
                'kinds': [Event.KIND_TEXT_NOTE],
                'limit': self._get_query_limit()
            })
        }

    def _event_relay_route(self):
        event_id = request.query.event_id
        self._check_event_id(event_id)

        # ok take a look which relays we saw at, TODO add date to event_relay

        return {
            'relays': self._event_store.event_relay(event_id)
        }

    def _text_events_for_profile(self):
        """
        get texts notes for pub_k or those we have as contacts
        :return:
        """
        pub_k = request.query.pub_k

        # will throw if we don't think valid pub_k
        self._check_key(pub_k)

        limit = self._get_query_limit()

        for_profile = self._profile_handler.get_profiles(pub_k,
                                                         create_missing=True)[0]
        self._profile_handler.load_contacts(for_profile)

        c: Contact

        filter = [
            {
                'authors': [pub_k] + [c.contact_public_key for c in for_profile.contacts],
                'kinds': [Event.KIND_TEXT_NOTE],
                'limit': limit
            },
            {
                'kinds': [Event.KIND_TEXT_NOTE],
                '#p': [pub_k]
            }]

        until = self._get_query_int('until', default_value='')
        if until != '':
            filter[0]['until'] = until
            filter[1]['until'] = until

        return {
            'events': self._get_events(filter,
                                       use_profile=for_profile),
            'filter': filter
        }

    def _reactions_route(self):
        v_profile = self._get_profile(key_field='view_pub_k',
                                      create_empty=True)
        r_filter = {
            'kinds': [Event.KIND_REACTION],
            'authors': [v_profile.public_key],
            'limit': self._get_query_limit()
        }

        until = self._get_query_int('until', default_value='')
        if until != '':
            r_filter['until'] = until

        # ret = self._get_events(filter=r_filter)
        ret = self._get_events(filter=r_filter,
                               use_profile=self._get_profile())

        # if request.query.pub_k:
        #     use_profile = self._get_profile()
        #     ret = self._add_reacted_to(p=use_profile,
        #                                evts=ret)

        ret = [self._serialise_event(c_evt) for c_evt in ret]

        return {
            'events': ret
        }

    def _do_reaction_route(self):
        """
        do a reaction, currently only suporting on/off type reactions e.g.
        like which is the only one the front end support anyhow
        :return:
        """
        p = self._get_profile(for_sign=True)

        event_id = request.query.event_id
        self._check_event_id(event_id)

        reaction = request.query.reaction
        active = request.query.active.lower() == 'true'

        # get event we're reacting to
        r_evt = self._event_handler.get_events_by_ids([event_id])

        if not r_evt:
            raise NostrWebException('couldn\'t find event reacting to, event_id: %s' % event_id)

        r_evt = Event.from_JSON(r_evt[0])
        my_react_event = Event(kind=Event.KIND_REACTION,
                               content=reaction,
                               tags=[
                                   ['p', r_evt.pub_key],
                                   ['e', r_evt.id]
                               ],
                               pub_key=p.public_key)

        c_evt: Event

        react_events = self._event_handler.get_events({
            'kinds': [Event.KIND_REACTION],
            '#e': [event_id],
            'authors': p.public_key
        })

        to_del = []
        for c_evt in react_events:
            e_tags = EventTags(c_evt['tags']).e_tags
            if e_tags and e_tags[len(e_tags)-1] == event_id \
                    and self._event_handler.reaction_lookup(reaction) == self._event_handler.reaction_lookup(c_evt['content']):
                to_del.append(['e', c_evt['id']])

        del_evt: Event = Event(kind=Event.KIND_DELETE,
                               content='user undid reaction',
                               pub_key=p.public_key,
                               tags=to_del)

        # insert new like
        if active is True:
            my_react_event.sign(p.private_key)
            self._client.publish(evt=my_react_event)

        # rem any old
        if to_del:
            del_evt.sign(p.private_key)
            self._client.publish(evt=del_evt)
            # do local delete - don't worry about seeing callback we can't rely on relays anyhow
            self._event_store.do_delete(del_evt)

        # ok for now - we only do likes...
        return {
            'liked': active
        }


    def _relay_status(self):
        # response.set_header('Content-type', 'application/json')
        return json.loads(DateTimeEncoder().encode(self._client.status))

    def _save_relay_state(self):
        # state = []
        # cr_state = self._relay_status()['relays']
        # for c_relay in cr_state:
        #     the_relay = cr_state[c_relay]
        #     state.append({
        #         'client': c_relay,
        #         'read': the_relay['read'],
        #         'write': the_relay['write']
        #     })

        self._settings.put('relays', json.dumps(self._client.clients))

    def _relay_list(self):
        pub_k = request.query.pub_k
        if pub_k:
            self._check_key(pub_k)
        else:
            pub_k = None

        return {
            'relays': self._event_store.relay_list(pub_k)
        }

    def _check_relay_url(self, url):
        if url == '':
            raise NostrWebException('url is required')

        if url.find('ws://') != 0 and url.find('wss://') != 0:
            raise NostrWebException('%s doesn\'t look like a websocket url' % url)

    def _get_rw_mode(self):
        mode = request.query.mode
        read = True
        write = True

        if 'read' not in mode:
            read = False
        if 'write' not in mode:
            write = False

        return read, write

    def _add_relay_route(self):
        url = request.query.url.lstrip()
        read, write = self._get_rw_mode()

        # just incase, though this isn't possible from the front end it could be done by url directly
        # and the gui doesn't currently have a way to show not read or write... and whats the point anyway
        # just delete
        if read is False and write is False:
            raise NostrWebException('Error adding relay neither read or write is true')

        self._check_relay_url(url)

        try:
            self._client.add({
                'client': url,
                'read': read,
                'write': write
            })
            self._save_relay_state()
        except Exception as e:
            raise NostrWebException(str(e))

        return {
            'success': 'relay %s added' % url
        }

    def _remove_relay_route(self):
        url = request.query.url.lstrip()
        self._check_relay_url(url)

        try:
            self._client.remove(url)
            self._save_relay_state()
        except Exception as e:
            raise NostrWebException(str(e))

        return {
            'success': 'relay %s removed' % url
        }

    def _relay_mode_route(self):
        url = request.query.url.lstrip()
        read, write = self._get_rw_mode()
        self._check_relay_url(url)
        try:
            self._client.set_read_write(url, read, write)
            self._save_relay_state()
        except Exception as e:
            raise NostrWebException(str(e))

        return {
            'success': 'relay %s mode updated to %s' % (url, request.query.mode)
        }

    @lru_cache(maxsize=5000)
    def _get_robo(self, val):
        ret = None

        def my_assemble():
            nonlocal ret
            rh = Robohash(val)
            rh.assemble(roboset='set1', sizex=128,sizey=128)
            image_buffer = BytesIO()
            rh.img.save(image_buffer, format='png')
            image_buffer.seek(0)
            ret = image_buffer.read()

        from gevent.thread import Greenlet

        g = Greenlet(my_assemble())
        g.start()
        g.join()



        return ret

    def _get_robo_route(self, hash_str):
        response.set_header('Content-type', 'image/png')
        return self._get_robo(hash_str)

    @lru_cache()
    def _get_web_preview(self, for_url):
        p = webpreview(for_url)
        return {
            'title': p.title,
            'description': p.description,
            'img': p.image
        }

    def _get_web_preview_route(self):
        for_url = request.query.for_url
        if not for_url:
            raise NostrWebException('parameter for_url is required')
        return self._get_web_preview(for_url)

    def is_spam(self, evt:Event):
        """
        obv this should be something handed in that can be more configurable but ok for now
        :param evt:
        :return:
        """
        return evt.content == '' or evt.content.startswith('{')

    def do_event(self, sub_id, evt: Event, relay):
        if self._spam_handler and self._spam_handler.is_spam(evt):
            logging.debug('ignoring spam event: %s' % evt)
            return

        if self._dedup.accept_event(evt):

            # # will update our profiles if meta/contact type data
            # self._profile_handler.do_event(sub_id, evt, relay)
            #
            # # and channels
            # self._channel_handler.do_event(sub_id, evt, relay)

            # push the event to our web sockets, only those events that have a time
            # otherwise client will get flooded with events if server is being started and there
            # are a lot of events to catch up on or db has just been created and maybe all old events
            # are being imported
            if evt.created_at_ticks > self._started_at:
                evt_data = evt.event_data()
                self.send_data(['event', evt_data])

    def send_data(self, the_data):
        for c_sock in self._web_sockets:
            try:
                ws = self._web_sockets[c_sock]['ws']
                pub_k = self._web_sockets[c_sock]['pub_k']
                send_data = the_data
                if the_data[0] == 'event':
                    use_profile = self._profile_handler.profiles.lookup_pub_key(pub_k)
                    evt_data = the_data[1]
                    if evt_data['kind'] == Event.KIND_REACTION and use_profile:
                        the_data[1] = self._event_handler.add_reaction_events(use_profile, [evt_data])[0]
                    send_data = ['event', self._serialise_event(the_data[1], use_profile)]

                ws.send(DateTimeEncoder().encode(send_data))
            except Exception as e:
                logging.debug('NostrWeb::send_data - %s' % e)

    def _handle_websocket(self):
        pub_k = request.query.pub_k
        logging.debug('Websocket opened given pub_k - %s' % pub_k)
        wsock = request.environ.get('wsgi.websocket')
        if not wsock:
            abort(400, 'Expected WebSocket request.')

        self._web_sockets[str(wsock)] = {
            'ws': wsock,
            'pub_k': pub_k
        }
        while True:
            try:
                # this is just to keep alive, currently we're doing nothing with dead sockets....
                wsock.receive()
            except WebSocketError:
                break
        # clean up
        try:
            del self._web_sockets[str(wsock)]
        except Exception as e:
            print('something bad happened?!?!?!??!?!?!?!')
