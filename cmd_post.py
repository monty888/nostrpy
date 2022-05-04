"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler, ProfileList
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.client import ClientPool, Client
from nostr.client.persist import SQLEventStore, TransientEventStore
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler
from nostr.encrypt import SharedEncrypt
from nostr.util import util_funcs
from nostr.event import Event
from cmd_line.post_loop_app import PostApp, PostAppGui

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
EVENT_STORE = SQLEventStore(DB)
# EVENT_STORE = TransientEventStore()
PROFILE_STORE = SQLProfileStore(DB)
# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
RELAYS = ['ws://localhost:8081']


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


def inbox_unwrap(evt: Event,
                 as_user: Profile,
                 public_inbox: Profile):

    evt.content = evt.decrypted_content(public_inbox.private_key, as_user.public_key)
    return Event.create_from_JSON(json.loads(evt.content))


def do_post(the_client: Client,
            post_app: PostApp,
            msg):

    is_done = False

    def my_connect(the_client: Client):
        nonlocal is_done
        post_app.do_post(msg)
        is_done = True

    the_client.set_on_connect(my_connect)
    the_client.start()

    while not is_done:
        time.sleep(0.2)

    the_client.end()


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
                                                                       'relay='
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

        my_client = ClientPool(RELAYS)
        my_post = PostApp(
            use_relay=my_client,
            as_user=as_user,
            to_users=to_users,
            is_encrypt=is_encrypt,
            subject=subject,
            public_inbox=public_inbox
        )
        if is_loop:
            if PROFILE_STORE is not None:
                peh = ProfileEventHandler(PROFILE_STORE)

            my_gui = PostAppGui(my_post,
                                profile_handler=peh)

            def my_connect(the_client: Client):
                the_client.subscribe(filters={
                    'since': util_funcs.date_as_ticks(datetime.now() - timedelta(hours=1))
                }, handlers=[my_post, peh])

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
                do_post(the_client=my_client,
                        post_app=my_post,
                        msg=msg)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_post()


