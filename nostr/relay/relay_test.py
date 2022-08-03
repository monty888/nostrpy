"""
    tests for the nostr.relay
"""
import unittest
import logging
import signal
import sys
from abc import ABC

from nostr.relay.relay import Relay
from nostr.event.persist import RelayMemoryEventStore
from nostr.event.event import Event
from nostr.client.client import Client
from nostr.client.event_handlers import EventHandler
from threading import Thread
import time

class RelayTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._relay = None
        def start_relay():
            self._relay = Relay(store=RelayMemoryEventStore(),
                                enable_nip15=True)
            self._relay.start(port=8888)

        self._thread = Thread(target=start_relay).start()
        # make sure relay is accepting before allowing on
        while self._relay is None or self._relay.started is False:
            time.sleep(0.1)

        # create a client attached to the relay ready to go
        self._is_connected = False

        def my_connect(the_client: Client):
            self._is_connected = True

        self._client = Client('ws://localhost:8888',
                              on_connect=my_connect).start()

        while self._is_connected is False:
            time.sleep(0.1)

        # key pair for tests
        self._pub_k = '40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486'
        self._priv_key = '5c7102135378a5223d74ce95f11331a8282ea54905d61018c7f1bc166994a1d9'

    def tearDown(self) -> None:
        self._client.end()
        self._relay.end()

    def _post_events(self, n_events):
        for i in range(0,n_events):
            n_evt=Event(kind=Event.KIND_TEXT_NOTE,
                        content='test_note: %s' % i,
                        pub_key=self._pub_k)
            n_evt.sign(self._priv_key)
            self._client.publish(n_evt)

    def test_post(self):
        """
        this just posts 10 events and passes as long as that doesn't break
        if it does probably anything after this is going to break too
        :return:
        """
        self._post_events(10)


    def test_sub(self):
        """
            test a sub by post event_count events and then adding a post to get all events
            n_count should match what we get back from the sub
        """

        # how many event we're going to test with
        event_count = 10
        done = False
        loop_count = 0

        class my_handler(EventHandler):
            def do_event(self, sub_id, evt: Event, relay):
                nonlocal seen_count
                seen_count += 1
        seen_count = 0

        # first post some events
        self._post_events(event_count)

        # now subscribe
        self._client.subscribe(handlers=[my_handler()],filters={})

        # we have nip15 so we'll exit early if we see it
        def my_end(the_client:Client, sub_id, events):
            nonlocal done
            done = True

        self._client.set_end_stored_events(my_end)

        while not done:
            if seen_count == event_count:
                done = True
            time.sleep(0.5)

            loop_count+=1

            # should have been ample time to get all events, something must be wrong?!
            if loop_count>10:
                done = True

        assert seen_count == event_count

if __name__ == '__main__':
    # logging.getLogger().setLevel(logging.DEBUG)
    def sigint_handler(signal, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)


    unittest.main()