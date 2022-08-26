"""
    starts a web server that gives access to data from a number of nostr servers
"""
import logging
import signal
import sys
import os
import time

from stem.control import Controller
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import getopt
from nostr.client.client import ClientPool, Client
from nostr.client.event_handlers import PersistEventHandler, ProfileEventHandler
from nostr.event.persist import ClientSQLEventStore, Event, ClientSQLiteEventStore, ClientEventStoreInterface, ClientMemoryEventStore
from nostr.ident.persist import SQLiteProfileStore, ProfileStoreInterface,MemoryProfileStore
# from nostr.ident.profile import ProfileEventHandler
from nostr.util import util_funcs
from web.web import NostrWeb

# TODO: also postgres
# defaults here if no config given???
WORK_DIR = '%s/.nostrpy/' % Path.home()
# DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
# EVENT_STORE = ClientSQLEventStore(DB)
# # EVENT_STORE = TransientEventStore()
# PROFILE_STORE = SQLProfileStore(DB)
# # RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# # RELAYS = ['wss://rsslay.fiatjaf.com']
# RELAYS = ['ws://localhost:8081']


def usage():
    print("""
TODO:
    """)
    sys.exit(2)


def get_profile_filter(for_client: Client,
                       event_store: ClientEventStoreInterface):
    """
    returns a filter that'll get you all the meta and contact list events for the client
    that we don't already have
    :param for_client:
    :param event_store:
    :return:
    """
    return [
        {
            'kinds': Event.KIND_META,
            'since': event_store.get_newest(for_client.url,
                                            {
                                                'kinds': Event.KIND_META
                                            })
        },
        {
            'kinds': Event.KIND_CONTACT_LIST,
            'since': event_store.get_newest(for_client.url,
                                            {
                                                'kinds': Event.KIND_CONTACT_LIST
                                            })
        }
    ]


def hook_signals():
    def sigint_handler(signal, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)


def run_tor(clients,
            event_store: ClientEventStoreInterface,
            profile_store: ProfileStoreInterface,
            web_dir: str):
    # we'll persist events, not done automatically by nostrweb
    evt_persist = PersistEventHandler(event_store)

    # called on connect and any reconnect
    def my_connect(the_client: Client):
        # all meta updates
        the_client.subscribe(handlers=my_server, filters=get_profile_filter(the_client, event_store))

        # the max look back should be an option, maybe the default should just be everything
        # this will do for now
        since = event_store.get_newest(the_client.url)
        since = util_funcs.date_as_ticks(datetime.now()-timedelta(hours=5))
        # less_30days = util_funcs.date_as_ticks(datetime.now()-timedelta(days=30))
        # if since < less_30days:
        #     since = less_30days
        the_client.subscribe(handlers=[evt_persist, my_server], filters={
            'since': since,
            'kinds': [
                Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT,
                Event.KIND_META, Event.KIND_CONTACT_LIST
            ]
            # 'since': util_funcs.date_as_ticks(datetime.now())
        })

    # so server can send out client status messages
    def my_status(status):
        my_server.send_data([
            'relay_status', status
        ])

    # connection to the various relays
    my_client = ClientPool(clients,
                           on_connect=my_connect,
                           on_status=my_status)

    my_server = NostrWeb(file_root='%s/web/static/' % web_dir,
                         event_store=event_store,
                         profile_store=profile_store,
                         client=my_client)

    my_client.start()

    hook_signals()

    try:
        # All hidden services have a directory on disk. Lets put ours in tor's data
        # directory.

        print(' * Connecting to tor')
        controller = Controller.from_port()

        controller.authenticate()

        # All hidden services have a directory on disk. Lets put ours in tor's data
        # directory.

        hidden_service_dir = os.path.join(controller.get_conf('DataDirectory', '/tmp'), 'hello_smeg')

        # Create a hidden service where visitors of port 80 get redirected to local
        # port 5000 (this is where Flask runs by default).
        print(" * Creating our hidden service in %s" % hidden_service_dir)
        result = controller.create_hidden_service(hidden_service_dir, 80, target_port=5000)

        # The hostname is only available when we can read the hidden service
        # directory. This requires us to be running with the same user as tor.

        if result.hostname:
            print(" * Our service is available at %s, press ctrl+c to quit" % result.hostname)
        else:
            print(
                " * Unable to determine our service's hostname, probably due to being unable to read the hidden service directory")

            my_server.start(host='localhost', port=5000)



    except OSError as oe:
        print(oe)
    finally:
        if my_client:
            my_client.end()
        if my_server:
            my_server.stop()
        if controller:
            print(" * Shutting down our hidden service")
            controller.remove_hidden_service(hidden_service_dir)
            shutil.rmtree(hidden_service_dir)

