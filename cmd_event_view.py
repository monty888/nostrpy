"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler, ProfileList, Contact
from nostr.ident.persist import SQLProfileStore, TransientProfileStore, ProfileStoreInterface
from nostr.client.client import ClientPool, Client
from nostr.event.persist import ClientSQLEventStore
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler, EventAccepter, DeduplicateAcceptor
from nostr.util import util_funcs
from nostr.event.event import Event
from app.post import PostApp
from cmd_line.util import EventPrinter, FormattedEventPrinter

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB_FILE = '%s/nostr-client.db' % WORK_DIR

# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
# RELAYS = ['wss://nostr-pub.wellorder.net']
RELAYS = ['ws://localhost:8081','wss://nostr-pub.wellorder.net','wss://rsslay.fiatjaf.com','wss://relay.damus.io']

# defaults if not provided at command line or from config file
# RELAYS = ['ws://localhost:8081']
AS_PROFILE = None
VIEW_PROFILE = None
INBOX = None
# default -24 hours from runtime
SINCE = 24

def usage():
    print("""
usage:



    """)
    sys.exit(2)

def get_from_config(config,
                    profile_store : ProfileStoreInterface,
                    profiles: ProfileEventHandler):
    as_user = None
    all_view = []
    view_extra = []
    inboxes = []
    inbox_keys = []
    shared_keys = []

    # the profile we'll be viewing as, if any... If it's not set then you'll see everything unless
    # you specify view_profiles.
    # in either case without as_user it's not possible to decrypt any evts
    if config['as_user'] is not None:
        as_user = profiles.profiles.get_profile(config['as_user'], create_type='public')
        if not as_user:
            print('unable to find/create as_user profile - %s' % config['as_user'])
            sys.exit(2)
        c_c: Contact
        for c_c in as_user.load_contacts(profile_store):
            all_view.append(profiles.profiles.get_profile(c_c.contact_public_key,
                                                          create_type=ProfileList.CREATE_PUBLIC))

    # view events from this profiles as many as you like
    if config['view_profiles']:
        vps = config['view_profiles'].split(',')
        for vp in vps:
            p = profiles.profiles.get_profile(vp, create_type='public')
            if not p:
                print('unable to find/create view_profile - %s' % vp)
                sys.exit(2)
            else:
                all_view.append(p)
                view_extra.append(p)

    # public inboxes for encrypted messages
    if config['inbox']:
        if as_user is None:
            print('inbox can only be used with as_user set')
            sys.exit(2)

        for c_box in config['inbox'].split(','):
            p = profiles.profiles.get_profile(c_box,
                                              create_type=ProfileList.CREATE_PRIVATE)
            if not p:
                print('unable to find/create inbox_profile - %s' % c_box)
                sys.exit(2)
            else:
                inboxes.append(p)
                inbox_keys.append(p.public_key)

    if as_user is not None:
        shared_keys = PostApp.get_clust_shared_keymap_for_profile(as_user, all_view)

    try:
        since = int(config['since'])
    except ValueError as e:
        print('since - %s not a numeric value' % config['since'])

    return {
        'as_user': as_user,
        'all_view': all_view,
        'view_extra': view_extra,
        'inboxes': inboxes,
        'inbox_keys': inbox_keys,
        'shared_keys': shared_keys,
        'since': since
    }


class MyAccept(EventAccepter):

    def __init__(self,
                 as_user: Profile = None,
                 view_profiles: [Profile] = None,
                 public_inboxes: [Profile] = None,
                 since=None):

        self._as_user = as_user
        self._view_profiles = view_profiles
        self._inboxes = public_inboxes

        self._view_keys = []
        self._make_view_keys()
        self._since = since

    def _make_view_keys(self):
        c_c: Contact
        c_p: Profile

        if self._as_user is not None:
            self._view_keys.append(self._as_user.public_key)
            self._view_keys = self._view_keys + [c_c.contact_public_key for c_c in self._as_user.contacts]

        if self._view_profiles is not None:
            self._view_keys = self._view_keys + [c_p.public_key for c_p in self._view_profiles]

        if self._inboxes is not None:
            self._view_keys = self._view_keys + [c_p.public_key for c_p in self._inboxes]

    def accept_event(self, evt: Event) -> bool:
        if self._since is not None and evt.created_at < self._since:
            return False

        # for now we'll just deal with these, though there's no reason why we couldn't show details
        # for meta or contact events and possibly others
        if evt.kind not in (Event.KIND_ENCRYPT, Event.KIND_TEXT_NOTE):
            return False

        # no specific view so all events
        if not self._view_keys:
            return True
        else:
            return evt.pub_key in self._view_keys or \
                   self._as_user is not None and \
                   (self._as_user.public_key in evt.pub_key or self._as_user.public_key in evt.p_tags)


