from datetime import datetime
import json
import secp256k1
import hashlib
from nostr.util import util_funcs


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

    def is_valid(self):
        pub_key = secp256k1.PublicKey(bytes.fromhex('02'+self._pub_key),
                                      raw=True)

        ret = pub_key.schnorr_verify(
            msg=bytes.fromhex(self._id),
            schnorr_sig=bytes.fromhex(self._sig),
            bip340tag='', raw=True)

        return ret

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

    @property
    def id(self):
        return self._id

    def __str__(self):
        ret = super(Event, self).__str__()
        # on signed events we can retrn something more useful
        if self.id:
            return '%s@%s' % (self.id,self._created_at)