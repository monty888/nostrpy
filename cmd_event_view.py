"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileList, Contact
from nostr.ident.persist import SQLProfileStore, MemoryProfileStore, ProfileStoreInterface
from nostr.client.client import ClientPool, Client
from nostr.event.persist import ClientSQLEventStore, ClientSQLiteEventStore, ClientMemoryEventStore, ClientEventStoreInterface
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler, EventAccepter, DeduplicateAcceptor, LengthAcceptor, ProfileEventHandler
from nostr.util import util_funcs
from nostr.event.event import Event
from nostr.encrypt import Keys
from app.post import PostApp
from cmd_line.util import EventPrinter, FormattedEventPrinter

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB_FILE = '%s/nostr-client-test.db' % WORK_DIR

# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
# RELAYS = ['wss://relay.damus.io']
# RELAYS = ['ws://localhost:8081','wss://nostr-pub.wellorder.net','wss://rsslay.fiatjaf.com','wss://relay.damus.io']
# RELAYS = ['wss://nostr-pub.wellorder.net']
RELAYS = ['ws://localhost:8081']
AS_PROFILE = None
VIEW_PROFILE = None
INBOX = None
# default -24 hours from runtime
SINCE = 24

def usage():
    print("""
usage:
-h, --help                  displays this text
--as_profile                profile_name, priv_k or pub_k of user to view as. If only created from pub_k then kind 4
                            encrypted events will be left encrypted.
--view_profiles             comma seperated list of profile_name or pub_k that will be included for view
--inbox                     profile_name or priv_k of mailbox to check for CLUST wrapped messages
--since                     show events n hours previous to running - default 24
--until                     show events n hours after since    

    """)
    sys.exit(2)

def get_from_config(config,
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
        as_key = config['as_user']
        as_user = profiles.profiles.get_profile(as_key)

        if not as_user:
            if Keys.is_key(as_key):
                # just create a tmp profile using key as pub_key maybe no meta or we just didn't fetch it yet
                # (which would be case on first run because profile store would be empty)
                as_user = Profile(pub_k=as_key, attrs={
                    'name': 'adhoc from pub_k'
                })

            else:
                print('unable to find/create as_user profile - %s' % as_key)
                sys.exit(2)
        c_c: Contact
        for c_c in as_user.load_contacts(profiles.store):
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

    if as_user is not None and as_user.private_key:
        shared_keys = PostApp.get_clust_shared_keymap_for_profile(as_user, all_view)

    try:
        since = int(config['since'])
    except ValueError as e:
        print('since - %s not a numeric value' % config['since'])

    until = config['until']
    try:
        if config['until'] is not None:
            until = int(config['until'])
    except ValueError as e:
        print('until - %s not a numeric value' % config['until'])
        sys.exit(2)

    return {
        'as_user': as_user,
        'all_view': all_view,
        'view_extra': view_extra,
        'inboxes': inboxes,
        'inbox_keys': inbox_keys,
        'shared_keys': shared_keys,
        'since': since,
        'until': until
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
    event_store:ClientEventStoreInterface = None
    # event_store = ClientSQLiteEventStore(DB_FILE, full_text=True)
    # event_store = ClientMemoryEventStore()
    # my_persist = PersistEventHandler(event_store)
    profile_store = SQLProfileStore(my_db)
    # profile_store = MemoryProfileStore()
    profile_handler = ProfileEventHandler(profile_store)

    config = get_from_config(config, profile_handler)
    as_user = config['as_user']
    view_profiles = config['all_view']
    inboxes = config['inboxes']
    inbox_keys = config['inbox_keys']
    share_keys = config['shared_keys']
    since = config['since']
    until = config['until']

    def print_run_info():
        c_p: Profile
        c_c: Contact

        extra_view_profiles = config['view_extra']
        # output running info
        if as_user:
            print('events will be displayed as user %s' % as_user.display_name())
            print('--- follows ---')

            for c_c in as_user.load_contacts(profile_store):
                c_p = profile_handler.profiles.get_profile(c_c.contact_public_key)
                if c_p:
                    print(c_p.display_name())
                else:
                    print(c_c.contact_public_key)
        else:
            print('runnning without a user')

        if extra_view_profiles:
            print('--- extra profiles ---')
            for c_p in extra_view_profiles:
                print(c_p.display_name())

        if inboxes:
            print('--- checking inboxes ---')
            for c_p in inboxes:
                print(c_p.display_name())

        print('showing events from now minus %s hours' % since)
        if until:
            print('until %s hours from this point' % until)

    # show run info
    print_run_info()
    # change to since to point in time
    since = datetime.now() - timedelta(hours=since)
    # same for util if it is a value, which is taken as hours from since
    if until:
        until = util_funcs.date_as_ticks(since + timedelta(hours=until))

    # prints out the events
    my_printer = PrintEventHandler(profile_handler=profile_handler,
                                   event_acceptors=[DeduplicateAcceptor(),
                                                    LengthAcceptor(),
                                                    MyAccept(as_user=as_user,
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

    def my_eose(the_client: Client, sub_id: str, events):
        # seems mutiple filters mean we get unpredictable order from the relay
        # we probably shouldn't rely on order from relay anyhow
        def my_sort(evt:Event):
            return evt.created_at_ticks
        events.sort(key=my_sort)

        profile_handler.do_event(sub_id, events, the_client.url)
        for c_evt in events:
            my_printer.do_event(sub_id, c_evt, the_client)

    def my_connect(the_client: Client):
        # all metas and contacts ever
        p_filter = {
            'kinds': [Event.KIND_META, Event.KIND_CONTACT_LIST],
            'since': profile_store.newest
        }
        # events back to since
        e_filter = {
            # 'since': event_store.get_newest(the_client.url)+1
            'since': util_funcs.date_as_ticks(since),
            'kinds': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT]
        }
        if until:
            e_filter['until'] = until
        # note in the case of wss://rsslay.fiatjaf.com it looks like author is required to receive anything
        if the_client.url == 'wss://rsslay.fiatjaf.com':
            e_filter['authors'] = [p.public_key for p in view_profiles]

        the_client.subscribe(handlers=[profile_handler, my_printer], filters=[
            p_filter,
            e_filter
        ])

    # local_filter = {
    #     'kinds': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT, Event.KIND_META, Event.KIND_CONTACT_LIST],
    #     'since': util_funcs.date_as_ticks(since)
    # }

    # print events as we have them locally if using persistent event store
    # existing_evts = event_store.get_filter(local_filter)
    # existing_evts.reverse()
    # for c_evt in existing_evts:
    #     my_printer.do_event(None, c_evt, None)
    #     since = c_evt.created_at - timedelta(hours=1)
    my_client = ClientPool(RELAYS, on_connect=my_connect, on_eose=my_eose).start()


def run_event_view():
    config = {
        'as_user': AS_PROFILE,
        'view_profiles': VIEW_PROFILE,
        'inbox': INBOX,
        'since': SINCE,
        'until': None
    }

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h', ['help',
                                                       'as_profile=',
                                                       'view_profiles=',
                                                       'inbox=',
                                                       'since=',
                                                       'until='])

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
            if o == '--until':
                config['until'] = a

        run_watch(config)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    # logging.getLogger().setLevel(logging.DEBUG)
    util_funcs.create_work_dir(WORK_DIR)
    util_funcs.create_sqlite_store(DB_FILE)
    run_event_view()