def run_watch(config):
    my_db = SQLiteDatabase(DB_FILE)
    event_store = ClientSQLEventStore(my_db)
    my_persist = PersistEventHandler(event_store)
    profile_store = SQLProfileStore(my_db)
    profile_handler = ProfileEventHandler(profile_store)

    config = get_from_config(config, profile_store, profile_handler)
    as_user = config['as_user']
    view_profiles = config['all_view']
    inboxes = config['inboxes']
    inbox_keys = config['inbox_keys']
    share_keys = config['shared_keys']
    since = config['since']

    def print_run_info():
        extra_view_profiles = config['view_extra']
        # output running info
        if as_user:
            print('events will be displayed as user %s' % as_user.display_name())
            print('--- follows ---')
            c_c: Contact
            for c_c in as_user.load_contacts(profile_store):
                print(profile_handler.profiles.get_profile(c_c.contact_public_key).display_name())
        else:
            print('runnning without a user')

        c_p: Profile
        if extra_view_profiles:
            print('--- extra profiles ---')
            for c_p in extra_view_profiles:
                print(c_p.display_name())

        if inboxes:
            print('--- checking inboxes ---')
            for c_p in inboxes:
                print(c_p.display_name())

        print('showing events from now minus %s hours' % since)

    # show run info
    print_run_info()
    # change to since to point in time
    since = datetime.now() - timedelta(hours=since)

    # prints out the events
    my_printer = PrintEventHandler(profile_handler=profile_handler,
                                   event_acceptors=[DeduplicateAcceptor(), MyAccept(as_user=as_user,
                                                                                    view_profiles=view_profiles,
                                                                                    public_inboxes=inboxes,
                                                                                    since=since)])
    # we'll attach our own evt printer rather than basic 1 liner of PrintEventHandler
    my_print = FormattedEventPrinter(profile_handler=profile_handler,
                                     as_user=as_user,
                                     inbox_keys=inbox_keys,
                                     share_keys=share_keys)

    def my_display(sub_id, evt: Event, relay):
        my_print.print_event(evt)

    my_printer.display_func = my_display

    def my_connect(the_client: Client):
        # all metas and contacts ever
        the_client.subscribe(handlers=[profile_handler], filters={
            'kind': [Event.KIND_META, Event.KIND_CONTACT_LIST]
        })

        # get events from newest we have for this relay
        # TODO: add kind to get_newest
        evt_filter = {
            'since': event_store.get_newest(the_client.url)+1
        }

        # note in the case of wss://rsslay.fiatjaf.com it looks like author is required to receive anything
        if the_client.url == 'wss://rsslay.fiatjaf.com':
            evt_filter['authors'] = [p.public_key for p in view_profiles]

        the_client.subscribe(handlers=[my_persist, my_printer],
                             filters=evt_filter)

    local_filter = {
        'kinds': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT, Event.KIND_META, Event.KIND_CONTACT_LIST],
        'since': util_funcs.date_as_ticks(since)
    }

    existing_evts = event_store.get_filter(local_filter)
    existing_evts.reverse()
    for c_evt in existing_evts:
        my_printer.do_event(None, c_evt, None)

    my_client = ClientPool(RELAYS, on_connect=my_connect).start()


def run_event_view():
    config = {
        'as_user': AS_PROFILE,
        'view_profiles': VIEW_PROFILE,
        'inbox': INBOX,
        'since': SINCE
    }

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h', ['help',
                                                       'as_profile=',
                                                       'view_profiles=',
                                                       'inbox=',
                                                       'since='])

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            if o == '--as_profile':
                config['as_user'] = a
            if o == '--view_profiles':
                config['view_profiles'] = a
            if o == '--inbox':
                config['inbox'] = a
            if o == '--since':
                config['since'] = a

        run_watch(config)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    util_funcs.create_work_dir(WORK_DIR)
    util_funcs.create_sqlite_store(DB_FILE)
    run_event_view()
    # from nostr.event.persist import ClientSQLiteEventStore
    # my_store = ClientSQLiteEventStore(DB_FILE)
    #
    # evts = my_store.get_filter({
    #     'ids' : ['e7cd845b72ecea0e409a22526c273982b5db3c724259152c80c704781b0515ae']
    # })
    # print(len(evts))

    # from nostr.event.persist import ClientSQLEventStore
    #
    #
    #
    #
    # event_store = ClientSQLEventStore(SQLiteDatabase(WORK_DIR + '/nostr-client.db'))
    #
    # print(event_store.get_newest(for_relay='wss://nostr-pub.wellorder.net',
    #                              filter={
    #                                  'kinds': Event.KIND_META
    #                              }))


    #
    #
    #
    # evts = event_store.get_filter([
    #     {
    #     }
    # ])
    #
    #
    # evt = Event(kind=Event.KIND_TEXT_NOTE,
    #             content='monkey',
    #             pub_key='40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486')
    # evt.sign('5c7102135378a5223d74ce95f11331a8282ea54905d61018c7f1bc166994a1d9')
    # # event_store.add_event(evt)
    # e = evts[0]
    # event_store.add_event_relay(e, 'shauns relay')




    # profile_store = SQLProfileStore(SQLiteDatabase(DB_FILE))
    # evts = event_store.get_filter({
    #     'ids' : ['d56320fbfa274944f8a95a935eb4d83b4ca0c5ca3421761905b827fbfed9b23d']
    # })
    #
    # as_user:Profile = profile_store.select({
    #     'profile_name': 'firedragon888'
    # })[0]
    #
    # evt = Event(kind=Event.KIND_ENCRYPT,
    #             content='1234567890123456',
    #             pub_key=as_user.public_key)
    # evt.content = evt.encrypt_content(as_user.private_key, as_user.public_key)
    # evt.sign(as_user.private_key)
    #
    # evt.content = evt.decrypted_content(as_user.private_key, as_user.public_key)
    # print('>>>>',evt.content)
