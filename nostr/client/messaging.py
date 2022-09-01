from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from nostr.event.persist import ClientEventStoreInterface
"""
    abstract some of the functionality we need in order to messages between people other nostr protocal

    todo
            1-1 unencrypted
            1-1 encrypted
            1-1 encrypted wraped

            future
            groups for the above
  656e4f70242342cd143295f2c53c47646bb6bc19f26ca27cc989945bc2928d14
"""

import base64
import logging
from gevent.lock import BoundedSemaphore
from nostr.ident.profile import Profile
from nostr.client.client import Client
from nostr.event.event import Event
from nostr.encrypt import SharedEncrypt


class MessageThreads:
    """
        keep a track of all 1-1 message for from_p
        if evt_store is given then

    """
    def __init__(self,
                 from_p: Profile,
                 evt_store: ClientEventStoreInterface,
                 on_message=None,
                 to_pub_k=None,
                 kinds=[Event.KIND_TEXT_NOTE]):
        """

        :param from_p:
        :param evt_store:
        :param on_message:
        :param to_pub_k:
        :param kinds:
        """
        self._from = from_p

        if not to_pub_k:
            to_pub_k = []
        if isinstance(to_pub_k, str):
            to_pub_k = [to_pub_k]

        self._to_puk_key = to_pub_k

        self._kinds = kinds

        # record of messages we've seen by eventid
        self._msg_lookup = set()
        # lock for above so we can prevent duplicates, for example
        # we'll see the same event multiple times if we're attached to multiple relays
        self._msg_lookup_lock = BoundedSemaphore()

        self._evt_store = evt_store

        # messages keyed on pub_key of who they are to
        self._msg_threads = {}

        self.load_local()
        self._on_message = on_message

    def load_local(self):
        """
        load the already seen msgs from what we've already seen locally
        """

        # we have no local store of events, completely reliant on fetch from relay
        if not self._evt_store:
            return

        # get all messages we created all were mentioned in
        all_evts = self._evt_store.get_filter(
            [
                {
                    'kinds': self._kinds,
                    'authors': [self._from.public_key]
                },
                {
                    'kinds': self._kinds,
                    '#p': [self._from.public_key]
                }
            ]
        )
        c_evt: Event
        for c_evt in all_evts:
            self._add_msg(c_evt)

    def _add_msg(self, msg_evt):
        p_tags = msg_evt.p_tags

        # we've already seen this event either from local store or previous sub recieved
        # or it's not 1-1 msg
        with self._msg_lookup_lock:
            if msg_evt.id in self._msg_lookup or len(p_tags) < 1 or len(p_tags) > 2:
                return False
            self._msg_lookup.add(msg_evt.id)

        to_id = p_tags[0]
        if to_id == self._from.public_key:
            to_id = msg_evt.pub_key

        if to_id == self._from.public_key:
            if len(p_tags) == 1:
                return False
            to_id = p_tags[1]

        if to_id not in self._msg_threads:
            """
                seperate store for the different types of notes, dict as we might in future add unread count etc.
            """
            self._msg_threads[to_id] = {
                Event.KIND_TEXT_NOTE: {
                    'msgs': []
                },
                Event.KIND_ENCRYPT: {
                    'msgs': []
                }
            }

        if msg_evt.kind == Event.KIND_ENCRYPT:
            # we keep in memory unecrypted, probably we should decrypt at the point
            # we're outputing to screen
            msg_copy = Event.create_from_JSON(msg_evt.event_data())
            try:

                msg_copy.content = msg_evt.decrypted_content(self._from.private_key, to_id)

            except Exception as e:
                msg_copy.content = '!!!unable to decrypt!!!'
        self._msg_threads[to_id][msg_evt.kind]['msgs'].append(msg_copy)

        return True

    def do_event(self, sub_id, evt: Event, relay):
        if self._add_msg(evt) and self._on_message:
            self._on_message(evt)

    def post_message(self,
                     the_client: Client,
                     from_user: Profile,
                     to_user: Profile,
                     text,
                     kind=Event.KIND_TEXT_NOTE):
        """
        :param from_user:
        :param to_user:
        :param msg:
        :param kind:
        :return:
        """
        the_content = text

        # # encrypt text as NIP4 if encrypted kind
        if kind == Event.KIND_ENCRYPT:
            # as decrypt add this as event method
            my_enc = SharedEncrypt(self._from.private_key)
            my_enc.derive_shared_key('02' + to_user.public_key)
            # crypt_message = my_enc.encrypt_message(b'a very simple message to test encrypt')
            crypt_message = my_enc.encrypt_message(bytes(text.encode('utf8')))
            enc_message = base64.b64encode(crypt_message['text'])
            iv_env = base64.b64encode(crypt_message['iv'])
            the_content = '%s?iv=%s' % (enc_message.decode(), iv_env.decode())

        n_event = Event(kind=kind,
                        content=the_content,
                        pub_key=from_user.public_key,
                        tags=[
                            ['p', to_user.public_key]
                        ])
        n_event.sign(from_user.private_key)
        the_client.publish(n_event)

    def messages(self, pub_k, kind, since=None, received_only=False):
        ret = []
        if pub_k in self._msg_threads:
            ret = self._msg_threads[pub_k][kind]['msgs']
            if since:
                ret = [msg for msg in ret if msg.created_at > since]
            if received_only:
                ret = [msg for msg in ret if pub_k not in msg.get_tags('p')[0][0]]

        return ret

    def messaged(self):
        """
        :return: pub_keys of anyone that we have messages to
        """
        logging.debug('>>>>>>> %s' % self._msg_threads.keys())
        return self._msg_threads.keys()
