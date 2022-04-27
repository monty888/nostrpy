"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
from pathlib import Path
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.client import ClientPool, Client
from nostr.client.persist import SQLEventStore
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler
from nostr.util import util_funcs
from nostr.event import Event

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
EVENT_STORE = SQLEventStore(DB)
PROFILE_STORE = SQLProfileStore(DB)
RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
AS_PROFILE = None

def usage():
    print("""
usage:



    """)
    sys.exit(2)


def run_watch(config):
    my_print = PrintEventHandler()
    my_persist = PersistEventHandler(EVENT_STORE)
    my_profiles = ProfileEventHandler(PROFILE_STORE)
    to_view = None

    if config['as_user'] is not None:
        as_user = my_profiles.profiles.get_profile(config['as_user'], create_type='public')
        if not as_user:
            print('unable to find/create as_user profile - %s' % config['as_user'])
            sys.exit(2)
        else:
            print('events will be displayed as user %s' % as_user.display_name())
            print('---follows---')
            to_view = []
            contacts = PROFILE_STORE.contacts().value_in('pub_k_owner',as_user.public_key)
            for c_c in contacts:
                c_p = my_profiles.profiles.get_profile(c_c['pub_k_contact'], create_type='public')
                print(c_p.display_name(with_pub=True))
                to_view.append(c_p.public_key)

    def my_display(sub_id, evt: Event, relay):
        p: Profile
        if (to_view is None or evt.pub_key in to_view) \
                and evt.kind == evt.KIND_TEXT_NOTE:
            p = my_profiles.profiles.lookup_pub_key(evt.pub_key)
            p_display = util_funcs.str_tails(evt.pub_key)
            if p:
                p_display = p.display_name()

            print('-- %s --' % p_display)
            print('%s@%s' % (evt.id, evt.created_at))
            if evt.kind == Event.KIND_TEXT_NOTE:
                print(evt.content)

    # attach are own display func
    my_print.display_func = my_display
    my_filter = {
        'kinds': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT, Event.KIND_META, Event.KIND_CONTACT_LIST]
    }

    # note in the case of wss://rsslay.fiatjaf.com it looks like author is required to recieve anything
    if to_view:
        my_filter['authors'] = to_view

    def my_connect(the_client: Client):
        the_client.subscribe(handlers=[my_print, my_profiles, my_persist],
                             filters=my_filter
                             )

    my_client = ClientPool(RELAYS, on_connect=my_connect).start()


def event_view():
    config = {
        'as_user': AS_PROFILE
    }

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h', ['help',
                                                       'as_profile=',
                                                       'view_profiles='])

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            if o == '--as_profile':
                config['as_user'] = a


        run_watch(config)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    event_view()

    # def my_connect(the_client: Client):
    #     print('connect')
    #     the_client.subscribe(handlers=[PrintEventHandler()], filters={
    #         'kinds': [1],
    #         'authors': ['0a6a0b8d3c024faa8c5b944dbcd88173fd0978a57700be17e681f6ee572205ec']
    #     })


    # my_client = Client('wss://rsslay.fiatjaf.com', on_connect=my_connect).start()