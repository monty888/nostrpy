"""
    starts a web server that gives access to data from a number of nostr servers
"""
import logging
import signal
import sys
import os
from stem.control import Controller
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import getopt
from nostr.client.client import ClientPool, Client
from nostr.client.event_handlers import PersistEventHandler
from nostr.event.persist import ClientSQLEventStore, Event, ClientSQLiteEventStore, ClientEventStoreInterface
from nostr.ident.persist import SQLiteProfileStore, ProfileStoreInterface
from nostr.ident.profile import ProfileEventHandler
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
                                                'kinds': Event.KIND_META}
                                            )
        },
        {
            'kinds': Event.KIND_CONTACT_LIST,
            'since': event_store.get_newest(for_client.url,
                                            {
                                                'kinds': Event.KIND_CONTACT_LIST}
                                            )
        }
    ]


def hook_signals():
    def sigint_handler(signal, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)


def run_tor(clients,
            event_store: ClientEventStoreInterface,
            profile_store: ProfileStoreInterface):
    # we'll persist events, not done automatically by nostrweb
    evt_persist = PersistEventHandler(event_store)

    # called on connect and any reconnect
    def my_connect(the_client: Client):
        # all meta updates
        the_client.subscribe(handlers=my_server, filters=get_profile_filter(the_client, event_store))

        # the max look back should be an option, maybe the default should just be everything
        # this will do for now
        since = event_store.get_newest(the_client.url)
        # less_30days = util_funcs.date_as_ticks(datetime.now()-timedelta(days=30))
        # if since < less_30days:
        #     since = less_30days
        the_client.subscribe(handlers=[evt_persist, my_server], filters={
            'since': since
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

    my_server = NostrWeb(file_root='%s/PycharmProjects/nostrpy/web/static/' % Path.home(),
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
            profile_store: ProfileStoreInterface):

    # we'll persist events, not done automatically by nostrweb
    evt_persist = PersistEventHandler(event_store)

    # called on connect and any reconnect
    def my_connect(the_client: Client):
        # all meta updates
        the_client.subscribe(handlers=my_server, filters=get_profile_filter(the_client, event_store))

        # the max look back should be an option, maybe the default should just be everything
        # this will do for now
        since = event_store.get_newest(the_client.url)
        # less_30days = util_funcs.date_as_ticks(datetime.now()-timedelta(days=30))
        # if since < less_30days:
        #     since = less_30days
        the_client.subscribe(handlers=[evt_persist, my_server], filters={
            'since': since
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

    my_server = NostrWeb(file_root='%s/PycharmProjects/nostrpy/web/static/' % Path.home(),
                         event_store=event_store,
                         profile_store=profile_store,
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
    db_file = WORK_DIR + 'nostr-client-test.db'
    db_type = 'sqlite'
    full_text = True
    is_tor = False

    # who to attach to
    clients = [
        {
            'client': 'wss://nostr-pub.wellorder.net',
            'write': True
        },
        'ws://localhost:8081',
        'ws://localhost:8082',
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
        profile_store = SQLiteProfileStore(db_file)

    if is_tor:
        run_tor(clients=clients,
                event_store=event_store,
                profile_store=profile_store)
    else:
        run_web(clients=clients,
                event_store=event_store,
                profile_store=profile_store)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run()

