from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass

import time
from json import JSONDecodeError
import logging
from nostr.ident.persist import ProfileStoreInterface
from nostr.ident.profile import Profile, ProfileList, Contact, ContactList
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
        self._store.put_profile(p, True)
        self._profiles.put(p)

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

    def _clear_followers(self):
        print('to be implemente, clear follows')

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
                p.contacts = None
                p.followed_by = None

        # fire update if any, as profile probably change to send as batch
        if self._on_contact_update:
            for i, c_p in enumerate(p):
                self._on_profile_update(c_p, c_c[i])

    @property
    def profiles(self) -> ProfileList:
        return self._profiles

    @property
    def store(self) -> ProfileStoreInterface:
        return self._store

    def set_on_update(self, on_update):
        self._on_update = on_update

    def profile(self, pub_k):
        ret = self._profiles.lookup_pub_key(pub_k)
        return ret

    def is_newer_profile(self, p: Profile):
        # return True if given profile is newer than what we have
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