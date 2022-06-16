"""
    web socket netork stuff for our nostr client
"""
from __future__ import annotations
import logging
import sys
import time
import websocket
from gevent import Greenlet
from collections import OrderedDict
from websocket._exceptions import WebSocketConnectionClosedException
import json
import random
from hashlib import md5
from json import JSONDecodeError
from datetime import datetime
from nostr.util import util_funcs
from nostr.event.event import Event
from nostr.client.event_handlers import EventTimeHandler, FileEventHandler
from threading import Thread

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
            with open(filename, "r") as f:
                try:
                    l = f.readline()
                    while l:
                        try:
                            evt = Event.create_from_JSON(json.loads(l))
                            my_client.publish(evt)
                        except JSONDecodeError as je:
                            logging.debug('Client::post_events_from_file - problem loading event data %s - %s' % (l, je))
                        l = f.readline()


                except Exception as e:
                    print(e)

    def __init__(self, relay_url,
                 on_connect=None,
                 on_status=None,
                 on_eose=None,
                 read=True,
                 write=True):
        self._url = relay_url
        self._handlers = {}
        self._run = True
        self._ws = None
        self._last_con = None
        self._last_err = None
        self._con_fail_count = 0
        self._on_connect = on_connect
        self._on_status = on_status
        self._is_connected = False
        self._read = read
        self._write = write
        self._eose_func = on_eose

    @property
    def url(self):
        return self._url

    def set_on_connect(self, on_connect):
        # probably should either pass in on create or call this before start()
        # anyway if we already connected the func passed in will be called straight away
        # and then again whenever we reconnect e.g. after losing connection
        self._on_connect = on_connect
        if self._is_connected:
            self._on_connect(self)

    def set_status_listener(self, on_status):
        self._on_status = on_status

    def subscribe(self, sub_id=None, handlers=None, filters={}):
        """
        :param sub_id: if none a rndish 4digit hex sub_id will be given
        :param handler: single or [] of handlers that'll get called for events on sub
        :param filters: filter to be sent to relay for matching events were interested in
        see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
        :return: sub_id
        """

        the_req = ['REQ']

        # no sub given, ok we'll generate one
        if sub_id is None:
            sub_id = self._get_sub_id()
        the_req.append(sub_id)
        the_req.append(filters)

        the_req = json.dumps(the_req)
        logging.debug('Client::subscribe - %s', the_req)
        # TODO: at the moment there'd be no point subscribing if you don't pass handler
        #  because there's no way of adding later
        #
        if handlers:
            # caller only passed in single handler
            if not hasattr(handlers, '__iter__'):
                handlers = [handlers]
            self._handlers[sub_id] = handlers

        self._ws.send(the_req)
        self._reset_status()
        return sub_id

    def _get_sub_id(self):
        """
        :return: creates a randomish 4digit hex to be used as sub_id if nothing supplied
        should be plenty as should only be using a few subs at most and relay will probbaly be
        restricting any more
        """
        ret = str(random.randrange(1, 1000)) + str(util_funcs.date_as_ticks(datetime.now()))
        ret = md5(ret.encode('utf8')).hexdigest()[:4]
        return ret

    def _reset_status(self):
        self._last_con = datetime.now()
        self._con_fail_count = 0
        self._is_connected = True
        self._last_err = None

    def unsubscribe(self, sub_id):
        # if subscribed, should we error if unknown sub_id?
        if sub_id in self._handlers:
            self._ws.send(json.dumps(['CLOSE', sub_id]))
            self._handlers[sub_id]
            self._reset_status()
        self._reset_status()

    def publish(self, evt: Event):
        logging.debug('Client::publish - %s', evt.event_data())
        to_pub = json.dumps([
            'EVENT', evt.event_data()
        ])

        self._ws.send(to_pub)
        self._reset_status()

    def set_end_stored_events(self, eose_func=None):
        self._eose_func = eose_func

    def _on_message(self, ws, message):
        self._reset_status()

        message = json.loads(message)

        type = message[0]
        sub_id = message[1]
        if type == 'EVENT':
            self._do_events(sub_id, message)
        elif type == 'NOTICE':
            # creator should probably be able to suppliy a notice handler
            logging.debug('NOTICE!! %s' % sub_id)
        elif type == 'EOSE':
            # if relay support nip15 you get this event after the relay has sent the last stored event
            # at the moment a single function but might be better to add as option to subscribe
            if self._eose_func:
                self._eose_func(sub_id)
            else:
                logging.debug('NIP-15 end of stored events for %s' % sub_id)

        else:
            logging.debug('Network::_on_message unexpected type %s' % type)

    def _do_events(self, sub_id, message):
        the_evt: Event

        if sub_id in self._handlers:
            try:
                the_evt = Event.create_from_JSON(message[2])
                for c_handler in self._handlers[sub_id]:
                    try:
                        c_handler.do_event(sub_id, the_evt, self._url)
                    except Exception as e:
                        logging.debug('Client::_do_events in handler %s - %s' % (c_handler, e))

            except Exception as e:
                # TODO: add name property to handlers
                logging.debug('Client::_do_events %s' % (e))
        else:
            logging.debug(
                'Client::_on_message event for subscription with no handler registered subscription : %s\n event: %s' % (
                sub_id, message))

    def _on_error(self, ws, error):
        self._last_err = str(error)
        logging.debug('Client::_on_error %s' % error)

    def _on_close(self, ws, close_status_code, close_msg):
        logging.debug('Client::_on_close %s' % self._url)

    def _on_open(self, ws):
        logging.debug('Client::_on_open %s' % self._url)
        self._reset_status()
        if self._on_connect:
            self._on_connect(self)


    def start(self):
        # should probably check self._run and error if already true

        # not sure about this at all!?...
        # rel.signal(2, rel.abort)  # Keyboard Interrupt
        def get_con():
            self._ws = websocket.WebSocketApp(self._url,
                                              on_open=self._on_open,
                                              on_message=self._on_message,
                                              on_error=self._on_error,
                                              on_close=self._on_close)
            self._ws.run_forever()  # Set dispatcher to automatic reconnection

        def monitor_thread():
            while self._run:
                try:
                    if self._on_status:
                        self._on_status(self.status)
                except Exception as e:
                    logging.debug(e)
                time.sleep(1)

        def my_thread():
            Thread(target=monitor_thread).start()

            while self._run:
                try:
                    get_con()
                except BrokenPipeError as be:
                    print('Client::my_thread %s\n check that connection details %s are correct' % (be, self._url))
                    self._run = False
                except WebSocketConnectionClosedException as wsc:
                    print('Client::my_thread %s\n lost connection to %s '
                          'should try to reestablish but for now it dead!' % (wsc, self._url))
                time.sleep(1)
                self._ws = None
                self._con_fail_count += 1
                self._is_connected = False

        Thread(target=my_thread).start()

        # time.sleep(1)
        # so can open.start() and asign in one line
        return self

    @property
    def status(self):
        con_count = 0
        if self._is_connected:
            con_count = 1

        return {
            'connected': self._is_connected,
            'fail_count': self._con_fail_count,
            'last_connect': self._last_con,
            'last_err': self._last_err,
            # so status from single Client looks same as ClientPool
            'relay_count': 1,
            'connect_count': con_count
        }

    def end(self):
        self._run = False
        if self._ws:
            self._ws.close()

        # rel.abort()

    # so where appropriate can use with syntax, exit function probably needs to do more...
    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()

    def __str__(self):
        return self._url

    def __len__(self):
        return 1

    def __iter__(self):
        yield self

    def __getitem__(self, i):
        return self

    @property
    def connected(self):
        return self._is_connected

    @property
    def last_connected(self):
        # this is actually the last message we did but probably we can get a better last con time from the
        # ws object itself
        #
        return self._last_con

    @property
    def last_error(self):
        return self._last_err

