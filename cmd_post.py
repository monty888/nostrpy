"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler, ProfileList
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.client import ClientPool, Client
# from nostr.client.persist import SQLEventStore, TransientEventStore
from nostr.event.persist import ClientSQLEventStore, ClientMemoryEventStore
from nostr.client.event_handlers import PersistEventHandler
from nostr.event.event import Event
from app.post import PostApp
from cmd_line.post_loop_app import PostAppGui
from nostr.util import util_funcs

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client-test.db' % WORK_DIR)
EVENT_STORE = ClientSQLEventStore(DB)
# EVENT_STORE = TransientEventStore()
PROFILE_STORE = SQLProfileStore(DB)
# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
RELAYS = ['ws://localhost:8081']
# RELAYS = ['ws://localhost:8081','ws://localhost:8082']
# RELAYS = ['wss://nostr-pub.wellorder.net']


def usage():
    print("""
usage:

    """)
    sys.exit(2)


def _get_profile(key, peh, err_str):
    ret = peh.profiles.get_profile(key,
                                   create_type=ProfileList.CREATE_PRIVATE)
    if not ret:
        print(err_str)

    return ret


def do_post(client: Client,
            post_app: PostApp,
            msg):

    client.start()
    while not post_app.connection_status:
        time.sleep(0.2)
    post_app.do_post(msg)
    client.end()


def show_post_info(as_user: Profile,
                   msg, to_users, is_encrypt, subject,
                   public_inbox: Profile):
    if msg is None:
        msg = '<no msg supplied>'
    just = 10
    print('from:'.rjust(just), as_user.display_name())
    if to_users:
        p: Profile
        print('to:'.rjust(just), [p.display_name() for p in to_users])
    if public_inbox:
        print('via:'.rjust(just), public_inbox.display_name())

    if subject:
        print('subject:'.rjust(just), subject)

    enc_text = 'encrypted'
    if not is_encrypt:
        enc_text = 'plain_text'
    print('format:'.rjust(just), enc_text)

    print('%s\n%s\n%s' % (''.join(['-'] * 10),
                          msg,
                          ''.join(['-'] * 10)))


def run_post():
    relays = RELAYS
    as_user = None
    is_encrypt = True
    ignore_missing = False
    is_loop = False
    subject = None
    peh = ProfileEventHandler(PROFILE_STORE)
    to_users = []
    public_inbox = None

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ha:t:piles:r:e:v:', ['help',
                                                                       'relay=',
                                                                       'as_profile=',
                                                                       'plain_text',
                                                                       'to=',
                                                                       'via=',
                                                                       'ignore_missing',
                                                                       'loop',
                                                                       'subject=',
                                                                       'event='])

        for o, a in opts:
            if o in ('-i', '--ignore_missing'):
                ignore_missing = True
            if o in ('-e','--event'):
                the_event = EVENT_STORE.get_filter({
                    'ids' : [a]
                })
                if not the_event:
                    print('no event found %s' % a)
                    sys.exit(2)
                else:
                    to_users.append(peh.profiles.get_profile(the_event[0].pub_key,
                                                             create_type=ProfileList.CREATE_PUBLIC))
                    for c_pk in the_event[0].p_tags:
                        to_users.append(peh.profiles.get_profile(c_pk,
                                                                 create_type=ProfileList.CREATE_PUBLIC))

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            elif o in ('-r', '--relay'):
                relays = a.split(',')
            elif o in ('-a', '--as_profile'):
                as_user = _get_profile(a, peh, '--as_profile %s not found' % a)
                if to_users:
                    if as_user in to_users:
                        to_users.remove(as_user)
            elif o in ('-p', '--plain_text'):
                is_encrypt = False
            elif o in ('-t', '--to'):
                for c_t in a.split(','):
                    to_add = _get_profile(c_t, peh, 'to profile %s not found' % c_t)
                    if to_add:
                        to_users.append(to_add)
                    elif not ignore_missing:
                        print('to profile missing and ignore_missing not set')
                        sys.exit(2)
            elif o in ('-v', '--via'):
                public_inbox = _get_profile(a, peh, 'via public_inbox %s not found' % a)
                if public_inbox is None:
                    print('via public inbox but it couldn\'t be created bad private key or unknown profile?')
                    sys.exit(2)

            elif o in ('-s', '--s'):
                subject = a
            elif o in ('-l', '--loop'):
                is_loop = True

        if not as_user and len(args) > 0:
            a = args.pop(0)
            as_user = _get_profile(a, peh, 'args[] %s not found' % a)

        if not as_user:
            print('no profile to post as supplied or unable to find')
            sys.exit(2)

        if not to_users and is_encrypt:
            print('to users must be defined for encrypted posts')
            sys.exit(2)

        msg = None
        if len(args) > 0:
            msg = ' '.join(args)

        my_client = ClientPool(relays)
        my_post = PostApp(
            use_relay=my_client,
            as_user=as_user,
            to_users=to_users,
            is_encrypt=is_encrypt,
            subject=subject,
            public_inbox=public_inbox
        )
        if is_loop:
            # for profile lookup
            persist_profile = ProfileEventHandler(PROFILE_STORE)

            # pre load local events
            local_events = EVENT_STORE.get_filter({
                'kind': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT],
                'since': util_funcs.date_as_ticks(datetime.now() - timedelta(days=10))
            })
            local_events.reverse()

            for c_evt in local_events:
                my_post.do_event(None, c_evt, None)
            persist_event = PersistEventHandler(EVENT_STORE)


            my_gui = PostAppGui(my_post,
                                profile_handler=persist_profile)

            def my_connect(the_client: Client):
                the_client.subscribe(filters={
                    'kind': [Event.KIND_META]
                }, handlers=[persist_profile])

                the_client.subscribe(filters={
                    # rem'd as if we're persisting locally it's best just to get everything else we're more likely
                    # to end up with gaps
                    # 'kind': [Event.KIND_TEXT_NOTE, Event.KIND_ENCRYPT],
                    'since': EVENT_STORE.get_newest(the_client.url)+1
                }, handlers=[my_post, persist_event])

            con_status = my_client.connected

            def on_status(status):
                nonlocal con_status
                if con_status != status['connected']:
                    con_status = status['connected']
                    my_gui.draw_messages()


            my_client.set_on_connect(my_connect)
            my_client.set_status_listener(on_status)
            my_client.start()
            my_gui.run()
            my_client.end()

            # my_post.run()
        else:
            if msg is None:
                print('no message supplied!!!')
                sys.exit(2)
            else:
                show_post_info(as_user, msg, to_users, is_encrypt, subject, public_inbox)
                do_post(client=my_client,
                        post_app=my_post,
                        msg=msg)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_post()

