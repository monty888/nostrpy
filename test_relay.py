import logging
from nostr.relay import Relay
from nostr.persist import RelayStore

# stuff that eventually should be config/come from cmdline
DB_FILE = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr-relay.db'
HOST = 'LOCALHOST'
PORT = 8081
LOG_LEVEL = logging.DEBUG

def db_create():
    my_store = RelayStore(DB_FILE)
    my_store.create()

def db_destroy():
    my_store = RelayStore(DB_FILE)
    my_store.destroy()

def test_relay_limit_message_length(max_length=10):
    # a relay that'll only allow message where content length <=max_length
    from nostr.relay import LengthAcceptReqHandler
    my_store = RelayStore(DB_FILE)
    my_relay = Relay(my_store, accept_req_handler=LengthAcceptReqHandler(max=max_length))
    my_relay.start(host=HOST, port=PORT)

def test_relay_limit_post_time(tick_min=5):
    # a relay that'll only allow message where a set time has passed since last post by pubkey
    # ticks is in secs
    from nostr.relay import ThrottleAcceptReqHandler
    my_store = RelayStore(DB_FILE)
    my_relay = Relay(my_store, accept_req_handler=ThrottleAcceptReqHandler(tick_min=tick_min))
    my_relay.start(host=HOST, port=PORT)

def start_relay():
    my_store = RelayStore(DB_FILE)
    my_relay = Relay(my_store)
    my_relay.start(host=HOST, port=PORT)

if __name__ == "__main__":
    logging.getLogger().setLevel(LOG_LEVEL)
    test_relay_limit_post_time()