class ClientPool:
    """
        a collection of Clients so we can subscribe/post to a number of relays with single call
        can pass in
            [relay_url,...]     -   Client objs created for each url
            [Client,...]        -   alrady created objs
            [
                {
                    client : relay_url,
                    read : bool
                    write : bool
                }
            ]
            also mix of the above
            where read/write not passed in they'll be True

    """
    def __init__(self, clients,
                 on_connect=None,
                 on_status=None):
        # Clients (Relays) we connecting to
        self._clients = {}
        # subscription event handlers keyed on sub ids
        self._handlers = {}

        # merge of status from pool, for example a single client connected means we consider connected to be True
        # last con will be newest of any relay we have etc....
        # indivdual relay status also stored here keyed on url
        self._status = {
            'connected': False,
            'relays': {}
        }
        # if want to listen for status changes from this group of relays
        self._on_status = on_status

        # for whatever reason using pool but only a single client handed in
        if isinstance(clients, str):
            clients = [clients]

        def get_on_status(relay_url):
            def on_status(status):
                self._on_pool_status(relay_url, status)
            return on_status

        for c_client in clients:
            try:
                if isinstance(c_client, str):
                    # read/write default True
                    the_client = self._clients[c_client] = Client(c_client,
                                                                  on_connect=on_connect)
                elif isinstance(c_client, Client):
                    the_client = self._clients[c_client.url] = c_client
                elif isinstance(c_client, dict):
                    read = True
                    if read in c_client:
                        read = c_client['read']
                    write = True
                    if write in c_client:
                        write = c_client['write']

                    client_url = c_client['client']

                    the_client = self._clients[client_url] = Client(client_url,
                                                                    on_connect=on_connect,
                                                                    read=read,
                                                                    write=write)

                self._clients[the_client.url].set_status_listener(get_on_status(the_client.url))

            except Exception as e:
                logging.debug('ClientPool::__init__ - %s' % e)

    def set_on_connect(self, on_connect):
        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            the_client.set_on_connect(on_connect)

    def _on_pool_status(self, relay_url, status):
        # the status we return gives each individual relay status at ['relays']
        self._status['relays'][relay_url] = status

        # high level to mimic single relay, any single relay connected counts as connected
        # we also add a count/connected count for use by caller
        n_status = {
            'relay_count': 0,
            'connect_count': 0,
            'connected': False,
            'last_connect': None,
            'fail_count': None
        }

        # see how many relays we have and how many are connected and give a value for each of
        # connected, fail_count, last_connect, last_err merged
        # as long as any single relay is connected all will look ood unless you look at
        # the relay/connect count
        for c_relay in self._status['relays']:
            r_status = self._status['relays'][c_relay]
            n_status['relay_count'] += 1
            if r_status['connected']:
                n_status['connected'] = True
                n_status['fail_count'] = 0
                n_status['connect_count'] += 1
                n_status['last_err'] = None

            # only fill in err counts if we're not connected (wiped if we find we're connected later)
            # last_err comes from relay with highest fail_count
            if not n_status['connected']:
                if n_status['fail_count'] is None or r_status['fail_count'] > n_status['fail_count']:
                    n_status['fail_count'] = r_status['fail_count']
                    n_status['last_err'] = r_status['last_err']

            # probably this comes from a connected relay but guess it could come from one that went bad now
            if n_status['last_connect'] is None or (r_status['last_connect']
                                                    and r_status['last_connect'] > n_status['last_connect']):
                n_status['last_connect'] = r_status['last_connect']

        # hopefully this is safe... self._status will be getting hit by mutiple threads so...
        status_copy = self._status.copy()
        status_copy.update(n_status)
        self._status = status_copy

        if self._on_status:
            self._on_status(self._status)

    def set_status_listener(self, on_status):
        self._on_status = on_status

    @property
    def status(self):
        return self._status

    @property
    def connected(self):
        return self._status['connected']

    # methods work on all but we'll probably want to be able to name on calls
    def start(self):
        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            the_client.start()

    def end(self):
        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            the_client.end()

    def subscribe(self, sub_id=None, handlers=None, filters={}):

        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            sub_id = the_client.subscribe(sub_id, self, filters)

        # add handlers if any given - nothing happens on receiving events if not
        if handlers:
            if not hasattr(handlers, '__iter__'):
                handlers = [handlers]
            self._handlers[sub_id] = handlers

        return sub_id

    def publish(self, evt: Event):
        logging.debug('ClientPool::publish - %s', evt.event_data())
        for c_client in self._clients:
            if self._clients[c_client]['write']:
                try:
                    self._clients[c_client]['client'].publish(evt)
                except Exception as e:
                    logging.debug(e)

    def do_event(self, sub_id, evt, relay):
        # shouldn't be possible...
        if relay not in self._clients:
            raise Exception('ClientPool::do_event received event from unexpected relay - %s WTF?!?' % relay)

        # only do anyhting if relay read is True
        if self._clients[relay]['read']:
            # note no de-duplication is done here, you might see the same event from mutiple relays
            if sub_id in self._handlers:
                for c_handler in self._handlers[sub_id]:
                    c_handler.do_event(sub_id, evt, relay)
            else:
                # supose this might happen if unsubscribe then evt comes in...
                logging.debug(
                    'ClientPool::do_event event for subscription with no handler registered subscription : %s\n event: %s' % (
                        sub_id, evt))

    def __repr__(self):
        return self._clients

    def __str__(self):
        ret_arr = []
        for c_client in self._clients:
            ret_arr.append(str(self._clients[c_client]['client']))

        return ', '.join(ret_arr)

    def __len__(self):
        return len(self._clients)

    def __iter__(self):
        for c_client in self._clients:
            yield self._clients[c_client]

    def __getitem__(self, i):
        # row at i
        return self._clients[i]
