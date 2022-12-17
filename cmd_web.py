"""
    starts a web server that gives access to data from a number of nostr servers
"""
from abc import ABC

from gevent import monkey
from gevent import Greenlet

monkey.patch_all()
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
from nostr.event.event_handlers import EventHandler, NetworkedEventHandler
from nostr.ident.profile import Profile, ContactList
from nostr.ident.persist import SQLiteProfileStore, ProfileStoreInterface, MemoryProfileStore
from nostr.ident.event_handlers import ProfileEventHandler, NetworkedProfileEventHandler
from nostr.channels.persist import SQLiteSQLChannelStore, ChannelStoreInterface
from nostr.channels.event_handlers import ChannelEventHandler, NetworkedChannelEventHandler
from nostr.settings.persist import SQLiteSettingsStore, SettingStoreInterface
from nostr.settings.handler import Settings
from nostr.util import util_funcs
from nostr.backfill.backfill import RangeBackfill, ProfileBackfiller
from web.web import NostrWeb
from nostr.spam_handlers.spam_handlers import ContentBasedDespam

# TODO: also postgres
# defaults here if no config given???
WORK_DIR = '%s/.nostrpy/' % Path.home()
DEFAULT_UNTIL = 365
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
                            event_kind,
                            on_empty: int):

    since = event_store.get_newest(for_client.url, {
        'kinds': [event_kind]
    })
    if since:
        since += 1
    else:
        since = on_empty

    return {
        'kinds': [event_kind],
        # 'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=5))
        'since': since
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
    evt_persist = EventHandler(event_store)

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


def get_until_days(settings: Settings, until):
    stored_until = settings.get('backfill.until', None)

    # user supplied a val
    if until is not None:
        # TODO: - add some stuff here, specifically if the user reduced... in future this will likely
        #  end with events getting pruned
        if stored_until:
            pass
        settings.put('backfill.until', until)
        ret = until
    # used stored val or default if never stored (first run?)
    else:
        if stored_until is None:
            stored_until = DEFAULT_UNTIL
            settings.put('backfill.until', stored_until)
        else:
            stored_until = int(stored_until)

        ret = stored_until

    return ret


def run_web(clients,
            event_store: ClientEventStoreInterface,
            profile_store: ProfileStoreInterface,
            channel_store: ChannelStoreInterface,
            settings_store: SettingStoreInterface,
            web_dir: str,
            host: str = 'localhost',
            port: int = 8080,
            until: int = None,
            until_me: int = None,
            until_follow: int = 365,
            until_follow_follow: int = 180,
            fill_size: int = 10):

    print('events until: %s' % (datetime.now()-timedelta(days=until)).date())
    # we'll persist events, not done automatically by nostrweb
    my_spam = ContentBasedDespam()
    start_time = datetime.now()
    my_settings = Settings(settings_store)
    until = get_until_days(my_settings, until)

    # called on connect and any reconnect
    def my_connect(the_client: Client):
        start_ticks = util_funcs.date_as_ticks(start_time)

        the_client.subscribe(handlers=[evt_persist, my_peh, my_ceh, my_server], filters=[
            get_latest_event_filter(the_client, event_store, Event.KIND_RELAY_REC, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_META, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_CONTACT_LIST, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_CHANNEL_CREATE, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_CHANNEL_MESSAGE, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_TEXT_NOTE, start_ticks),
            # FIXME: why get encrypts for those not to or from where we have priv_k?
            get_latest_event_filter(the_client, event_store, Event.KIND_ENCRYPT, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_REACTION, start_ticks),
            get_latest_event_filter(the_client, event_store, Event.KIND_DELETE, start_ticks)
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

    def get_my_messages(evts: [Event]):
        ret = []
        c_evt: Event
        c_p: Profile

        my_profiles = my_peh.local_profiles()
        for c_evt in evts:
            for c_p in my_profiles:
                if c_p.is_my_encrypt(c_evt):
                    ret.append(c_evt)
                    break
        return ret

    def my_do_events(the_client: Client, sub_id:str, events: [Event]):
        Event.sort(events, inplace=True)
        events_by_kind = split_events(events)

        for c_kind in events_by_kind.keys():
            kind_events = events_by_kind[c_kind]

            # we only need the latest for these kind of events, relays sometimes give us older
            if c_kind in (Event.KIND_META, Event.KIND_CONTACT_LIST):
                kind_events = Event.latest_events_only(evts=kind_events,
                                                       kind=c_kind)

            if c_kind in (Event.KIND_META, Event.KIND_CONTACT_LIST):
                my_peh.do_event(sub_id, kind_events, the_client.url)
            elif c_kind in (Event.KIND_CHANNEL_CREATE, Event.KIND_CHANNEL_MESSAGE):
                my_ceh.do_event(sub_id, kind_events, the_client.url)

            # for encrypted msgs we only keep those which we can decrypt, so either to or from
            # accounts that we have
            if c_kind == Event.KIND_ENCRYPT:
                evt_persist.do_event(sub_id, get_my_messages(kind_events), the_client.url)
            else:
                evt_persist.do_event(sub_id, kind_events, the_client.url)

            # some extra pre caching
            # for each unique public_k import the profile/contact info
            if c_kind != Event.KIND_META:
                ProfileEventHandler.import_profile_info(profile_handler=my_peh,
                                                        for_keys=list({c_evt.pub_key for c_evt in kind_events}))

            # for each channel msg import the channel meta
            if c_kind == Event.KIND_CHANNEL_MESSAGE:
                ChannelEventHandler.import_channel_info(channel_handler=my_ceh,
                                                        events=kind_events)

    def my_eose(the_client: Client, sub_id: str, events: [Event]):
        c_evt: Event
        print('eose relay %s %s events' % (the_client.url, len(events)))
        my_do_events(the_client, sub_id, events)

        # now we're upto date we can start the backfill/resync process
        RangeBackfill(client=the_client,
                      settings=my_settings,
                      start_dt=start_time,
                      until_ndays=until,
                      day_chunk=fill_size,
                      do_event=my_do_events,
                      profile_handler=my_peh).run()

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
                # ret = ['wss://relay.damus.io',
                #        'wss://nostr-pub.wellorder.net/']
                # ret = ['wss://relay.nostr.info']
                ret = ['wss://nostr.zebedee.cloud']
                # ret = ['ws://localhost:8081']

        return ret


    my_client = ClientPool(clients=get_clients(),
                           on_connect=my_connect,
                           on_status=my_status,
                           on_eose=my_eose)

    def _event_profile_prefetch(evts: [Event]):
        my_peh.get_profiles(list({c_evt.pub_key for c_evt in evts}))

    evt_persist = NetworkedEventHandler(event_store,
                                        client=my_client,
                                        spam_handler=my_spam,
                                        settings=my_settings,
                                        on_fetch=_event_profile_prefetch)
    my_peh = NetworkedProfileEventHandler(profile_store, client=my_client)
    my_ceh = NetworkedChannelEventHandler(channel_store, client=my_client)
    # my_ceh = ChannelEventHandler(channel_store)

    # def _do_profile_fill(the_client: Client, evts: [Event]):
    #     evt_persist.do_event(None, evts, the_client.url)
    #     my_peh.do_event(None, evts, the_client.url)
    #     my_ceh.do_event(None, evts, the_client.url)


        # print('channels done')

    # profile fill doesn't need to do anything in before time as it's handled by the range fill
    def p_fill_start_dt():
        return start_time - timedelta(until)

    my_profile_backfill = ProfileBackfiller(client=my_client,
                                            do_event=my_do_events,
                                            profile_handler=my_peh,
                                            settings=my_settings,
                                            start_dt=p_fill_start_dt,
                                            user_until=until_me,
                                            follow_until=until_follow,
                                            follow_follow_until=until_follow_follow,
                                            day_chunk=fill_size)

    def on_profile_update(n_profile: Profile,
                          o_profile: Profile):
        Greenlet(util_funcs.get_background_task(my_profile_backfill.profile_update, n_profile, o_profile)).start_later(0)

    def on_contact_update(p: Profile,
                          n_c: ContactList,
                          o_c: ContactList):
        pass
        # my_profile_backfill.contact_update(p, n_c, o_c)

    my_peh.set_on_profile_update(on_profile_update)
    my_peh.set_on_contact_update(on_contact_update)


    my_server = NostrWeb(file_root='%s/web/static/' % web_dir,
                         event_handler=evt_persist,
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
    db_file = WORK_DIR + 'nostrpy-client.db'
    db_type = 'sqlite'
    full_text = True
    is_tor = False
    web_dir = os.getcwd()
    host = 'localhost'
    port = 8080
    # default we'll fetch any event back to this point
    until = 365
    # backfill chunk sizes, events wll be fetched in fill_size days back until max_until
    fill_size = 90
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
                    until = int(a)
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
        event_store = ClientSQLiteEventStore(db_file, full_text=full_text)
        profile_store = SQLiteProfileStore(db_file)
        # profile_store = MemoryProfileStore()
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
                until=until,
                fill_size=fill_size)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run()

    # pstore = SQLiteProfileStore(WORK_DIR + 'nostrpy-client.db')
    # ps = pstore.select_profiles()
    # p: Profile
    #
    with ClientPool('wss://relay.nostr.info') as c:
        followers = c.query({
            'kinds': [Event.KIND_CONTACT_LIST],
            '#p': ['3efdaebb1d8923ebd99c9e7ace3b4194ab45512e2be79c1b7d68d9243e0d2681']
        })

        ufs = {ContactList.from_event(c).owner_public_key for c in followers}

        # this will timeout
        metas1 = c.query({
            'kinds': [Event.KIND_META],
            'authors': list(ufs)
        }, timeout=5)

        # this will return ok in damus
        q = []
        for k in util_funcs.chunk(list(ufs),250):
            q.append({
                'kinds': [Event.KIND_META],
                'authors': k
            })
        metas2 = c.query(q, timeout=5)
        print(len(metas1) == len(metas2))

    #
    #     from nostr.channels.persist import SQLiteSQLChannelStore
    #     my_ceh = NetworkedChannelEventHandler(SQLiteSQLChannelStore(WORK_DIR + 'nostrpy-client.db'),client=c)
    #     # my_ceh.do_event(None,evt,None)
    #
    #     print(my_ceh.get_channels('6793194b103abd9369dc831a990d3c9e94a824abd8c11dc84108bf8b7db3e27b')[0])










