from __future__ import annotations
from typing import TYPE_CHECKING

import beaker.middleware
import cryptography.x509

if TYPE_CHECKING:
    pass

import json
from json import JSONEncoder
from datetime import datetime
import re
from json import JSONDecodeError
from bottle import request, Bottle, static_file, abort
from beaker import session

import logging
from pathlib import Path
from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.websocket import WebSocket
from geventwebsocket.handler import WebSocketHandler
from nostr.event.event import Event
from nostr.ident.profile import ProfileList, Profile, Contact, ContactList
from nostr.ident.persist import SQLiteProfileStore, ProfileType
from nostr.event.persist import ClientEventStoreInterface, SQLiteEventStore
from nostr.encrypt import Keys
from nostr.client.client import ClientPool, Client
from nostr.client.event_handlers import DeduplicateAcceptor, ProfileEventHandler
from nostr.util import util_funcs
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
                 event_store: ClientEventStoreInterface,
                 profile_handler: ProfileEventHandler,
                 client: Client):

        self._event_store = event_store
        self._profile_handler = profile_handler
        self._profile_store = profile_handler.store

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
            def _wrapped():
                try:
                    return method()
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
        self._app.route('/profile', callback=_get_err_wrapped(self._profile))
        self._app.route('/profiles', method=['POST', 'GET'], callback=self._profiles_list)
        self._app.route('/local_profiles', callback=_get_err_wrapped(self._local_profiles))
        self._app.route('/update_profile', method='POST', callback=_get_err_wrapped(self._do_profile_update))
        self._app.route('/export_profile', method='POST', callback=_get_err_wrapped(self._export_profile))
        self._app.route('/link_profile', method='POST', callback=_get_err_wrapped(self._link_profile))
        self._app.route('/update_follows',  callback=_get_err_wrapped(self._do_contact_update))

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

        self._app.route('/websocket', callback=self._handle_websocket)
        self._app.route('/count', callback=self._count)


    def _count(self):
        if 'count' not in self.session:
            self.session['count'] = 0

        self.session['count'] += 1
        return str(self.session['count'])


    def _home_route(self):

        return static_file(filename='home.html', root=self._file_root+'/html/')

    def _check_key(self, key, key_name='pub_k'):
        if not key:
            raise NostrWebException('%s is required' % key_name)
        if not Keys.is_key(key):
            raise NostrWebException('value - %s doesn\'t look like a valid nostr %s' % (key, key_name))

    def _get_all_contacts_profile(self, pub_k):
        # shortcut, nothing asked for
        if pub_k == '':
            return set([])

        p: Profile
        c: Contact

        self._check_key(pub_k)
        p = self._profile_handler.profiles.get_profile(pub_k)
        if p is None:
            raise Exception('no profile found for pub_k - %s' % pub_k)

        # make contacts
        cons = [c.contact_public_key for c in p.load_contacts(self._profile_store)]

        # make followers'
        fols = [c.owner_public_key for c in p.load_followers(self._profile_store)]

        # finally create ret set with ourself included
        ret = set([pub_k])
        ret.update(cons)
        ret.update(fols)

        return ret

    def _profiles_list(self):
        # , list of pub_ks we want profiles for
        pub_k = request.query.pub_k
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
                else:
                    ret['profiles'].append({
                        'pub_k': c_pub_k
                    })

        # eventually this full list will probably have to go
        else:
            ret['profiles'] = self._profile_handler.profiles.as_arr()

        return ret

    def _profile(self):
        the_profile: Profile
        pub_k = request.query.pub_k
        priv_k = request.query.priv_k
        include_contacts = request.query.include_contacts.lower() == 'true'
        include_followers = request.query.include_followers.lower() == 'true'
        full_profiles = request.query.full_profiles.lower() == 'true'

        def get_profile(key):
            f_profile = self._profile_handler.profiles.lookup_pub_key(key)
            if f_profile is not None:
                f_profile = f_profile.as_dict()
            else:
                f_profile= {
                    'pub_k': key
                }
            return f_profile

        # only used when checking priv_k, we just create a profile with the priv_k and
        # then turn that into pub_k. any supplied pub_k is ignored
        if priv_k:
            self._check_key(priv_k,key_name='priv_k')
            the_profile = Profile(priv_k=priv_k)
            pub_k = the_profile.public_key

        # will throw if we don't think valid pub_k
        self._check_key(pub_k)
        the_profile = self._profile_handler.profiles.get_profile(pub_k)
        if the_profile is None:
            raise NostrWebException('no profile found for pub_k - %s' % pub_k)

        ret = the_profile.as_dict()

        c: Contact
        # add in contacts if asked for
        if include_contacts is True:
            the_profile.load_contacts(self._profile_store)
            if full_profiles:
                ret['contacts'] = [get_profile(c.contact_public_key) for c in the_profile.contacts]
            # just keys
            else:
                ret['contacts'] = [c.contact_public_key for c in the_profile.contacts]

        # add in follows if asked for
        if include_followers is True:
            the_profile.load_followers(self._profile_store)
            if full_profiles:
                ret['followed_by'] = [get_profile(c.owner_public_key) for c in the_profile.followed_by]
            else:
                ret['followed_by'] = [c.owner_public_key for c in the_profile.followed_by]

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

        the_profile = self._profile_handler.profiles.get_profile(pub_k)



        if the_profile is None:
            raise NostrWebException('no profile found for pub_k - %s' % pub_k)

        from copy import copy
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

        self._profile_store.export_file(out_file, [for_name])

        return {
            'success': True,
            'output': out_file
        }


    def _local_profiles(self):
        """
        :return: profiles that we have priv_k for
        """
        profiles = self._profile_store.select_profiles(profile_type=ProfileType.LOCAL)
        c_p: Profile

        ret = {
            'profiles': [c_p.as_dict() for c_p in profiles]
        }
        return ret

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
        event = json.loads(request.forms['event'])
        content = event['content']

        tags = event['tags']
        kind = event['kind']
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
        the_profile = self._profile_handler.profiles.get_profile(pub_k)
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
                                    'picture' : picture,
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

        profile: Profile = self._profile_handler.profiles.get_profile(pub_k)

        if profile is None:
            raise NostrWebException('Profile not found for pub_k: %s' % pub_k)
        if not profile.private_key:
            raise NostrWebException('don\'t have the private key to sign for given pub_k: ' % pub_k)

        if follow != '':
            follow_list = follow.split(',')

        if unfollow != '':
            unfollow_list = unfollow.split(',')

        if not follow_list and not unfollow_list:
            raise NostrWebException('follow or unfollow pks required')

        check_keys(follow_list)
        check_keys(unfollow_list)

        my_contacts = ContactList(contacts=profile.load_contacts(self._profile_store).contacts,
                                  owner_pub_k=profile.public_key)

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

        # just local, as we always publish may go and rely on the save that gets done when we see the publish
        # self._profile_store.set_contacts(my_contacts)
        # current_profile.load_contacts(profile_store=self._profile_store,
        #                               reload=True)

        # self._update_session_profile(current_profile)

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


        ret = """
            APP.nostr.data.server_state = {
                'relay_status' : %s
            };
        """ % (json.dumps(DateTimeEncoder().encode(self._client.status)))

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

    def _get_events(self, filter, decrypt_p: Profile=None):
        events = self._event_store.get_filter(filter)
        c_evt: Event
        ret = []

        for c_evt in events:
            to_add = c_evt.event_data()
            if c_evt.kind == Event.KIND_ENCRYPT:
                to_add['content'] = self._decrypt_event_content_as_user(c_evt, decrypt_p)

            ret.append(to_add)

        return ret

    def _events_route(self):
        """
        returns events that match given nostr filter [{},...]
        :return:
        """
        pub_k = request.query.pub_k
        decrypt_p: Profile = None
        if pub_k:
            self._check_key(pub_k)
            decrypt_p = self._profile_handler.profiles.lookup_pub_key(pub_k)

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
            'events': self._get_events(filter,
                                       decrypt_p=decrypt_p)
        }

    def _messages(self):
        pub_k = request.query.pub_k
        decrypt_p: Profile = None
        self._check_key(pub_k)
        decrypt_p = self._profile_handler.profiles.lookup_pub_key(pub_k)
        if decrypt_p is None:
            raise NostrWebException('unable to find profile for decryption pub_k: %s', pub_k)

        # get the top message for everyone we
        filter = {
            'ids': []
        }
        dms = self._event_store.direct_messages(pub_k)
        for c_dm in dms:
            filter['ids'].append(c_dm['event_id'])

        return {
            'events': self._get_events(filter,
                                       decrypt_p=decrypt_p)
        }

    def _events_text_search_route(self):
        search_str = request.query.search_str
        limit = self._get_query_limit()

        def extract_tag(tag_prefix, text):
            pat = '\\%s(\w*)' % tag_prefix
            matches = re.findall(pat, text)
            for c_match in matches:
                text = text.replace(tag_prefix + c_match, '')

            return matches, text

        def find_authors(prefixes):
            c_p: Profile
            m_find = 100
            ret = []

            for c_pre in prefixes:
                auth_match = self._profile_handler.profiles.matches(c_pre, m_find)
                if auth_match:
                    ret = ret + [c_p.public_key for c_p in auth_match]
                    if len(ret) > m_find:
                        break

            return ret[:m_find-1]

        filter = {
            'limit': self._get_query_limit(),
            'kinds': [Event.KIND_TEXT_NOTE]
        }

        if search_str.replace(' ', ''):
            # add hash tags to filter
            hashtags, search_str = extract_tag('#', search_str)
            if hashtags:
                filter['#hashtag'] = hashtags

            # add authors to filter
            author_pres, search_str = extract_tag('@', search_str)
            if author_pres:
                authors = find_authors(author_pres)
                if authors:
                    filter['authors'] = authors
                else:
                    # so nothing will match
                    filter['authors'] = [' ']

            search_str = ' '.join(search_str.split())

            ids_pres, search_str = extract_tag('&', search_str)
            if ids_pres:
                filter['ids'] = ids_pres

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


        evts = [c_evt.event_data() for c_evt in self._event_store.get_filter(filter)]

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
        if event_id == '':
            raise NostrWebException('event_id required')

        # looks like event id?
        if not Event.is_event_id(event_id):
            raise NostrWebException('%s doesn\'t look like a valid nostr event' % event_id)


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

        for_profile = self._profile_handler.profiles.get_profile(pub_k,
                                                                 create_type=ProfileList.CREATE_PUBLIC)
        for_profile.load_contacts(self._profile_store)
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

        return {
            'events': self._get_events(filter),
            'filter': filter
        }

    def _relay_status(self):
        return DateTimeEncoder().encode(self._client.status)

    def _relay_list(self):
        pub_k = request.query.pub_k
        if pub_k:
            self._check_key(pub_k)
        else:
            pub_k = None

        return {
            'relays': self._event_store.relay_list(pub_k)
        }

    def do_event(self, sub_id, evt: Event, relay):
        if self._dedup.accept_event(evt):
            print(evt, relay, evt.kind)
            # will update our profiles if meta/contact type data
            self._profile_handler.do_event(sub_id, evt, relay)

            if evt.kind == Event.KIND_ENCRYPT:
                decrypted = 'unable to decrypt...'
                try:
                    """
                        would prefer to use _decrypt_event_content_as_user here but we have a problem that we don't have
                        a request so we can't get the current user...
                        This means we'll decrypted anything we can with the profiles we have which may not be the profile the user 
                        is currently using... Obvs this isn't great, possibly we can get the session user from the ws when we send data?
                        It doesn't really matter at teh moment as front end will only show events for current view but most 
                        importantly we're only really worried about a single user and all this profiles are theres so they could 
                        just switch profile and see the text we decrypt anyhow

                    """
                    p_tags = evt.p_tags
                    if p_tags:
                        send: Profile = self._profile_handler.profiles.lookup_pub_key(evt.pub_key)
                        to_p = p_tags[0]
                        if to_p == send.public_key:
                            to_p = p_tags[1]

                        rec: Profile = self._profile_handler.profiles.lookup_pub_key(to_p)

                    if send and rec:
                        if send.private_key:
                            decrypted = evt.decrypted_content(priv_key=send.private_key,
                                                              pub_key=rec.public_key)
                        elif rec.private_key:
                            decrypted = evt.decrypted_content(priv_key=rec.private_key,
                                                              pub_key=send.public_key)

                except:
                    pass
                evt.content = decrypted

            # push the event to our web sockets, only those events that have a time
            # otherwise client will get flooded with events if server is being started and there
            # are a lot of events to catch up on or db has just been created and maybe all old events
            # are being imported
            if evt.created_at_ticks > self._started_at:
                print('doing event send?')
                self.send_data(evt.event_data())

    def send_data(self, the_data):
        for c_sock in self._web_sockets:
            try:
                ws = self._web_sockets[c_sock]
                ws.send(DateTimeEncoder().encode(the_data))
            except Exception as e:
                logging.debug('NostrWeb::send_data - %s' % e)

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
        # clean up
        try:
            del self._web_sockets[str(wsock)]
        except Exception as e:
            print('something bad happened?!?!?!??!?!?!?!')
