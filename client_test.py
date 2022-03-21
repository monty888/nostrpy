import logging
import time
from datetime import datetime
from nostr.client.client import Client
from nostr.client.event_handlers import PrintEventHandler
from nostr.client.persist import Store

# stuff that eventually should be config/come from cmdline
DB_FILE = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
RELAY_URL = 'ws://localhost:8081/'
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
    Client.post_events_from_file(RELAY_URL,BASE_DIR+'event_with_e_tag.json')


def test_import_events(filename=None):
    if filename is None:
        filename = BASE_DIR + 'events.json'

    Client.post_events_from_file(RELAY_URL, filename)


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


def test_events_to_file(relay=None, filename=None, filter={}):
    if relay is None:
        relay = RELAY_URL
    if filename is None:
        filename = '%s%s_events.json' % (BASE_DIR, f'{datetime.now():%Y%m%d%H%M%S}')
    print(filename)
    Client.relay_events_to_file(relay, filename, filter)


def test_postings():
    import random
    from nostr.util import util_funcs
    from datetime import datetime
    from hashlib import md5
    from nostr.event import Event
    my_client = Client(RELAY_URL).start()
    while True:
        msg = str(random.randrange(1, 1000)) + str(util_funcs.date_as_ticks(datetime.now()))
        msg = md5(msg.encode('utf8')).hexdigest()

        n_Event = Event(kind=Event.KIND_TEXT_NOTE,
                        content=msg,
                        pub_key='40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486')
        n_Event.sign('5c7102135378a5223d74ce95f11331a8282ea54905d61018c7f1bc166994a1d9')

        my_client.publish(n_Event)
        time.sleep(.1)



if __name__ == "__main__":
    logging.getLogger().setLevel(LOG_LEVEL)
    # test_filter_match([{
    #         '#p': ['3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d']
    #     },
    #     {
    #         'ids' : ['03da578a8b3c9c6a51', '8a05a9825e6a9447c6e50d01d92289cabb8e0f0e48e4e9bb3324dbdafa236280']
    #     },
    #     {
    #         'kinds' : 4
    #     }])

    # test_filter_match({
    #     'author' : '40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486'
    # })
    from nostr.event import Event
    test_events_to_file(filter={
        'kinds': Event.KIND_META
    },filename=BASE_DIR+'meta_only.json')

    # test_import_events(BASE_DIR+'events.json')
    # from nostr.ident import Profile
    # Profile.import_from_file('/home/shaun/.nostrpy/local_profiles.csv',DB_FILE)
