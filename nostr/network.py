"""
    web socket netork stuff for our nostr client
"""
from __future__ import annotations
import logging
import secp256k1
import websocket
import rel
import json
import hashlib
from datetime import datetime
from nostr.util import util_funcs
from threading import Thread

rel.safe_read()

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

    def __init__(self, id=None, sig=None, kind=None, content=None, tags=None, pub_key=None):
        self._id = id
        self._sig = sig
        self._kind = kind
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
        ], separators=(',',':'))

        print(ret)
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
        sig = pk.schnorr_sign(id_bytes,bip340tag='',raw=True)
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


class Client:

    def __init__(self, relay_url):
        self._url = relay_url
        self._ws = websocket.WebSocketApp(self._url,
                                          on_open=self._on_open,
                                          on_message=self._on_message,
                                          on_error=self._on_error,
                                          on_close=self._on_close)
        self._handlers = {}

        self._ws.run_forever(dispatcher=rel)  # Set dispatcher to automatic reconnection

        # not sure about this at all!?...
        # rel.signal(2, rel.abort)  # Keyboard Interrupt
        def my_thread():
            rel.dispatch()
        Thread(target=my_thread).start()

    @property
    def url(self):
        return self._url

    def subscribe(self, sub_id, handler, filters={}):
        the_req = ['REQ']

        if sub_id is None:
            sub_id = self._get_sub_id()
        the_req.append(sub_id)
        the_req.append(filters)

        the_req = json.dumps(the_req)

        logging.debug('Client::subscribe - %s', the_req)
        self._handlers[sub_id] = handler
        self._ws.send(the_req)
        return sub_id

    def publish(self, evt: Event):
        logging.debug('Client::publish - %s', evt.event_data())


        to_pub = json.dumps([
            'EVENT', evt.event_data()
        ])

        self._ws.send(to_pub)


    def _get_sub_id(self):
        pass

    def _on_message(self, ws, message):
        message = json.loads(message)
        type = message[0]
        for_sub = message[1]
        if type=='EVENT':
            if for_sub in self._handlers:
                self._handlers[for_sub](message[2])
            else:
                logging.debug('Network::_on_message unexpected subscription??? %s' % for_sub)
        elif type=='NOTICE':
            logging.debug('NOTICE!! %s' % message[1])
        else:
            logging.debug('Network::_on_message unexpected type %s' % type)

    def _on_error(self, ws, error):
        print(error)

    def _on_close(self, ws, close_status_code, close_msg):
        print("### closed ###")

    def _on_open(self, ws):
        print("Opened connection")
