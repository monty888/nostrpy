"""
    starts a web server that gives access to data from a number of nostr servers
"""
import logging
import signal
import sys
import os
import time
import json

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
from nostr.settings.persist import SQLiteSettingsStore, SettingStoreInterface
from nostr.settings.handler import Settings
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
            settings_store: SettingStoreInterface,
            web_dir: str,
            host: str = 'localhost',
            port: int = 8080,
            until: int = 365,
            fill_size: int =10):

    print('events until: %s' % (datetime.now()-timedelta(days=until)).date())
    # we'll persist events, not done automatically by nostrweb
    my_spam = ContentBasedDespam()
    start_time = datetime.now()

    evt_persist = PersistEventHandler(event_store, spam_handler=my_spam)
    my_peh = ProfileEventHandler(profile_store)
    my_ceh = ChannelEventHandler(channel_store)
    my_settings = Settings(settings_store)

    # called on connect and any reconnect
    def my_connect(the_client: Client):


        the_client.subscribe(handlers=[evt_persist, my_peh, my_ceh, my_server], filters=[
            # things we're greedy for we'll get all we can of these as far back as they go
            # we start queries from the newest event we see per client/kind
            get_latest_event_filter(the_client, event_store, Event.KIND_META),
            get_latest_event_filter(the_client, event_store, Event.KIND_CONTACT_LIST),
            get_latest_event_filter(the_client, event_store, Event.KIND_CHANNEL_CREATE),
            # non greedy though we start a backfill process for these kinds starting from
            # the oldest(or resync_from) we have to until
            {
                'kinds': [Event.KIND_TEXT_NOTE,
                          Event.KIND_CHANNEL_MESSAGE,
                          Event.KIND_RELAY_REC,
                          Event.KIND_ENCRYPT,
                          Event.KIND_REACTION,
                          Event.KIND_DELETE],
                # this should be start_time or latest if that is newer
                'since': util_funcs.date_as_ticks(start_time)
            }
        ])

    def split_events(evts:[ Event]):
        """
        :param evts: [Events] to be split
        :return: {
                    'kind': [Events]
                }
        """
        c_evt: Event
        ret = {}
        for c_evt in evts:
            if c_evt.kind not in ret:
                ret[c_evt.kind] = []
            ret[c_evt.kind].append(c_evt)
        return ret

    def latest_events_only(evts: [Event], kind):
        """
        use with events where only the latest event matters for example contact, profile updates
        the relay may do this (probably should have) but just incase
        events should be sorted newest first before calling

        :param evts:
        :param kind: the kind we're interested in
        :return:
        """

        ret = []
        since_lookup = set()

        c_evt: Event
        for c_evt in evts:
            if c_evt.kind == kind and c_evt.pub_key not in since_lookup:
                since_lookup.add(c_evt.pub_key)
                ret.append(c_evt)
            elif c_evt.kind == kind:
                logging.debug('latest_events_only: ignore superceeded event %s' % c_evt)

        return ret

    def my_eose(the_client: Client, sub_id: str, events: [Event]):
        c_evt: Event
        print('eose relay %s %s events' % (the_client.url, len(events)))
        # sort events newest to oldest
        def sort_func(evt:Event):
            return evt.created_at
        events.sort(key=sort_func)

        events_by_kind = split_events(events)

        # profiles
        if Event.KIND_META in events_by_kind:
            p_events = latest_events_only(evts=events_by_kind[Event.KIND_META],
                                          kind=Event.KIND_META)
            my_peh.do_event(sub_id, p_events, the_client.url)
            evt_persist.do_event(sub_id, p_events, the_client.url)
            print('imported %s profile events from %s' % (len(p_events), the_client.url))

        # contacts
        if Event.KIND_CONTACT_LIST in events_by_kind:
            con_events = latest_events_only(evts=events_by_kind[Event.KIND_CONTACT_LIST],
                                          kind=Event.KIND_CONTACT_LIST)
            my_peh.do_event(sub_id, con_events, the_client.url)
            evt_persist.do_event(sub_id, con_events, the_client.url)
            print('imported %s contact events from %s' % (len(con_events), the_client.url))

        # channel creates
        if Event.KIND_CHANNEL_CREATE in events_by_kind:
            chn_events = latest_events_only(evts=events_by_kind[Event.KIND_CHANNEL_CREATE],
                                            kind=Event.KIND_CHANNEL_CREATE)
            my_ceh.do_event(sub_id, chn_events, the_client.url)
            evt_persist.do_event(sub_id, chn_events, the_client.url)
            print('imported %s channel create events from %s' % (len(chn_events), the_client.url))

        # and the rest - you shouldn't get many here and they'll mainly be delt with either
        # as they come in or by the back fill next
        for c_kind in [Event.KIND_TEXT_NOTE,
                       Event.KIND_CHANNEL_MESSAGE,
                       Event.KIND_RELAY_REC,
                       Event.KIND_ENCRYPT,
                       Event.KIND_REACTION,
                       Event.KIND_DELETE]:
            if c_kind in events_by_kind:
                evt_persist.do_event(sub_id, events_by_kind[c_kind], the_client.url)
                if c_kind == Event.KIND_CHANNEL_MESSAGE:
                    my_ceh.do_event(sub_id, events_by_kind[c_kind], the_client.url)

        # now we're upto date we can start the backfill/resync process
        do_backfill(the_client)

    def do_backfill(the_client: Client):
        until_dt = start_time - timedelta(days=until)

        # if we already did a backfill for this relay we should have saved the backfilled to date
        backfill_date = my_settings.get(the_client.url + '.backfilltime')
        if backfill_date:
            backfill_date = util_funcs.ticks_as_date(int(backfill_date))

        for c_kind in [Event.KIND_TEXT_NOTE,
                       Event.KIND_CHANNEL_MESSAGE,
                       Event.KIND_RELAY_REC,
                       Event.KIND_ENCRYPT,
                       Event.KIND_REACTION,
                       Event.KIND_DELETE]:

            if backfill_date:
                c_oldest = backfill_date
            else:
                # fallback look for oldest event of this kind we have, most likely this is first time though so
                # we'll get 0 in which case we start from time the server was started
                c_oldest = event_store.get_oldest(the_client.url, {
                    'kinds': [c_kind]
                })
                if c_oldest == 0:
                    c_oldest = util_funcs.date_as_ticks(start_time)
                c_oldest = util_funcs.ticks_as_date(c_oldest)

            # if we already have events <= util_date then no more import is required
            if c_oldest <= until_dt:
                print('%s no backfill required for kind: %s' % (the_client.url,
                                                                c_kind))
                continue
            else:
                print('%s backfill for kind %s starting at: %s until: %s with %s days chunks' % (the_client.url,
                                                                                                 c_kind,
                                                                                                 c_oldest,
                                                                                                 until_dt.date(),
                                                                                                 fill_size))

            for c in range(0, until, fill_size):
                c_until = c_oldest - timedelta(days=c)
                c_since = c_oldest - timedelta(days=c+fill_size)
                if c_since < until_dt:
                    c_since = until_dt

                print('%s backfilling kind %s %s - %s' % (the_client.url,
                                                          c_kind,
                                                          c_until,
                                                          c_since))
                got_chunk = False
                while not got_chunk:
                    try:
                        evts = the_client.query(filters=[
                            {
                                'kinds': [c_kind],
                                'since': util_funcs.date_as_ticks(c_since),
                                'until': util_funcs.date_as_ticks(c_until)
                            }
                        ])
                        evt_persist.do_event(None, evts, the_client.url)
                        my_ceh.do_event(None, evts, the_client.url)
                        my_peh.do_event(None, evts, the_client.url)
                        got_chunk = True
                    except Exception as e:
                        logging.debug('do_backfill: %s error fetching range %s - %s, %s' %(the_client.url,
                                                                                           c_until,
                                                                                           c_since,
                                                                                           e))
                        time.sleep(1)
                # no events assume we reached end of stored events
                # if not evts:
                #     break

                print('%s recieved %s kind %s events ' % (the_client.url,
                                                          len(evts),
                                                          c_kind))

        # store that we're backfilled to this date
        my_settings.put(the_client.url+'.backfilltime', util_funcs.date_as_ticks(until_dt))
        print('%s backfill is complete' % the_client.url)


    # so server can send out client status messages
    def my_status(status):
        my_server.send_data([
            'relay_status', status
        ])

    # connection to the various relays
    def get_clients():
        # defined from cmd line... If so maybe we should lock the ability to change relays?, as is
        # this will override the saved settings
        ret = clients

        # get saved insettings, this should exist after we run at least once
        if ret is None:
            ret = my_settings.get('relays')
            if ret:
                ret = json.loads(ret)

            if ret is None:
                # fallback first run an no relay defined... hardcoded relays
                # change this so that just relay list is pulled from hardcoded and then user has to select
                # probably this should just be flag for those that know what they're doing
                ret = ['wss://relay.damus.io',
                       'wss://nostr-pub.wellorder.net/']

        return ret


    my_client = ClientPool(clients=get_clients(),
                           on_connect=my_connect,
                           on_status=my_status,
                           on_eose=my_eose)

    my_server = NostrWeb(file_root='%s/web/static/' % web_dir,
                         event_store=event_store,
                         profile_handler=my_peh,
                         channel_handler=my_ceh,
                         settings=my_settings,
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
    util_funcs.create_work_dir(WORK_DIR)
    db_file = WORK_DIR + 'nostrpy-client-backfilltest.db'
    db_type = 'sqlite'
    full_text = True
    is_tor = False
    web_dir = os.getcwd()
    host = 'localhost'
    port = 8080
    # default fetch bac events to this data, excludes profiles, contacts, channel creates
    max_until = 365
    # backfill chunk sizes, events wll be fetched in fill_size days back until max_until
    fill_size = 10
    # backfill rescan starts from here if not supplied it starts from the oldest event/kind for each relay
    rescan_from = None
    # if given then when we reach we'll skip, we'll skip up until oldest event/kind for realy or just
    # continue on if we already passed
    rescan_to = None
    # comma seperated relays to attach to, done like this will always be read/write
    relays = None

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ht', ['help',
                                                        'db-file=',
                                                        'tor',
                                                        'host=',
                                                        'port=',
                                                        'until=',
                                                        'fillsize=',
                                                        'relay='])


        # first pass
        for o, a in opts:
            pass

        # attempt interpret action
        for o, a in opts:
            if o in ('-t', '--tor'):
                is_tor = True
            elif o == '--host':
                host = a
            elif o == '--port':
                try:
                    port = int(a)
                except ValueError as ve:
                    print('port %s not a valid value' % a)
                    sys.exit(2)
            elif o == '--db-file':
                db_file = a
                if os.path.pathsep not in db_file:
                    db_file = WORK_DIR+db_file
            elif o == '--until':
                try:
                    max_until = int(a)
                except ValueError as ve:
                    print('until %s not a valid value' % a)
                    sys.exit(2)
            elif o == '--fillsize':
                try:
                    fill_size = int(a)
                except ValueError as ve:
                    print('fillsize %s not a valid value' % a)
                    sys.exit(2)
            if o == '--relay':
                relays = a.split(',')


    except getopt.GetoptError as e:
        print(e)
        usage()

    if db_type == 'sqlite':
        util_funcs.create_sqlite_store(db_file)
        event_store = ClientSQLiteEventStore(db_file,
                                             full_text=full_text)

        profile_store = SQLiteProfileStore(db_file)
        channel_store = SQLiteSQLChannelStore(db_file)
        settings_store = SQLiteSettingsStore(db_file)


    if is_tor:
        run_tor(clients=relays,
                event_store=event_store,
                profile_store=profile_store,
                web_dir=web_dir)
    else:
        run_web(clients=relays,
                event_store=event_store,
                profile_store=profile_store,
                channel_store=channel_store,
                settings_store=settings_store,
                web_dir=web_dir,
                host=host,
                port=port,
                until=max_until,
                fill_size=fill_size)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run()


    # c = Client('wss://relay.damus.io').start()
    #
    # evts = c.query(filters=[
    #     {
    #         'kinds': [Event.KIND_TEXT_NOTE],
    #         'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=1)),
    #         'until': util_funcs.date_as_ticks(datetime.now())
    #     }
    # ])
    # print(evts)

    # my_store = ClientSQLiteEventStore(WORK_DIR + 'nostrpy-client-backfilltest.db')
    # print(my_store.get_oldest())

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


