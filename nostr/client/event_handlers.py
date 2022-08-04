"""
    EventHandlers for Client subscribe method, there should be a do_event(evt, relay) which should be passed as the
    handler arg when calling the subscribe method. Eventually support mutiple handlers per sub and add.remove handlers
    plus maybe chain of handlers

"""
from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import gevent

if TYPE_CHECKING:
    from nostr.ident.persist import ProfileStoreInterface

from json import JSONDecodeError
from nostr.ident.profile import ProfileList, Profile, Contact, ContactList
from abc import ABC, abstractmethod
import base64
import logging
import json
from collections import OrderedDict
# from gevent.lock import BoundedSemaphore
from threading import BoundedSemaphore

# from nostr.client.persist import ClientEventStoreInterface
from nostr.event.persist import ClientEventStoreInterface
from nostr.encrypt import SharedEncrypt
from nostr.util import util_funcs
from nostr.event.event import Event
from app.post import PostApp


class EventAccepter(ABC):

    @abstractmethod
    def accept_event(self, evt: Event) -> bool:
        'True/False if the event will be accepted'


class DeduplicateAcceptor(EventAccepter):

    def __init__(self, max_dedup=10000):
        # de-duplicating of events for when we're connected to multiple relays
        self._duplicates = OrderedDict()
        self._max_dedup = max_dedup
        self._lock = BoundedSemaphore()

    def accept_event(self, evt: Event) -> bool:
        ret = False
        with self._lock:
            if evt.id not in self._duplicates:
                self._duplicates[evt.id] = True
                if len(self._duplicates) >= self._max_dedup:
                    self._duplicates.popitem(last=False)
                ret = True
        return ret


class LengthAcceptor(EventAccepter):

    def __init__(self, min=1, max=None):
        self._min = min
        self._max = max

    def accept_event(self, evt: Event) -> bool:
        ret = True
        msg_len = len(evt.content)
        if self._min and msg_len<self._min:
            ret = False
        if self._max and msg_len>self._max:
            ret = False
        return ret


class EventHandler(ABC):

    def __init__(self, event_acceptors: [EventAccepter]=[]):
        if not hasattr(event_acceptors, '__iter__'):
            event_acceptors = [event_acceptors]
        self._event_acceptors = event_acceptors

    def accept_event(self, evt: Event):
        ret = True
        for accept in self._event_acceptors:
            if not accept.accept_event(evt):
                ret = False
                break

        return ret

    @abstractmethod
    def do_event(self, sub_id, evt: Event, relay):
        """
        if self.accept_event(evt):
            do_something
        or just do_something if no accept criteria
        """


class PrintEventHandler(EventHandler):
    """
       basic handler for outputting events
    """
    def __init__(self,
                 event_acceptors=[],
                 view_on=True,
                 profile_handler: ProfileEventHandler = None):

        self._view_on = view_on
        self._profile_handler = profile_handler
        super().__init__(event_acceptors)

    def view_on(self):
        self._view_on = True

    def view_off(self):
        self._view_on = False

    def do_event(self, sub_id, evt: Event, relay):
        if self._view_on and self.accept_event(evt):
            self.display_func(sub_id, evt, relay)

    def display_func(self, sub_id, evt: Event, relay):
        # single line basic evt info, override this if you want something more
        profile_name = evt.pub_key
        if self._profile_handler is not None:
            profile_name = self._profile_handler.profiles.get_profile(profile_name,
                                                                      create_type=ProfileList.CREATE_PUBLIC).display_name()

        print('%s: %s - %s' % (evt.created_at,
                               util_funcs.str_tails(profile_name, 4),
                               evt.content))


class DecryptPrintEventHandler(PrintEventHandler):
    """
        prints out decrypted messages we created or sent to us
        NOTE: this is not the style that is compatiable with clust, that uses a public inbox
        and encrypts the event as a package... want to add this too
    """

    def __init__(self, priv_k, view_on=True):
        self._priv_k = priv_k
        self._my_encrypt = SharedEncrypt(priv_k)
        super(DecryptPrintEventHandler, self).__init__(view_on)

    def _do_dycrypt(self, crypt_text, pub_key):
        msg_split = crypt_text.split('?iv')
        text = base64.b64decode(msg_split[0])
        iv = base64.b64decode(msg_split[1])

        return (self._my_encrypt.decrypt_message(encrypted_data=text,
                                                 iv=iv,
                                                 # note the ext is ignored anyway
                                                 pub_key_hex='02' + pub_key))

    def do_event(self, sub_id, evt, relay):
        if self._view_on is False:
            return
        do_decrypt = False
        to_key = evt['tags'][0][1]
        print(to_key, self._my_encrypt.public_key_hex)
        if evt['kind'] == Event.KIND_ENCRYPT:
            # messages we created
            if evt['pubkey'] == self._my_encrypt.public_key_hex[2:]:
                pub_key = to_key
                do_decrypt = True

            # messages sent to us
            elif to_key == self._my_encrypt.public_key_hex[2:]:
                pub_key = evt['pubkey']
                do_decrypt = True

        content = evt['content']
        if do_decrypt:
            content = self._do_dycrypt(evt['content'], pub_key)

        print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                               evt['pubkey'],
                               content))


