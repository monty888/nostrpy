from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.client.client import Client

import time
from json import JSONDecodeError
from gevent import Greenlet
from functools import lru_cache
import logging
from nostr.ident.persist import ProfileStoreInterface
from nostr.ident.profile import Profile, ProfileList, Contact, ContactList, Keys
from .persist import ProfileType
from nostr.util import util_funcs
from nostr.event.event import Event


class ProfileEventHandler:
    """
        access profile, contacts through here rather than via the store, at the moment we keep everything in memory
        but in future where this might not be possible it should be transparent to caller that we had to fetch from store...

        NOTE locking is only for underlying storage we may(probably) need to have some access locks fothe code too
        try LOCK_BATCH sqlite, memstore will probably implement are own locking inside it so would be lock NEVER

        NOTE we're using the local cached copy to check if the event is newer... If a db update was done somewhere else
        and we get sent an older event that is newer then anything we have then that profile/contact will be overwritten
        atleast until we see a newer event ourself...
    """

    @staticmethod
    def import_profile_info(profile_handler: ProfileEventHandler, for_keys):
        for chunk_keys in util_funcs.chunk(for_keys, 250):
            ps = profile_handler.get_profiles(chunk_keys, create_missing=False)
            profile_handler.load_contacts(ps)
            profile_handler.load_followers(ps)

    def __init__(self,
                 profile_store: ProfileStoreInterface,
                 on_profile_update=None,
                 on_contact_update=None,
                 max_insert_batch=500):

        self._store = profile_store
        self._profiles = self._store.select_profiles()
        self._on_profile_update = on_profile_update
        self._on_contact_update = on_contact_update
        self._max_insert_batch = max_insert_batch

    # update locally rather than via meta 0 event
    # only used to link prov_k or add/change profile name
    def do_update_local(self, p: Profile):
        o_p: Profile = self._profiles.lookup_pub_key(p.public_key)
        self._store.put_profile(p, True)
        self._profiles.put(p)

        if self._on_profile_update:
            try:
                self._on_profile_update(p, o_p)
            except Exception as e:
                logging.debug('ProfileEventHandler::do_update_local(_on_profile_update) - %s' % e)

    def local_profiles(self) -> [Profile]:
        """
        :return: profiles that we have priv_k for
        """
        return self._store.select_profiles(profile_type=ProfileType.LOCAL)

    def do_event(self, sub_id, evt: Event, relay):
        if not hasattr(evt, '__iter__'):
            evt = [evt]

        # split events
        c_evt: Event
        profile_update_events = [c_evt for c_evt in evt if c_evt.kind == Event.KIND_META]

        def get_profile_store_func(the_chunk):
            def the_func():
                self._do_profiles_update(the_chunk)
            return the_func

        if profile_update_events:
            for c_chunk in util_funcs.chunk(profile_update_events, self._max_insert_batch):
                util_funcs.retry_db_func(get_profile_store_func(c_chunk))
                time.sleep(0.1)

        contact_update_events = [c_evt for c_evt in evt if c_evt.kind == Event.KIND_CONTACT_LIST]

        def get_contacts_store_func(the_chunk):
            def the_func():
                self._do_contacts_update(the_chunk)
            return the_func

        if contact_update_events:
            for c_chunk in util_funcs.chunk(contact_update_events, self._max_insert_batch):
                util_funcs.retry_db_func(get_contacts_store_func(c_chunk))
                time.sleep(0.1)

    def _get_to_update_profiles(self, evts:[Event]) -> ([Profile], [Profile]):
        p_e = []
        p = []
        for c_evt in evts:
            c_p = self._profiles.lookup_pub_key(c_evt.pub_key)
            if c_p is None or c_p.update_at < c_evt.created_at_ticks:
                try:
                    p_e.append(c_p)
                    p.append(Profile.from_event(c_evt))
                except JSONDecodeError as je:
                    logging.debug('ProfileEventHandler::_do_profiles_update error converting event to profile: %s \nerr: %s' % (c_evt,
                                                                                                                                je))
        return p_e, p

    def _do_profiles_update(self, evts: [Event]):
        c_evt: Event
        c_p: Profile

        p_e, p = self._get_to_update_profiles(evts)

        self._store.put_profile(p)

        # update local cache
        for c_p in p:
            self._profiles.put(c_p)

        # fire update if any, probably change to send as batch too
        if self._on_profile_update:
            for i, c_p in enumerate(p):
                try:
                    self._on_profile_update(c_p, p_e[i])
                except Exception as e:
                    logging.debug('ProfileEventHandler:_do_profiles_update>_on_profile_update error: %s, profile: %s ' % (e,
                                                                                                                          c_p.public_key))

    def _get_to_update_contacts(self, evts: [Event]) -> ([ContactList], [ContactList]):
        c = []
        c_e = []
        exist: ContactList
        for c_evt in evts:
            exist = ContactList(contacts=self._store.select_contacts({'owner': c_evt.pub_key}),
                                owner_pub_k=c_evt.pub_key)

            if exist.updated_at is None or exist.updated_at < c_evt.created_at_ticks:
                c_e.append(exist)
                c.append(ContactList.from_event(c_evt))

        return c_e, c

    def _do_contacts_update(self, evts: [Event]):
        c_evt: Event
        c_c: ContactList
        c_fl: ContactList
        c_f: Contact
        p: Profile

        c_e, c = self._get_to_update_contacts(evts)

        self._store.put_contacts(c)

        # clear contacts of anyone who has been updated
        for i, c_c in enumerate(c):
            # FIXME: only null those that don't appear in both current contacts and before update
            p = self._profiles.lookup_pub_key(c_c.owner_public_key)
            if p:
                # p.contacts = None don't see why we'd do this?
                p.followed_by = None

        # fire update if any, as profile probably change to send as batch
        if self._on_contact_update:
            for i, c_c in enumerate(c):
                self._on_contact_update(p, c_c, c_e[i])

    @property
    def profiles(self) -> ProfileList:
        # where possible don't access the underlying list directly use our methods which give us a chance to
        # intercept calls
        return self._profiles

    def get_pub_k(self, pub_k: str):
        return self._profiles.lookup_pub_key(pub_k)

    def get_profiles(self, pub_ks: [str], create_missing=True) -> ProfileList:
        if isinstance(pub_ks, str):
            pub_ks = [pub_ks]

        profiles = []
        for k in pub_ks:
            p = self._profiles.lookup_pub_key(k)
            if p:
                profiles.append(p)
            elif create_missing:
                profiles.append(Profile(pub_k=k))

        return ProfileList(profiles)

    def matches(self, m_str, max_match=None, search_about=False):
        # sort the profiles first
        sorted_ps = self._profiles.sort_profiles(self._profiles,
                                                 inplace=False)
        return sorted_ps.matches(m_str=m_str,
                                 max_match=max_match,
                                 search_about=search_about)

    def load_contacts(self, p: Profile, reload=False):
        if not p.contacts_is_set() or reload:
            p.contacts = ContactList(self._store.select_contacts({
                'owner': self.public_key
            }), owner_pub_k=self.public_key)

    def load_followers(self, p: Profile, reload=False):
        p.load_followers(profile_store=self._store,
                         reload=reload)

    @property
    def store(self) -> ProfileStoreInterface:
        return self._store

    def set_on_profile_update(self, on_update):
        self._on_profile_update = on_update

    def set_on_contact_update(self, on_update):
        self._on_contact_update = on_update

    def profile(self, pub_k):
        ret = self._profiles.lookup_pub_key(pub_k)
        return ret

    def is_newer_profile(self, p: Profile):
        # return True if given profile is newer than we have
        ret = False
        c_p = self.profile(p.public_key)
        if c_p is None or c_p.update_at < p.update_at:
            ret = True
        return ret

    def is_newer_contacts(self, contacts: ContactList):
        # return True if given profile is newer than what we have
        ret = False

        c_p = self.profile(contacts.owner_public_key)
        if c_p is None:
            existing = ContactList(contacts=self._store.select_contacts({'owner': contacts.owner_public_key}),
                                   owner_pub_k=contacts)

        else:
            c_p.load_contacts(self._store)
            existing = c_p.contacts

        if existing is None or existing.updated_at is None or existing.updated_at < contacts.updated_at:
            if existing.updated_at is None and len(contacts) == 0:
                # check this... assumed that we have the contact but cant find any contacts for then
                # which is the same as adding 0 len contacts ie nothing to do
                pass
            else:
                ret = True

        return ret


