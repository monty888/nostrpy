from datetime import datetime
import json
import secp256k1
import hashlib
import base64
import logging
from nostr.persist import Store
from nostr.util import util_funcs
from nostr.encrypt import SharedEncrypt

class Event:
    """
        base class for nost events currently used just as placeholder for the kind type consts
        likely though that we'll subclass and have some code where you actually create and use these
        events. Also make so easy to sign and string and create from string

    """
    KIND_META = 0
    KIND_TEXT_NOTE = 1
    KIND_RELAY_REC = 2
    KIND_CONTACT_LIST = 3
    KIND_ENCRYPT = 4

    @classmethod
    def create_from_JSON(cls, evt_json):
        """
        TODO: add option to verify sig/eror if invalid?
        creates an event object from json - at the moment this must be a full event, has id and has been signed,
        may add option for presigned event in future
        :param evt_json: json to create the event, as you'd recieve from subscription
        :return:
        """
        return Event(
            id=evt_json['id'],
            sig=evt_json['sig'],
            kind=evt_json['kind'],
            content=evt_json['content'],
            tags=evt_json['tags'],
            pub_key=evt_json['pubkey'],
            created_at=util_funcs.ticks_as_date(evt_json['created_at'])
        )

    def __init__(self, id=None, sig=None, kind=None, content=None, tags=None, pub_key=None, created_at=None):
        self._id = id
        self._sig = sig
        self._kind = kind
        self._created_at = created_at
        # normally the case when creating a new event
        if created_at is None:
            self._created_at = datetime.now()
        self._content = content
        self._tags = tags
        self._pub_key = pub_key
        if tags is None:
            self._tags = []

    def serialize(self):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
        """
        if self._pub_key is None:
            raise Exception('Event::serialize can\'t be done unless pub key is set')

        ret = json.dumps([
            0,
            self._pub_key[2:],
            util_funcs.date_as_ticks(self._created_at),
            self._kind,
            self._tags,
            self._content
        ], separators=(',', ':'))

        return ret

    def _get_id(self):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
            pub key must be set to generate the id
        """
        evt_str = self.serialize()
        self._id = hashlib.sha256(evt_str.encode('utf-8')).hexdigest()

    def sign(self, priv_key):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
            pub key must be set to generate the id

            if you were doing we an existing event for some reason you'd need to change the pub_key
            as else the sig we give won't be as expected

        """
        self._get_id()

        # pk = secp256k1.PrivateKey(priv_key)
        pk = secp256k1.PrivateKey()
        pk.deserialize(priv_key)

        # sig = pk.ecdsa_sign(self._id.encode('utf-8'))
        # sig_hex = pk.ecdsa_serialize(sig).hex()
        id_bytes = (bytes(bytearray.fromhex(self._id)))
        sig = pk.schnorr_sign(id_bytes, bip340tag='', raw=True)
        sig_hex = sig.hex()

        self._sig = sig_hex

    def event_data(self):
        return {
            'id': self._id,
            'pubkey': self._pub_key[2:],
            'created_at': util_funcs.date_as_ticks(self._created_at),
            'kind': self._kind,
            'tags': self._tags,
            'content': self._content,
            'sig': self._sig
        }

    """
        get/set various event properties
        Note changing is going to make event_data that has been signed incorrect, probably the caller should be aware
        of this but might do something to make this clear 

    """

    @property
    def pub_key(self):
        return self._pub_key

    @pub_key.setter
    def pub_key(self, pub_key):
        self._pub_key = pub_key


"""
    EventHandlers for Client subscribe method, there should be a do_event(evt, relay) which should be passed as the 
    handler arg when calling the subscribe method. Eventually support mutiple handlers per sub and add.remove handlers
    plus maybe chain of handlers  

    TODO: move event/handlers to own file
"""


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

    def do_event(self, evt, relay):
        if self._view_on:
            print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                                   evt['pubkey'],
                                   evt['content']))


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

    def do_event(self, evt, relay):
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

    def do_event(self, evt, relay):
        # appends to
        with open(self._file_name, "a") as f:
            evt['pubkey'] = evt['pubkey']
            f.writelines(json.dumps(evt) + '\n')
        logging.debug('FileEventHandler::do_event event appended to file %s' % self._file_name)


class EventTimeHandler:

    def __init__(self, callback=None):
        self._callback = callback

    def do_event(self, evt, relay):
        self._callback(evt['created_at'])


class PersistEventHandler:
    """
        persists event we have seen to storage, profiles created/updated for meta_data type
        TODO: either add back in persist profile here or move to own handler
    """

    def __init__(self, db_file):
        self._store = Store(db_file)
        # to check if new or update profile
        # self._profiles = DataSet.from_sqlite(db_file,'select pub_k from profiles')

    def do_event(self, evt, relay):

        # store the actual event
        try:
            self._store.add_event(evt, relay)
        except:
            # most likely because we already have, we could though add a table that
            # linking evets with every relay we saw them from
            pass

        # pubkey = evt['pubkey']
        #
        # # if meta then add/update profile as required
        # if evt['kind'] == Event.KIND_META:
        #     c_profile = self._profiles.value_in('pub_k',pubkey)
        #     if c_profile:
        #         my_store.update_profile(c_profile)
        #     else:
        #         c_profile = Profile(pub_k=pubkey,attrs=evt['content'],update_at=evt['created_at'])
        #         my_store.add_profile(c_profile)
        #
        #     # for now we just reload the whole lot from db rather then just updating what we have
        #     profiles = ProfileList.create_others_profiles_from_db(db_file)
