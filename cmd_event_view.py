"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler, ProfileList
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.client import ClientPool, Client
from nostr.client.persist import SQLEventStore, TransientEventStore
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler
from nostr.util import util_funcs
from nostr.event import Event

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
EVENT_STORE = SQLEventStore(DB)
# EVENT_STORE = TransientEventStore()
PROFILE_STORE = SQLProfileStore(DB)
# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
# RELAYS = ['wss://nostr-pub.wellorder.net']
RELAYS = ['ws://localhost:8081','wss://nostr-pub.wellorder.net']
AS_PROFILE = None
VIEW_PROFILE = None

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

    # view as this profile, show events for public keys that this profile follows
    # only no reason that couldn't use union of multiple profiles
    if config['as_user'] is not None:
        as_user = my_profiles.profiles.get_profile(config['as_user'], create_type='public')
        if not as_user:
            print('unable to find/create as_user profile - %s' % config['as_user'])
            sys.exit(2)
        else:
            print('events will be displayed as user %s' % as_user.display_name())
            print('---follows---')
            to_view = []
            # add self - do this always?
            to_view.append(as_user.public_key)

            contacts = PROFILE_STORE.contacts().value_in('pub_k_owner',as_user.public_key)
            for c_c in contacts:
                c_p = my_profiles.profiles.get_profile(c_c['pub_k_contact'], create_type='public')
                print(c_p.display_name(with_pub=True))
                to_view.append(c_p.public_key)

    # view events from this profiles as many as you like
    if config['view_profiles']:
        vps = config['view_profiles'].split(',')
        for vp in vps:
            p = my_profiles.profiles.get_profile(vp, create_type='public')
            if not p:
                print('unable to find/create view_profile - %s' % p)
                sys.exit(2)
            else:
                if not to_view:
                    to_view = []
                print('added view for %s' % p.display_name())
                to_view.append(p.public_key)

    def my_display(sub_id, evt: Event, relay):
        p: Profile
        def make_head_str():
            ret_arr = []
            p = my_profiles.profiles.get_profile(evt.pub_key,
                                                 create_type=ProfileList.CREATE_PUBLIC)
            ret_arr.append('-- %s --' % p.display_name())

            to_list = []
            for c_pk in evt.p_tags:
                to_list.append(my_profiles.profiles.get_profile(c_pk,
                                                                create_type=ProfileList.CREATE_PUBLIC).display_name())
            if to_list:
                ret_arr.append('-> %s' % to_list)

            ret_arr.append('%s@%s' % (evt.id, evt.created_at))

            return '\n'.join(ret_arr)

        if to_view is None or evt.pub_key in to_view or as_user.public_key in evt.p_tags:
            if evt.kind in (Event.KIND_ENCRYPT, Event.KIND_TEXT_NOTE):
                # p = my_profiles.profiles.lookup_pub_key(evt.pub_key)
                # p_display = util_funcs.str_tails(evt.pub_key)
                # if p:
                #     p_display = p.display_name()
                if evt.kind == Event.KIND_TEXT_NOTE:
                    print(make_head_str())
                    print(evt.content)

                # explain this...!
                elif as_user and evt.kind == Event.KIND_ENCRYPT:
                    try:
                        # a message we sent, we our crude group send we expect theres one we can decrypt using
                        # the 0 ptag, tags 1+ are just the same mesage so we don't want to decrypt anyhow
                        if evt.pub_key == as_user.public_key:
                            content = evt.decrypted_content(as_user.private_key, evt.p_tags[0])
                        # message to us
                        else:
                            content = evt.decrypted_content(as_user.private_key, evt.pub_key)
                        print(make_head_str())
                        print(content)
                    except Exception as e:
                        pass

    # attach are own display func
    my_print.display_func = my_display

    def my_connect(the_client: Client):
        client_filter = {
            'since': EVENT_STORE.get_newest(the_client.url)+1
        }
        the_client.subscribe(handlers=[my_persist, my_profiles, my_print],
                             filters=client_filter
                             )

    # note in the case of wss://rsslay.fiatjaf.com it looks like author is required to recieve anything
    view_filter = {
        'kinds': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT, Event.KIND_META, Event.KIND_CONTACT_LIST],
        'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=1))
    }

    # if to_view:
    #     view_filter['authors'] = to_view

    existing_evts = EVENT_STORE.get_filter(view_filter)
    existing_evts.reverse()
    for c_evt in existing_evts:
        my_display(None, c_evt, None)

    my_client = ClientPool(RELAYS, on_connect=my_connect).start()


def event_view():
    config = {
        'as_user': AS_PROFILE,
        'view_profiles': VIEW_PROFILE
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
            if o == '--view_profiles':
                config['view_profiles'] = a

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
    #
    #
    # my_client = Client('wss://rsslay.fiatjaf.com', on_connect=my_connect).start()