def run_web(clients,
            event_store: ClientEventStoreInterface,
            profile_store: ProfileStoreInterface,
            web_dir: str):

    # we'll persist events, not done automatically by nostrweb
    evt_persist = PersistEventHandler(event_store)

    # called on connect and any reconnect
    def my_connect(the_client: Client):
        # all meta updates
        # the_client.subscribe(handlers=my_server, filters=get_profile_filter(the_client, event_store))

        # the max look back should be an option, maybe the default should just be everything
        # this will do for now
        since = event_store.get_newest(the_client.url)
        # less_30days = util_funcs.date_as_ticks(datetime.now()-timedelta(days=30))
        # if since < less_30days:
        #     since = less_30days
        the_client.subscribe(handlers=[evt_persist, my_server], filters={
            # 'since': util_funcs.date_as_ticks(datetime.now()-timedelta(hours=10)),
            'since': since,
            'kinds': [
                Event.KIND_RELAY_REC,
                Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT,
                Event.KIND_META, Event.KIND_CONTACT_LIST
            ]
        })

    my_peh = ProfileEventHandler(profile_store)

    def my_eose(the_client: Client, sub_id: str, events):
        print('eose', the_client.url)
        my_peh.do_event(sub_id, events, the_client.url)
        evt_persist.do_event(sub_id, events, the_client.url)

    # so server can send out client status messages
    def my_status(status):
        my_server.send_data([
            'relay_status', status
        ])

    # connection to the various relays
    my_client = ClientPool(clients,
                           on_connect=my_connect,
                           on_status=my_status,
                           on_eose=my_eose)

    my_server = NostrWeb(file_root='%s/web/static/' % web_dir,
                         event_store=event_store,
                         profile_handler=my_peh,
                         client=my_client)

    my_client.start()

    hook_signals()

    try:
        my_server.start(host='192.168.0.14')
    except OSError as oe:
        print(oe)
    finally:
        if my_client:
            my_client.end()
        if my_server:
            my_server.stop()


