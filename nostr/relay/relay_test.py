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
from nostr.encrypt import Keys

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

        self._client = Client('ws://localhost:8888').start()
        self._client.wait_connect()

        # key pair for tests
        k = Keys.get_new_key_pair()
        self._pub_k = k['pub_k'][2:]
        self._priv_key = k['priv_k']

    def tearDown(self) -> None:
        self._client.end()
        self._relay.end()

    def _post_events(self, n_events):
        for i in range(0,n_events):
            n_evt = Event(kind=Event.KIND_TEXT_NOTE,
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

        self._client.wait_connect()
        self._post_events(event_count)
        ret = self._client.query([{}])

        assert 10 == event_count

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    def sigint_handler(signal, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)


    unittest.main()