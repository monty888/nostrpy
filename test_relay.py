import logging
from nostr.relay import Relay
from nostr.persist import RelayStore

DB_FILE = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr-relay.db'

def db_create():
    my_store = RelayStore(DB_FILE)
    my_store.create()

def start_relay():
    my_store = RelayStore(DB_FILE)
    my_relay = Relay(my_store)
    my_relay.start(port=8081)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    start_relay()