class FileEventHandler:

    def __init__(self, file_name, delete_exist=True):
        self._file_name = file_name
        if delete_exist:
            with open(self._file_name, 'w'):
                pass

    def do_event(self, sub_id, evt, relay):
        # appends to
        with open(self._file_name, "a") as f:
            evt['pubkey'] = evt['pubkey']
            f.writelines(json.dumps(evt) + '\n')
        logging.debug('FileEventHandler::do_event event appended to file %s' % self._file_name)


class EventTimeHandler:

    def __init__(self, callback=None):
        self._callback = callback

    def do_event(self, sub_id, evt, relay):
        self._callback(evt['created_at'])


class PersistEventHandler:
    """
        persists event we have seen to storage, profiles created/updated for meta_data type
        TODO: either add back in persist profile here or move to own handler
    """

    def __init__(self,
                 store: ClientEventStoreInterface,
                 max_insert_batch=5000):
        self._store = store
        self._lock = BoundedSemaphore()
        self._max_insert_batch = max_insert_batch
        # to check if new or update profile
        # self._profiles = DataSet.from_sqlite(db_file,'select pub_k from profiles')

    def do_event(self, sub_id, evt: Event, relay):
        # store the actual event
        if not hasattr(evt, '__iter__'):
            evt = [evt]

        if self._max_insert_batch:
            evt = [evt[i:i + self._max_insert_batch] for i in range(0, len(evt), self._max_insert_batch)]
        else:
            evt = [evt]

        try:
            with self._lock:
                for c_evt_chunk in evt:
                    try:
                        self._store.add_event_relay(c_evt_chunk, relay)
                        if len(evt)>1:
                            time.sleep(0.1)
                    except Exception as e:
                        # nasty but the lock we have only applies to events coming thorught... profiles also might be done via
                        # batch and could lock the db, (profile backfill done at EOSE too) if we chunk the profiles hopefully
                        # this wouldn't be needed
                        if 'locked' in str(e):
                            print('wait and try once....')
                            time.sleep(3)
                            self._store.add_event_relay(c_evt_chunk, relay)


                # self._store.add_event_relay(evt, relay)
        except Exception as e:
            id = 'batched events'
            if not hasattr(evt,'__iter__'):
                id = evt.id

            logging.debug('PersistEventHandler::do_event error persisting event %s - %s' % (id, e))


class RepostEventHandler:
    """
    reposts events seen  on to given Client/ClientPool object
    event size number of event ids to keep to prevent duplicates being sent out
    NOTE though this is really just to prevent wasteful repost of events, relays
    shouldn't have a problem receiving duplicate ids

    to_client, TODO: define interface that both Client and ClientPool share and type hint with that

    """
    def __init__(self, to_client, max_dedup=1000):
        self._to_client = to_client
        self._duplicates = OrderedDict()
        self._max_dedup = max_dedup
        self._lock = BoundedSemaphore()

    def do_event(self, sub_id, evt:Event, relay):
        do_send = False
        with self._lock:
            if evt.id not in self._duplicates:
                do_send = True
                self._duplicates[evt.id] = True
                if len(self._duplicates) >= self._max_dedup:
                    self._duplicates.popitem(False)

        if do_send:
            self._to_client.publish(evt)
            print('RepostEventHandler::sent event %s to %s' % (evt, self._to_client))


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

    LOCK_NEVER = 0
    LOCK_BATCH = 1
    LOCK_ALWAYS = 2

    def __init__(self,
                 profile_store: 'ProfileStoreInterface',
                 on_profile_update=None,
                 on_contact_update=None):

        self._store = profile_store
        self._profiles = self._store.select_profiles()
        self._on_profile_update = on_profile_update
        self._on_contact_update = on_contact_update
        self._lock = BoundedSemaphore()
        lock_mode = ProfileEventHandler.LOCK_BATCH

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
        contact_update_events = [c_evt for c_evt in evt if c_evt.kind == Event.KIND_CONTACT_LIST]
        if profile_update_events:
            try:
                self._do_profiles_update(profile_update_events)
            except Exception as e:
                print('profile update %s '%e )
        if contact_update_events:
            try:
                self._do_contacts_update(contact_update_events)
            except Exception as e:
                print('contacts update %s '%e )

    def _get_to_update_profiles(self, evts:[Event]) -> ([Profile], [Profile]):
        p_e = []
        p = []
        for c_evt in evts:
            c_p = self._profiles.lookup_pub_key(c_evt.pub_key)
            if c_p is None or c_p.update_at < c_evt.created_at:
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

        with self._lock:
            self._store.put_profile(p)

        # update local cache
        for c_p in p:
            self.profiles.put(c_p)

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

        with self._lock:
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
