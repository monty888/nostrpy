"""
    web socket netork stuff for our nostr client
"""
from __future__ import annotations
import logging
import time
import websocket
import rel
import json
from json import JSONDecodeError
from datetime import datetime, timedelta
from nostr.util import util_funcs
from nostr.event import Event, EventTimeHandler, FileEventHandler
from threading import Thread

rel.safe_read()

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


class ClientPool:
    """
        a collection of Clients so we can subscribe/post to a number of relays with single call
        can pass in
            [relay_url,...]     -   Client objs created for each url
            [Client,...]        -   alrady created objs
            [
                {
                    client : urel_str/Client,
                    read : bool
                    write : bool
                }
            ]
            also mix of the above
            where read/write not passed in they'll be True

    """
    def __init__(self, clients):
        self._clients = {}
        for c_client in clients:
            try:
                if isinstance(c_client, str):
                    self._clients[c_client] = {
                        'client': Client(c_client),
                        'read': True,
                        'write': True
                    }
                elif isinstance(c_client, Client):
                    self._clients[c_client] = {
                        'client': Client(c_client),
                        'read': True,
                        'write': True
                    }
                elif isinstance(c_client, dict):
                    to_add = {
                        'client': c_client['client'],
                        'read': True,
                        'write': True
                    }
                    if isinstance(to_add['client'], str):
                        to_add['client'] = Client(to_add['client'])
                        if 'read' in c_client:
                            to_add['read'] = c_client['read']
                        if 'write' in c_client:
                            to_add['write'] = c_client['write']

            except Exception as e:
                logging.debug('ClientPool::__init__ - %s' % e)


    # methods work on all but we'll probably want to be able to name on calls
    def start(self):
        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            the_client.start()

    def subscribe(self, sub_id, handler=None, filters={}):
        for c_client in self._clients:
            the_client = self._clients[c_client]['client']
            the_client.subscribe(sub_id, self, filters)

    def do_event(self, evt, relay):
        print(evt,relay)

    def __str__(self):
        ret_arr = []
        for c_client in self._clients:
            the_client = self._clients[c_client]
            ret_arr.append(c_client+ '\n')
            ret_arr.append('read: %s write: %s\n' % (the_client['read'],
                                                     the_client['write']))

        return ''.join(ret_arr)