class NetworkedProfileEventHandler(ProfileEventHandler):

    def __init__(self,
                 profile_store: ProfileStoreInterface,
                 client: Client,
                 on_profile_update=None,
                 on_contact_update=None,
                 max_insert_batch=500):

        self._client = client
        self._timeout = 5
        super().__init__(profile_store=profile_store,
                         on_profile_update=on_profile_update,
                         on_contact_update=on_contact_update,
                         max_insert_batch=max_insert_batch)

    def fetch_profile_events(self, keys):

        if isinstance(keys, str):
            keys = keys.split(',')

        ret = []

        if keys:
            # some relays limit the n of keys, but seems to work if we just use mutiple qs
            q = []
            for k_chunk in util_funcs.chunk(keys, 250):
                q.append({
                    'kinds': [Event.KIND_META],
                    'authors': k_chunk
                })
            evts = self._client.query(q, timeout=self._timeout)
            if evts:
                ret = [Profile.from_event(c_evt) for c_evt in evts]
                Greenlet(util_funcs.get_background_task(self._do_profiles_update, evts)).start_later(0)

        return ret

    def fetch_contact_events(self, keys):

        if isinstance(keys, str):
            keys = keys.split(',')

        ret = []
        if keys:
            # some relays limit the n of keys, but seems to work if we just use mutiple qs
            q = []
            for k_chunk in util_funcs.chunk(keys, 250):
                q.append({
                    'kinds': [Event.KIND_CONTACT_LIST],
                    'authors': k_chunk
                })

            evts = self._client.query(q, timeout=self._timeout)

            if evts:
                ret = [ContactList.from_event(c_evt) for c_evt in evts]
                Greenlet(util_funcs.get_background_task(self._do_contacts_update, evts)).start_later(0)

        return ret

    def fetch_follows(self, keys):
        if isinstance(keys, str):
            keys = keys.split(',')

        # as meta and follows chunk
        ret = []
        if keys:
            q = []
            for k_chunk in util_funcs.chunk(keys, 250):
                q.append({
                    'kinds': [Event.KIND_CONTACT_LIST],
                    '#p': k_chunk
                })

            evts = self._client.query(q, timeout=self._timeout)

            if evts:
                evts = Event.latest_events_only(evts)
                # we'll be returning a list of pub_ks
                ret = [ContactList.from_event(c_evt) for c_evt in evts]
                # think it's better not to update contacts list here
                # Greenlet(util_funcs.get_background_task(self._do_contacts_update, evts)).start_later(0)

        return ret

    def get_pub_k(self, pub_k: str):
        ret = super().get_pub_k(pub_k)
        if ret is None:
            fetched_ps = self.fetch_profile_events(pub_k)
            if fetched_ps:
                ret = fetched_ps[0]

        return ret

    def get_profiles(self, pub_ks: [str], create_missing=True) -> ProfileList:
        if isinstance(pub_ks, str):
            pub_ks = [pub_ks]
        ret = super().get_profiles(pub_ks, create_missing=False)
        to_fetch = [k for k in pub_ks if ret.lookup_pub_key(k) is None
                    and Keys.is_key(k)]

        ret = ret.profiles

        if to_fetch:
            to_fetch.sort()
            ret = ret + self.fetch_profile_events(','.join(to_fetch))

        p: Profile
        if len(ret) != len(pub_ks) and create_missing:
            got = set([p.public_key for p in ret])
            for k in pub_ks:
                if k not in got:
                    empty_profile = Profile(pub_k=k)
                    ret.append(empty_profile)
                    # so we won't continually be trying to fetch
                    # on seeing a meta event it'll get updated anyhow
                    self._profiles.put(empty_profile)

        return ProfileList(ret)

    def load_contacts(self, p: Profile, reload=False) -> ContactList:
        if not hasattr(p, '__iter__'):
            p = [p]

        # get keys to load contacts for
        c_p: Profile
        if reload:
            request_keys = [c_p.public_key for c_p in p]
        else:
            request_keys = []
            for c_p in p:
                if not c_p.contacts_is_set():
                    c_p.contacts = ContactList(self._store.select_contacts({
                        'owner': c_p.public_key
                    }), owner_pub_k=c_p.public_key)
                if len(c_p.contacts) == 0:
                    request_keys.append(c_p.public_key)

        # go fecth them if any
        if request_keys:
            contacts_lists = self.fetch_contact_events(request_keys)
            c_l: ContactList
            lookup = dict([(c_l.owner_public_key, c_l) for c_l in contacts_lists])
            for_p = [c_p for c_p in p if c_p.public_key in set(request_keys)]

            for c_p in for_p:
                if c_p.public_key in lookup:
                    c_p.contacts = lookup[c_p.public_key]
                else:
                    c_p.contacts = ContactList(contacts=[],
                                               owner_pub_k=c_p.public_key)

    def load_followers(self, p: Profile, reload=False):
        """ because follows is made up by looking at all contact events where p is mentioned
        we have no choice but to go to the network if we want a relativly complete count
        we only unset if we see a meta where p is metioned... in future we could keep track
        from that point on without requesting from the net
        :param p:
        :param reload:
        :return:
        """
        if not hasattr(p, '__iter__'):
            p = [p]

        request_keys = [c_p.public_key for c_p in p
                        if reload or not c_p.follows_by_is_set()]

        if request_keys:
            contact_lists = self.fetch_follows(request_keys)
            c_l: ContactList
            c_c: Contact
            for_p = [c_p for c_p in p if c_p.public_key in set(request_keys)]
            lookup = dict([(c_p.public_key, set([])) for c_p in for_p])
            for c_l in contact_lists:
                for c_c in c_l:
                    if c_c.contact_public_key in lookup:
                        lookup[c_c.contact_public_key].add(c_l.owner_public_key)

            for c_p in for_p:
                if c_p.public_key in lookup:
                    c_p.followed_by = list(lookup[c_p.public_key])
                else:
                    c_p.followed_by = []
