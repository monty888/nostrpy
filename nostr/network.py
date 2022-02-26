"""
    web socket netork stuff for our nostr client
"""
from __future__ import annotations
import logging
import time

import secp256k1
import websocket
import rel
import json
from json import JSONDecodeError
import hashlib
from datetime import datetime, timedelta
from nostr.util import util_funcs
from nostr.persist import Store
from data.data import DataSet
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
        ], separators=(',',':'))

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
            f.writelines(json.dumps(evt)+'\n')
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
            self._store.add_event(evt)
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

class Client:

    @classmethod
    def relay_events_to_file(cls, relay_url, filename, filter=None):
        """

        subscribes to given relay and outputs to file all events matching the filter then exits
        because its a subscription rather query that will return everything the critera we use to stop
        is either since an event that is has created_at>= when we started or if we didn't see an event for 10s

        :param relay_url: relay url
        :param filename: file to export to
        :param filter: nostr filter, events to select
        :return: None
        """
        my_client = Client(relay_url).start()
        if filter is None:
            filter = {}

        last_event_at = datetime.now()
        started_at_ticks = util_funcs.date_as_ticks(last_event_at)

        def check_since(since):
            nonlocal last_event_at
            # update time we last saw an event
            last_event_at = datetime.now()
            if started_at_ticks-since <= 0:
                my_client.end()

        my_client.subscribe('copy',
                            [EventTimeHandler(callback=check_since),
                             FileEventHandler(filename)],
                            filter)

        def time_since_event():
            nonlocal last_event_at
            run = True
            while(run):
                time_since_evt = (datetime.now()-last_event_at).seconds
                print('time since event - %s' % time_since_evt)
                if time_since_evt >= 10:
                    run = False
                time.sleep(1)
            # we done
            my_client.end()

        Thread(target=time_since_event).start()

    @classmethod
    def post_events_from_file(cls, relay_url, filename):
        """
        post events to a really that were previously exported with relay_events_to_file
        It's possible relays well reject some reason for example maybe events that are too old...
        :param relay_url: relay url
        :param filename: file containing events as json seperated by newline
        :return:
        """
        with Client(relay_url) as my_client:
            print(my_client)
            with open(filename, "r") as f:
                try:
                    l = f.readline()
                    while l:
                        try:
                            evt = Event.create_from_JSON(json.loads(l))
                            # when we get events from relay the key extension is missing because nostr only uses keys as
                            # 02 type. we add 2 extra chars which will be ignored and striped when the event data is sent
                            if(len(evt.pub_key)==64):
                                evt.pub_key = 'XX' + evt.pub_key

                            my_client.publish(evt)
                        except JSONDecodeError as je:
                            logging('Client::post_events_from_file - problem loading event data %s - %s' % (l, je))
                        l = f.readline()


                except Exception as e:
                    print(e)


    def __init__(self, relay_url):
        self._url = relay_url
        self._handlers = {}

    @property
    def url(self):
        return self._url

    def subscribe(self, sub_id, handler=None, filters={}):
        the_req = ['REQ']

        if sub_id is None:
            sub_id = self._get_sub_id()
        the_req.append(sub_id)
        the_req.append(filters)

        the_req = json.dumps(the_req)

        logging.debug('Client::subscribe - %s', the_req)
        # TODO: at the moment there'd be no point subscribing if you don't pass handler
        #  because there's no way of adding later
        #
        if handler:
            # caller only passed in single handler
            if not hasattr(handler, '__iter__'):
                handler = [handler]
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

    def _do_events(self, for_sub, message):
        if for_sub in self._handlers:
            for c_handler in self._handlers[for_sub]:
                try:
                    c_handler.do_event(message[2], self._url)
                except Exception as e:
                    # TODO: add name property to handlers
                    logging.debug('Client::_do_events in handler %s - %s' % (c_handler, e))
        else:
            logging.debug(
                'Network::_on_message event for subscription with no handler registered subscription : %s\n event: %s' % (
                for_sub, message))

    def _on_message(self, ws, message):
        message = json.loads(message)
        type = message[0]
        for_sub = message[1]
        if type=='EVENT':
            self._do_events(for_sub, message)
        elif type=='NOTICE':
            logging.debug('NOTICE!! %s' % message[1])
        else:
            logging.debug('Network::_on_message unexpected type %s' % type)

    def _on_error(self, ws, error):
        print(error)

    def _on_close(self, ws, close_status_code, close_msg):
        # probably won't see this
        print("### closed %s ###", self._url)

    def _on_open(self, ws):
        print('Opened connection %s' % self._url)

    def start(self):
        self._ws = websocket.WebSocketApp(self._url,
                                          on_open=self._on_open,
                                          on_message=self._on_message,
                                          on_error=self._on_error,
                                          on_close=self._on_close)
        self._ws.run_forever(dispatcher=rel)  # Set dispatcher to automatic reconnection

        # not sure about this at all!?...
        # rel.signal(2, rel.abort)  # Keyboard Interrupt
        def my_thread():
            rel.dispatch()
        Thread(target=my_thread).start()

        # so can open.start() and asign in one line
        return self

    def end(self):
        self._ws.close()
        rel.abort()

    # so where appropriate can use with syntax, exit function probably needs to do more...
    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()

