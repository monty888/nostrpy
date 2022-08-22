"""
    web socket netork stuff for our nostr client
"""
from __future__ import annotations
import logging
import sys
import time
import websocket
import requests
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
from threading import Thread, BoundedSemaphore
from enum import Enum


class RunState(Enum):
    init = -1
    running = 0
    starting = 1
    stopping = 2
    stopped = 3

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
                 write=True,
                 emulate_eose=True):
        self._url = relay_url
        self._subs = {}
        self._run = False
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
        self._emulate_eose = emulate_eose
        # NIP11 info for the relay we're connected to
        self._relay_info = None

        self._state = RunState.init

    @property
    def url(self):
        return self._url

    @property
    def relay_information(self):
        """
        what to do in case of error?
        :return:
        """
        if self._relay_info is None:
            info_url = self._url.replace('ws:','http:').replace('wss:', 'https:')
            response = requests.get(info_url,
                                    headers={
                                        'Accept': 'application/nostr+json'
                                    })
            if response.status_code == 200:
                try:
                    self._relay_info = json.loads(response.content)
                except JSONDecodeError as je:
                    self._relay_info = {}

        return self._relay_info

    def set_on_connect(self, on_connect):
        # probably should either pass in on create or call this before start()
        # anyway if we already connected the func passed in will be called straight away
        # and then again whenever we reconnect e.g. after losing connection
        self._on_connect = on_connect
        if self._is_connected:
            self._on_connect(self)

    def set_status_listener(self, on_status):
        self._on_status = on_status

    def subscribe(self, sub_id=None, handlers=None, filters={}, wait_connect=False, eose_func=None):
        """
        :param sub_id: if none a rndish 4digit hex sub_id will be given
        :param handler: single or [] of handlers that'll get called for events on sub
        :param filters: filter to be sent to relay for matching events were interested in
        see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
        :return: sub_id
        """

        # block until we have connection, fine for simple stuff
        if wait_connect:
            self.wait_connect()
        the_req = ['REQ']

        # no sub given, ok we'll generate one
        if sub_id is None:
            sub_id = self._get_sub_id()
        the_req.append(sub_id)
        if isinstance(filters, dict):
            filters = [filters]
        the_req = the_req + filters

        the_req = json.dumps(the_req)
        logging.debug('Client::subscribe - %s', the_req)

        # caller only passed in single handler
        if not hasattr(handlers, '__iter__'):
            handlers = [handlers]
        self._subs[sub_id] = {
            'handlers': handlers,
            # if we have eose function then the caller will receive all stored events via the EOSE func
            # and this will be set True when done. If not the events will look like they come in 1 by 1
            'is_eose': eose_func is None and self._eose_func is None,
            'eose_func': eose_func,
            'events': [],
            'start_time': datetime.now(),
            'last_event': None
        }

        if not self._relay_supports_eose() and self._emulate_eose:
            logging.debug('emulating EOSE for sub_id %s' % sub_id)
            def my_emulate():
                is_wait = True
                from datetime import timedelta
                while is_wait:
                    sub_info = self._subs[sub_id]
                    now = datetime.now()
                    if (sub_info['last_event'] is not None and now - sub_info['last_event'] > timedelta(seconds=2)) or \
                            (now - sub_info['start_time'] > timedelta(seconds=2)):
                        is_wait = False
                    time.sleep(1)

                self._on_message(self._ws, json.dumps(['EOSE', sub_id]))
            Thread(target=my_emulate).start()

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
        # FIXME: this probably needs to be wrapped in a lock
        if sub_id in self._subs:
            self._ws.send(json.dumps(['CLOSE', sub_id]))
            del self._subs[sub_id]
            self._reset_status()
        self._reset_status()

    def publish(self, evt: Event):
        if self.write:
            logging.debug('Client::publish - %s', evt.event_data())
            to_pub = json.dumps([
                'EVENT', evt.event_data()
            ])
            self._ws.send(to_pub)

        self._reset_status()

    def query(self, url: str, filters=[]):
        """
            do simple one of queries to a given relay
        """
        is_done = False
        ret = None

        def my_done(the_client: Client, sub_id: str, events):
            nonlocal is_done
            nonlocal ret
            ret = events
            is_done = True

        sub_id = self.subscribe(filters=filters, wait_connect=True, eose_func=my_done)
        while is_done is False:
            time.sleep(0.1)
            if self.connected is False:
                print('raise an error here?!?!?!?')

        self.unsubscribe(sub_id)

        return ret

    def set_end_stored_events(self, eose_func=None):
        self._eose_func = eose_func

    def _on_message(self, ws, message):
        self._reset_status()

        message = json.loads(message)

        type = message[0]
        sub_id = message[1]
        if type == 'EVENT':
            if self._read:
                self._do_events(sub_id, message)
        elif type == 'NOTICE':
            # creator should probably be able to suppliy a notice handler
            logging.debug('NOTICE!! %s' % sub_id)
        elif type == 'EOSE':
            # if relay support nip15 you get this event after the relay has sent the last stored event
            # at the moment a single function but might be better to add as option to subscribe
            if not self._have_sub(sub_id):
                logging.debug('Client::_on_message EOSE event for unknown sub_id?!??!! - %s' % sub_id)

            # eose defined for this sub
            if self._subs[sub_id]['eose_func'] is not None:
                self._subs[sub_id]['eose_func'](self, sub_id, self._subs[sub_id]['events'])
            #client level eose
            elif self._eose_func:
                self._eose_func(self, sub_id, self._subs[sub_id]['events'])

            # no longer needed
            logging.debug('end of stored events for %s - %s events received' % (sub_id,
                                                                                len(self._subs[sub_id]['events'])))
            self._subs[sub_id]['events'] = []
            self._subs[sub_id]['is_eose'] = True

        else:
            logging.debug('Network::_on_message unexpected type %s' % type)

    def _have_sub(self, sub_id):
        return sub_id in self._subs

    def _relay_supports_eose(self):
        relay_info = self.relay_information
        return relay_info and 'supported_nips' in relay_info and 15 in relay_info['supported_nips']

    def _check_eose(self, sub_id, message):
        the_evt: Event
        ret = self._subs[sub_id]['is_eose']

        # these are stored events
        if ret is False:
            if self._relay_supports_eose() or self._emulate_eose:
                self._subs[sub_id]['events'].append(Event.create_from_JSON(message[2]))
                self._subs[sub_id]['last_event'] = datetime.now()
            else:
                # eose not supported by relay and we're not emulating
                self._subs[sub_id]['is_eose'] = True
                ret = True

        return ret

    def _do_events(self, sub_id, message):
        the_evt: Event
        if not self._have_sub(sub_id):
            logging.debug(
                'Client::_on_message event for subscription with no handler registered subscription : %s\n event: %s' % (
                    sub_id, message))
            return

        if sub_id in self._subs and self._check_eose(sub_id, message):
            try:
                the_evt = Event.create_from_JSON(message[2])
                for c_handler in self._subs[sub_id]['handlers']:
                    try:
                        c_handler.do_event(sub_id, the_evt, self._url)
                    except Exception as e:
                        logging.debug('Client::_do_events in handler %s - %s' % (c_handler, e))

            except Exception as e:
                # TODO: add name property to handlers
                logging.debug('Client::_do_events %s' % (e))

    def _on_error(self, ws, error):
        self._last_err = str(error)
        logging.debug('Client::_on_error %s' % error)

    def _on_close(self, ws, close_status_code, close_msg):
        logging.debug('Client::_on_close %s' % self._url)
        if self._on_status:
            self._on_status(self.status)

    def _on_open(self, ws):
        logging.debug('Client::_on_open %s' % self._url)
        self._reset_status()
        if self._on_connect:
            self._on_connect(self)
        if self._on_status:
            self._on_status(self.status)

    def _did_comm(self, ws, data):
        self._reset_status()

    @property
    def running(self):
        return self._state == RunState.running

    @property
    def run_state(self):
        return self._state

    def start(self):
        # we should probably error if not correct init or stopped
        if self._state not in (RunState.init, RunState.stopped):
            return
        self._state = RunState.starting
        self._run = True

        # not sure about this at all!?...
        # rel.signal(2, rel.abort)  # Keyboard Interrupt
        def get_con():
            self._ws = websocket.WebSocketApp(self._url,
                                              on_open=self._on_open,
                                              on_message=self._on_message,
                                              on_error=self._on_error,
                                              on_close=self._on_close,
                                              on_ping=self._did_comm,
                                              on_pong=self._did_comm)
            self._ws.run_forever(ping_interval=60)  # Set dispatcher to automatic reconnection

        # def monitor_thread():
        #     while self._run:
        #         try:
        #             if self._on_status:
        #                 self._on_status(self.status)
        #         except Exception as e:
        #             logging.debug(e)
        #         time.sleep(1)

        def my_thread():
            # Thread(target=monitor_thread).start()
            self._state = RunState.running
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

            self._state = RunState.stopped

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
            'connect_count': con_count,
            'read': self._read,
            'write': self._write
        }

    def end(self):
        self._state = RunState.stopping
        self._run = False
        if self._ws:
            self._ws.close()

    def wait_connect(self):
        while not self.connected:
            time.sleep(0.1)

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
    def read(self):
        return self._read

    @property
    def write(self):
        return self._write

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
                 on_status=None,
                 on_eose=None):
        # Clients (Relays) we connecting to
        self._clients = {}
        # guards access to self._clients
        self._clients_lock = BoundedSemaphore()
        # subscription event handlers keyed on sub ids
        self._handlers = {}

        self._on_connect = on_connect
        self._on_eose = on_eose
        self._state = RunState.init

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

        for c_client in clients:
            try:
                the_client = self.add(c_client)
            except Exception as e:
                logging.debug('ClientPool::__init__ - %s' % e)

    def add(self, client, auto_start=True) -> Client:
        """
        :param auto_start: start the client if the pool is started
        :param client: client, url str or {
            'client': url
            read: true/false
            write: true/false
        }
        :return: Client
        """
        ret: Client = None
        if isinstance(client, str):
            # read/write default True
            ret = Client(client,
                         on_connect=self._on_connect,
                         on_eose=self._on_eose)
        elif isinstance(client, Client):
            ret = client
            ret.set_on_connect(self._on_connect)
            ret.set_end_stored_events(self._on_eose)
        elif isinstance(client, dict):
            read = True
            if 'read' in client:
                read = client['read']
            write = True
            if 'write' in client:
                write = client['write']

            client_url = client['client']
            ret = Client(client_url,
                         on_connect=self._on_connect,
                         on_eose=self._on_eose,
                         read=read,
                         write=write)

        if ret.url in self._clients:
            raise Exception('ClientPool::add - %s attempted to add Client that already exists' % ret.url)

        # error if trying to add when we're stopped or stopping
        if self._state in (RunState.stopping, RunState.stopped):
            raise Exception('ClientPool::add - can\'t add new client to pool that is stopped or stoping url - %s' % ret.url)

        # TODO: here we should go through handlers and add any subscriptions if they have be added via subscribe
        #  method. Need to cahnge the subscrbe to keep a copy of the filter.. NOTE that normally it's better
        #  to do subscriptions in the on connect method anyhow when using a pool

        # we're started so start the new client
        if auto_start is True and self._state in (RunState.starting, RunState.running):
            # starts it if not already running, if it's started and we're not should we do anything?
            ret.start()

        # for monitoring the relay connection
        def get_on_status(relay_url):
            def on_status(status):
                self._on_pool_status(relay_url, status)
            return on_status

        with self._clients_lock:
            self._clients[ret.url] = ret
            ret.set_status_listener(get_on_status(ret.url))

        return ret

    def remove(self, client_url: str, auto_stop=True):
        if client_url not in self._clients:
            raise Exception('ClientPool::remove attempt to remove client that hasn\'t been added')

        the_client: Client = self._clients[client_url]
        if auto_stop:
            the_client.end()

        with self._clients_lock:
            the_client.set_status_listener(None)
            del self._status['relays'][client_url]
            del self._clients[client_url]

        self._update_pool_status()
        if self._on_status:
            self._on_status(self._status)

        return the_client

    def set_on_connect(self, on_connect):
        for c_client in self._clients_copy():
            the_client = self._clients[c_client]['client']
            the_client.set_on_connect(on_connect)

    def _on_pool_status(self, relay_url, status):
        # the status we return gives each individual relay status at ['relays']
        self._status['relays'][relay_url] = status
        self._update_pool_status()
        if self._on_status:
            self._on_status(self._status)

    def _update_pool_status(self):
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
        with self._clients_lock:
            relays = [c_relay for c_relay in self._status['relays']]

        for c_relay in relays:
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
        # status_copy = self._status.copy()
        # status_copy.update(n_status)
        # self._status = status_copy
        with self._clients_lock:
            self._status.update(n_status)

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
        self._state = RunState.starting

        for c_client in self._clients_copy():
            the_client = self._clients[c_client]
            the_client.start()

        self._state = RunState.running

    def end(self):
        self._state = RunState.stopping
        for c_client in self._clients_copy():
            the_client = self._clients[c_client]
            the_client.end()

        self._state = RunState.stopping

    def _clients_copy(self):
        """
        if looping through clients use this rather then self._clients directly to minimise
        the time we lock
        :return:
        """
        with self._clients_lock:
            ret = [c_client for c_client in self._clients]
        return ret

    def subscribe(self, sub_id=None, handlers=None, filters={}):
        for c_client in self._clients_copy():
            the_client = self._clients[c_client]
            sub_id = the_client.subscribe(sub_id, self, filters)

        # add handlers if any given - nothing happens on receiving events if not
        if handlers:
            if not hasattr(handlers, '__iter__'):
                handlers = [handlers]
            self._handlers[sub_id] = handlers

        return sub_id

    def publish(self, evt: Event):
        logging.debug('ClientPool::publish - %s', evt.event_data())
        c_client: Client

        for c_client in self._clients_copy():
            c_client = self._clients[c_client]
            if c_client.write:
                try:
                    c_client.publish(evt)
                except Exception as e:
                    logging.debug(e)

    def do_event(self, sub_id, evt, relay):
        def get_do_event(handler):
            def my_func():
                handler.do_event(sub_id, evt, relay)
            return my_func

        # shouldn't be possible...
        if relay not in self._clients:
            raise Exception('ClientPool::do_event received event from unexpected relay - %s WTF?!?' % relay)

        # only do anyhting if relay read is True
        if self._clients[relay].read:
            # note no de-duplication is done here, you might see the same event from mutiple relays
            if sub_id in self._handlers:
                for c_handler in self._handlers[sub_id]:
                    # c_handler.do_event(sub_id, evt, relay)
                    Greenlet(get_do_event(c_handler)).start()
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
