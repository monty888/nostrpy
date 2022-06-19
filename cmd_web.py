"""
    starts a web server that gives access to data from a number of nostr servers
"""
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
import getopt
from nostr.client.client import ClientPool, Client
from nostr.client.event_handlers import PersistEventHandler
from nostr.event.persist import ClientSQLEventStore, Event
from nostr.ident.persist import SQLiteProfileStore
from nostr.util import util_funcs
from web.web import NostrWeb
import beaker.middleware

# TODO: also postgres
# defaults here if no config given???
# WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
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


def run_web():
    # db location
    nostr_db_file = '%s/.nostrpy/nostr-client.db' % Path.home()

    # event storage, default sqllite (the only one fully working...)
    event_store = util_funcs.create_sqlite_store(nostr_db_file,
                                                 full_text=True)
    evt_persist = PersistEventHandler(event_store)

    # profile storage default also sqllite
    profile_store = SQLiteProfileStore(nostr_db_file)

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
        opts, args = getopt.getopt(sys.argv[1:], 'h', ['help'])

        # first pass
        for o, a in opts:
            pass

        # attempt interpret action
        for o, a in opts:
            pass

        # called on connect and any reconnect
        def my_connect(the_client: Client):
            # all meta updates
            the_client.subscribe(handlers=my_server, filters={
                'kinds': Event.KIND_META,
                'since': event_store.get_newest(the_client.url, {
                    'kinds': Event.KIND_META
                })
            })

            # the max look back should be an option, maybe the default should just be everything
            # this will do for now
            since = util_funcs.date_as_ticks(event_store.get_newest(the_client.url))
            less_30days = util_funcs.date_as_ticks(datetime.now()-timedelta(days=30))
            if since < less_30days:
                since = less_30days

            the_client.subscribe(handlers=[evt_persist, my_server], filters={
                'since': since
                # 'since': util_funcs.date_as_ticks(datetime.now())
            })

        # so server cna send out client status messages
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

        # example clean exit... need to look into more though

        def sigint_handler(signal, frame):
            my_client.end()
            my_server.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, sigint_handler)
        # my_server.start(host='localhost')

        # set up the session middleware, we're not using this at the moment but expect we will
        session_opts = {
            'session.type': 'file',
            'session.cookie_expires': 300,
            'session.data_dir': './data',
            'session.auto': True
        }
        my_server.app = beaker.middleware.SessionMiddleware(my_server.app, session_opts)

        my_server.start(host='localhost')


    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_web()

