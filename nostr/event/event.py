from datetime import datetime
import base64
from enum import Enum
import json
from json import JSONDecodeError
import secp256k1
import hashlib
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
    KIND_DELETE = 5
    # NIP 25 reactions https://github.com/nostr-protocol/nips/blob/master/25.md
    KIND_REACTION = 7
    # NIP 28 events for group chat
    # https://github.com/nostr-protocol/nips/blob/af6893145f9a4a63be3d90beffbcfd4d90e872ae/28.md
    KIND_CHANNEL_CREATE = 40
    KIND_CHANNEL_META = 41
    KIND_CHANNEL_MESSAGE = 42
    KIND_CHANNEL_HIDE = 43
    KIND_CHANNEL_MUTE = 44

    @staticmethod
    def create_from_JSON(evt_json):
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

    @staticmethod
    def is_event_id(event_id: str):
        """
        basic check that given str is a nostr event id
        """
        ret = False
        if len(event_id) == 64:
            # and also hex, will throw otherwise
            try:
                bytearray.fromhex(event_id)
                ret = True
            except:
                pass
        return ret

    def __init__(self, id=None, sig=None, kind=None, content=None, tags=None, pub_key=None, created_at=None):
        self._id = id
        self._sig = sig
        self._kind = kind
        self._created_at = created_at
        # normally the case when creating a new event
        if created_at is None:
            self._created_at = datetime.now()
        self._content = content

        self._pub_key = pub_key

        self.tags = tags

    def serialize(self):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
        """
        if self._pub_key is None:
            raise Exception('Event::serialize can\'t be done unless pub key is set')

        ret = json.dumps([
            0,
            self._pub_key,
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
            'pubkey': self._pub_key,
            'created_at': util_funcs.date_as_ticks(self._created_at),
            'kind': self._kind,
            'tags': self._tags,
            'content': self._content,
            'sig': self._sig
        }

    def test(self, filter):
        # where ttype is [e]vent or [p]ubkey
        def _test_tag_match(t_type, single_filter):
            ismatch = False
            # create lookup of out type tags
            t_lookup = set()
            for c_tag in self._tags:
                if c_tag[0] == t_type:
                    t_lookup.add(c_tag[1])
            # if there are any p tags on this event
            if t_lookup:
                # just incase has been passed as str
                t_filter = single_filter['#'+t_type]
                if isinstance(t_filter, str):
                    t_filter = [t_filter]

                for c_t in t_filter:
                    if c_t in t_lookup:
                        ismatch = True
                        break

            return ismatch

        def _field_tag_match(name, single_filter):
            field_match = False
            if name not in c_filter:
                field_match = True
            else:
                to_test = single_filter[name]
                if isinstance(to_test, str):
                    to_test = [to_test]

                for c_test in to_test:
                    if name == 'authors' and self.pub_key.startswith(c_test):
                        field_match = True
                        break
                    elif name == 'ids' and self.id.startswith(c_test):
                        field_match = True
                        break

            return field_match

        if isinstance(filter, dict):
            filter = [filter]

        for c_filter in filter:
            ret = True
            if 'since' in c_filter and self.created_at_ticks <= c_filter['since']:
                ret = False
            if 'until' in c_filter and self.created_at_ticks >= c_filter['until']:
                ret = False
            if 'kinds' in c_filter:
                fkinds = c_filter['kinds']
                if hasattr(fkinds, '__iter__'):
                    if self.kind not in fkinds:
                        ret = False
                elif fkinds != self.kind:
                    ret = False
            if not _field_tag_match('authors', c_filter):
                ret = False
            if not _field_tag_match('ids', c_filter):
                ret = False

            # generic tags start with #, also included here are p and e tags as they're done in same way
            for c_name in c_filter:
                # its an event tag
                if c_name[0] == '#':
                    if not _test_tag_match(c_name[1:], c_filter):
                        ret = False

            # multiple filters are joined so a pass on any and we're out of here
            if ret:
                break

        return ret

    def get_tags(self, tag_name):
        """
        returns tag data for tag_name, no checks on the data e..g. that #e, event id is long enough to be valid event
        :param tag_name:
        :return:
        """
        return [t[1:] for t in self._tags if len(t) >= 1 and t[0] == tag_name]

    def get_tags_value(self, tag_name):
        """
        returns the first val of data for given tags in most cases this would be what we want otherwise use get_tags
        :param tag_name:
        :return:
        """
        return [t[0] for t in self.get_tags(tag_name)]

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, tags):

        # if passed in as json str e.g. as event is received over ws
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except JSONDecodeError as je:
                tags = None

        if tags is None:
            tags = []
        self._tags = tags

    @property
    def e_tags(self):
        """
        :return: all ref'd events/#e tag in [evt_id, evt_id,...] makes sure evt_id is correct len
        """
        return [t[0] for t in self.get_tags('e') if len(t[0]) == 64]

    @property
    def p_tags(self):
        """
        :return: all ref'd profile/#p tag in [pub_k, pub_k,...] makes sure pub_k is correct len
        """
        return [t[0] for t in self.get_tags('p') if len(t[0]) == 64]

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

    @property
    def short_id(self):
        # shorter version of id for display, note id doesn't until signing
        return util_funcs.str_tails(self.id, 4)

    @property
    def created_at(self):
        return self._created_at

    @property
    def created_at_ticks(self):
        return util_funcs.date_as_ticks(self._created_at)

    @property
    def kind(self):
        return self._kind

    @property
    def content(self):
        return self._content

    def decrypted_content(self, priv_key, pub_key):
        """
        dycrypts a NIP04 encoded event...
        :param priv_key:
        :return:
        """
        if self.kind != Event.KIND_ENCRYPT:
            raise Exception('attempt to decrypt non encrypted event %s' % self.id)

        my_enc = SharedEncrypt(priv_key)
        msg_split = self.content.split('?iv')

        try:
            text = base64.b64decode(msg_split[0])
            iv = base64.b64decode(msg_split[1])

            if len(pub_key) == 64:
                pub_key = '02' + pub_key

            ret = my_enc.decrypt_message(text, iv, pub_key).decode('utf8')

        except Exception as e:
            raise Exception('unable to decrypt event %s using given priv_k' % priv_key)

        return ret

    def encrypt_content(self, priv_key, pub_key):
        my_enc = SharedEncrypt(priv_key)
        if len(pub_key) == 64:
            pub_key = '02' + pub_key

        my_enc.derive_shared_key(pub_key)

        crypt_message = my_enc.encrypt_message(bytes(self.content.encode('utf8')))
        enc_message = base64.b64encode(crypt_message['text'])
        iv_env = base64.b64encode(crypt_message['iv'])

        return '%s?iv=%s' % (enc_message.decode(), iv_env.decode())

    # FIXME:
    #  setters should probably invalidate the id and sig as they'll need to be done again,
    #  though only important if going to post
    @content.setter
    def content(self, content):
        self._content = content

    @property
    def sig(self):
        return self._sig

    def __str__(self):
        ret = super(Event, self).__str__()
        # on signed events we can retrn something more useful
        if self.id:
            ret =  '%s@%s' % (self.id,self._created_at)
        return ret