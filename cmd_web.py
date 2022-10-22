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
from nostr.event.persist import ClientSQLiteEventStore, ClientEventStoreInterface
from nostr.event.event import Event
from nostr.event.event_handlers import PersistEventHandler
from nostr.ident.persist import SQLiteProfileStore, ProfileStoreInterface, MemoryProfileStore
from nostr.ident.event_handlers import ProfileEventHandler
from nostr.channels.persist import SQLiteSQLChannelStore, ChannelStoreInterface
from nostr.channels.event_handlers import ChannelEventHandler
from nostr.util import util_funcs
from web.web import NostrWeb
from nostr.spam_handlers.spam_handlers import ContentBasedDespam

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

def get_latest_event_filter(for_client: Client,
                            event_store: ClientEventStoreInterface,
                            event_kind):
    return {
        'kinds': [event_kind],
        # 'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=5))
        'since': event_store.get_newest(for_client.url, {
            'kinds': [event_kind]
        })+1
    }


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
            channel_store: ChannelStoreInterface,
            web_dir: str,
            host: str = 'localhost',
            port: int = 8080):

    # we'll persist events, not done automatically by nostrweb
    my_spam = ContentBasedDespam()

    evt_persist = PersistEventHandler(event_store, spam_handler=my_spam)
    my_peh = ProfileEventHandler(profile_store)
    my_ceh = ChannelEventHandler(channel_store)

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

        the_client.subscribe(handlers=[evt_persist, my_peh, my_ceh, my_server], filters=[
            get_latest_event_filter(the_client, event_store, Event.KIND_REACTION),
            get_latest_event_filter(the_client, event_store, Event.KIND_DELETE),
            get_latest_event_filter(the_client, event_store, Event.KIND_TEXT_NOTE),
            get_latest_event_filter(the_client, event_store, Event.KIND_ENCRYPT),
            get_latest_event_filter(the_client, event_store, Event.KIND_RELAY_REC)
        ])

        the_client.subscribe(handlers=[evt_persist, my_peh, my_server], filters=[
            get_latest_event_filter(the_client, event_store, Event.KIND_META),
            get_latest_event_filter(the_client, event_store, Event.KIND_CONTACT_LIST)
        ])

        the_client.subscribe(handlers=[evt_persist, my_ceh, my_server], filters=[
            get_latest_event_filter(the_client, event_store, Event.KIND_CHANNEL_CREATE),
            get_latest_event_filter(the_client, event_store, Event.KIND_CHANNEL_MESSAGE)
        ])



    def my_eose(the_client: Client, sub_id: str, events):
        print('eose', the_client.url)
        my_peh.do_event(sub_id, events, the_client.url)
        print('peh complete', the_client.url)
        my_ceh.do_event(sub_id, events, the_client.url)
        print('ceh complete', the_client.url)
        evt_persist.do_event(sub_id, events, the_client.url)
        print('evt complete', the_client.url)


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
                         channel_handler=my_ceh,
                         spam_handler=my_spam,
                         client=my_client)

    my_client.start()

    hook_signals()

    try:
        my_server.start(host=host, port=port)
    except OSError as oe:
        print(oe)
    finally:
        if my_client:
            my_client.end()
        if my_server:
            my_server.stop()


def run():
    db_file = WORK_DIR + 'nostrpy-client.db'
    db_type = 'sqlite'
    full_text = True
    is_tor = False
    web_dir = os.getcwd()
    host = 'localhost'
    port = 8080

    # who to attach to
    clients = [
        {
            'client': 'wss://nostr-pub.wellorder.net',
            'write': True
        },
        'ws://localhost:8081',
        # # # # 'ws://localhost:8083',
        {
            'client': 'wss://relay.damus.io',
            'write': True
        }
    ]


    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ht', ['help', 'db-file=', 'tor','host=','port='])


        # first pass
        for o, a in opts:
            pass

        # attempt interpret action
        for o, a in opts:
            if o in ('-t', '--tor'):
                is_tor = True
            if o == '--host':
                host = a
            if o == '--port':
                try:
                    port = int(a)
                except ValueError as ve:
                    print('port %s not a valid value' % a)
                    sys.exit(2)
            if o == '--db-file':
                db_file = a
                if os.path.pathsep not in db_file:
                    db_file = WORK_DIR+db_file

    except getopt.GetoptError as e:
        print(e)
        usage()

    if db_type == 'sqlite':
        util_funcs.create_sqlite_store(db_file)
        event_store = ClientSQLiteEventStore(db_file,
                                             full_text=full_text)

        # event_store = ClientMemoryEventStore()
        profile_store = SQLiteProfileStore(db_file)
        channel_store = SQLiteSQLChannelStore(db_file)
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
                channel_store=channel_store,
                web_dir=web_dir,
                host=host,
                port=port)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    run()

    # from nostr.channels.persist import SQLiteSQLChannelStore
    #
    # c_s = SQLiteSQLChannelStore(db_file=WORK_DIR + 'nostrpy-client.db')
    # print(c_s.select(limit=10, until=1666147754))
    # from nostr.spam_handlers.spam_handlers import ContentBasedDespam
    # e_s = ClientSQLiteEventStore( WORK_DIR + 'nostrpy-client.db')
    # e_data = e_s.get_filter({
    #     'ids': '8de658c8d7c18a19fec24a07bafab7fe190a15349b73133d626809ff7f796daa'
    # })[0]
    #
    # my_spam = ContentBasedDespam()
    # test_e = Event.from_JSON(e_data)
    # print(my_spam.is_spam(test_e))

    #
    # parts = ''.split(' ')
    # if len(parts) <= 1:
    #     if parts[0] == '' or len(parts[0]) > 10 and not parts[0].startswith('http:'):
    #         print('potential spam')
    #
    # print('>',''.split(' '))


