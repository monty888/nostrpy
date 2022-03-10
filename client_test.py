import logging
from nostr.network import Client
from nostr.event_handlers import PrintEventHandler
from nostr.persist import Store
import time

# stuff that eventually should be config/come from cmdline
DB_FILE = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
RELAY_URL = 'ws://localhost:8081/websocket'
LOG_LEVEL = logging.DEBUG
BASE_DIR = '/home/shaun/.nostrpy/'

def db_create():
    my_store = Store(DB_FILE)
    my_store.create()

def test_unsubscribe():
    my_client = Client(RELAY_URL).start()
    # filter to print everything for this sub to screen
    my_client.subscribe('test_id', PrintEventHandler(), {})
    # wait post something from another client and you should see, you'll also see previous events because we used {}
    # as filter
    time.sleep(5)
    my_client.unsubscribe('test_id')
    # at if you open another con and post to client you should see anything anymore
    time.sleep(20)

def test_import_taged_event():
    Client.post_events_from_file(RELAY_URL,BASE_DIR+'event_with_tag.json')

def test_import_import_events():
    Client.post_events_from_file(RELAY_URL, BASE_DIR+'events.json')

def test_max_subscribe():
    my_client = Client(RELAY_URL).start()
    for i in range(0,5):
        id = my_client.subscribe(filters={})
        # NOTE to know that sub failed you'd need to check the notice
        # not sure if there is a standard msg yet for failure
        print('attempt add sub %s as %s' % (i, id))
    print('DONE')
    time.sleep(10)
    my_client.end()

def test_filter_match(filter):
    my_client = Client(RELAY_URL).start()
    my_client.subscribe(handler=PrintEventHandler(), filters=filter)

if __name__ == "__main__":
    logging.getLogger().setLevel(LOG_LEVEL)
    test_filter_match({
        'kinds': 4
    })