def run():
    db_file = WORK_DIR + 'nostr-client-now.db'
    db_type = 'sqlite'
    full_text = True
    is_tor = False
    web_dir = os.getcwd()

    # who to attach to
    clients = [
        {
            'client': 'wss://nostr-pub.wellorder.net',
            'write': True
        },
        'ws://localhost:8081',
        # 'ws://localhost:8083',
        {
            'client': 'wss://relay.damus.io',
            'write': True
        }
    ]


    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ht', ['help', 'sqlite-file=', 'tor'])

        # first pass
        for o, a in opts:
            pass

        # attempt interpret action
        for o, a in opts:
            if o in ('-t', '--tor'):
                is_tor = True


    except getopt.GetoptError as e:
        print(e)
        usage()

    if db_type == 'sqlite':
        util_funcs.create_sqlite_store(db_file)
        event_store = ClientSQLiteEventStore(db_file,
                                             full_text=full_text)

        # event_store = ClientMemoryEventStore()
        profile_store = SQLiteProfileStore(db_file)
        # profile_store = MemoryProfileStore()
        # profile_store.import_profiles_from_events(event_store)
        # profile_store.import_contacts_from_events(event_store)

        # from nostr.event.persist import ClientMemoryEventStore
        # event_store = ClientMemoryEventStore()


    if is_tor:
        run_tor(clients=clients,
                event_store=event_store,
                profile_store=profile_store,
                web_dir=web_dir)
    else:
        run_web(clients=clients,
                event_store=event_store,
                profile_store=profile_store,
                web_dir=web_dir)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)

    # run()
    # import re
    # def extract_tag(tag_prefix, text, with_pat=None):
    #     if with_pat is None:
    #         with_pat = '\\%s(\w*)' % tag_prefix
    #
    #
    #     matches = re.findall(with_pat, text)
    #     for c_match in matches:
    #         text = text.replace(tag_prefix + c_match, '')
    #
    #     return matches, text
    #
    # print(extract_tag('$', 'test with #hashtag $test ok cool',
    #                   with_pat='\$([\s\w]*)'))

    # my_str="👍"
    # print(my_str.encode())

    with Client('wss://relay.damus.io') as c:
        events = c.query(url='wss://relay.damus.io',
                         filters=[{
                             'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=10)),
                             'kinds': [40]
                         }])
    c_evt: Event
    from nostr.ident.profile import Profile,ValidatedProfile
    for c_evt in events:
        print(c_evt.content,c_evt.tags, c_evt.id)
        # if 'f06a690997a1b7d8283c90a7224eb8b7fe96b7c3d3d8cc7b2e7f743532c02b42' in c_evt.e_tags:
        #     print(c_evt.content)

    from nostr.client.event_handlers import EventHandler
    # is_done = False
    #
    # class my_printer(EventHandler):
    #
    #     def do_event(self, sub_id, evt: Event, relay):
    #         print(evt)
    # my_handler = my_printer()
    #
    # def my_eose(the_client: Client, sub_id: str, events: []):
    #     for c_evt in events:
    #         my_handler.do_event(sub_id, c_evt, the_client)
    #
    # def my_stuff(the_client: Client):
    #     print(the_client.relay_information)
    #
    #     the_client.subscribe(filters={
    #         'since': util_funcs.date_as_ticks(datetime.now() - timedelta(days=100))
    #     }, handlers=my_handler)
    #
    # from nostr.ident.profile import Profile
    # def my_post_test(the_client:Client):
    #     store = SQLiteProfileStore(WORK_DIR + 'nostr-client-test.db')
    #
    #     p: Profile = store.select_profiles({
    #         'profile_name': 'squizal'
    #     })[0]
    #
    #
    #     e = Event(kind=10000,
    #               content='this is a replaceable dude bad hombre 3rd!!!',
    #               pub_key=p.public_key,
    #               tags=[
    #                   ['e','5294b71fd914015d07d9fe40ae9bbcd2393cd2a1175ddaa693f55d720fbcbea9']
    #               ])
    #     e.sign(p.private_key)
    #     the_client.publish(e)
    #
    #     time.sleep(1)
    #     # the_client.end()
    #
    #
    # complete = False
    # my_store = ClientMemoryEventStore()
    # def my_eose(the_client: Client, sub_id: str, events):
    #     global complete
    #     my_store.add_event(events)
    #     my_store.relay_list()
    #     complete = True
    #
    # with Client('ws://localhost:8081', on_eose=my_eose) as c:
    #     c.subscribe(filters={
    #         'kinds': [Event.KIND_RELAY_REC]
    #     },wait_connect=True)
    #
    #     while complete is False:
    #         time.sleep(0.1)


    # pub_k = '32e1827635450ebb3c5a7d12c1f8e7b2b514439ac10a67eef3d9fd9c5c68e245'
    # from nostr.encrypt import Keys
    # print(Keys.bech32(pub_k))



    #
    # f = {
    #     'ids': []
    # }
    # dms = e_store.direct_messages('40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486')
    # for c_dm in dms:
    #     f['ids'].append(c_dm['event_id'])
    #
    # print(len(e_store.get_filter(f)))


    #
    # k1 = '32e1827635450ebb3c5a7d12c1f8e7b2b514439ac10a67eef3d9fd9c5c68e245'
    # k2 = '9ec7a778167afb1d30c4833de9322da0c08ba71a69e1911d5578d3144bb56437'
    # p = p_store.select({
    #     'pub_k': [k1, k2]
    # })
    # from nostr.ident.profile import ContactList
    # p1 = p.lookup_pub_key(k1)
    # c1 = ContactList(p1.load_contacts(p_store),owner_pub_k=p1.public_key)
    # p2 = p.lookup_pub_key(k2)
    # c2 = ContactList(p2.load_contacts(p_store), owner_pub_k=p2.public_key)
    #
    # print(len(c1))
    # print(len(c2))
    #
    # print(len(c1.diff(c2)))

