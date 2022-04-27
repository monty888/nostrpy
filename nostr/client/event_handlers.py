"""
    EventHandlers for Client subscribe method, there should be a do_event(evt, relay) which should be passed as the
    handler arg when calling the subscribe method. Eventually support mutiple handlers per sub and add.remove handlers
    plus maybe chain of handlers

"""
import base64
import logging
import json
from collections import OrderedDict
from nostr.client.persist import ClientEventStoreInterface
from nostr.encrypt import SharedEncrypt
from nostr.util import util_funcs
from nostr.event import Event


class PrintEventHandler:
    """
        Basic handler that just prints to screen any events it sees.
        Can be turned off by calling view_off

        TODO: add kinds filter, default NOTE and ENCRYPT only
    """

    def __init__(self, view_on=True):
        self._view_on = view_on

    def view_on(self):
        self._view_on = True

    def view_off(self):
        self._view_on = False

    def do_event(self, sub_id, evt: Event, relay):
        if self._view_on:
            self.display_func(sub_id, evt, relay)

    def display_func(self, sub_id, evt: Event, relay):
        print('%s: %s - %s' % (evt.created_at,
                               util_funcs.str_tails(evt.pub_key, 4),
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

    def __init__(self, store: ClientEventStoreInterface):
        self._store = store
        # to check if new or update profile
        # self._profiles = DataSet.from_sqlite(db_file,'select pub_k from profiles')

    def do_event(self, sub_id, evt:Event, relay):
        # store the actual event
        try:
            self._store.add_event(evt, relay)
        except Exception as e:
            print(e)
            # most likely because we already have, we could though add a table that
            # linking evets with every relay we saw them from


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

    def do_event(self, sub_id, evt:Event, relay):
        if evt.id not in self._duplicates:
            self._duplicates[evt.id] = True
            if len(self._duplicates) >= self._max_dedup:
                self._duplicates.popitem(False)

            # evt = Event.create_from_JSON(evt)
            self._to_client.publish(evt)
            print('RepostEventHandler::sent event %s to %s' % (evt, self._to_client))

