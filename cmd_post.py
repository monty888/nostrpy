"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
import time
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
RELAYS = ['wss://nostr-pub.wellorder.net']


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

def do_post(as_user, msg, to_users, is_encrypt):
    is_connected = False
    def my_connect(the_client):
        nonlocal is_connected
        is_connected = True

    with Client('ws://localhost:8081', on_connect=my_connect) as my_client:
        while not is_connected:
            time.sleep(0.2)

        tags = []
        for c_t in to_users:
            tags.append(['p', c_t.public_key])

        if not is_encrypt:
            evt = Event(kind=Event.KIND_TEXT_NOTE,
                        content=msg,
                        pub_key=as_user.public_key,
                        tags=tags)

            evt.sign(as_user.private_key)
            my_client.publish(evt)
        else:
            for c_post in tags:
                evt = Event(kind=Event.KIND_ENCRYPT,
                            content=msg,
                            pub_key=as_user.public_key,
                            tags=[c_post])
                evt.content = evt.encrypt_content(priv_key=as_user.private_key,
                                                  pub_key=c_post[1])
                evt.sign(as_user.private_key)
                my_client.publish(evt)

def show_post_info(as_user, msg, to_users, is_encrypt):
    enc_text = 'encrypted'
    if not is_encrypt:
        enc_text = 'plain_text'

    print('\nsending %s message as %s  ' % (enc_text,
                                            as_user.display_name()))

    print('%s\n%s\n%s' % (''.join(['-'] * 10),
                          msg,
                          ''.join(['-'] * 10)))
    if to_users:
        print('to:')
    for c_t in to_users:
        print(c_t.display_name())

def run_post():
    as_user = None
    is_encrypt = True
    ignore_missing = False
    peh = ProfileEventHandler(PROFILE_STORE)
    to_users = []

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ha:t:pi', ['help',
                                                             'as_profile=',
                                                             'plain_text',
                                                             'to=',
                                                             'ignore_missing'])

        for o, a in opts:
            if o in ('-i', '--ignore_missing'):
                ignore_missing = True

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            if o in ('-a', '--as_profile'):
                as_user = _get_profile(a, peh, '--as_profile %s not found' % a)
            if o in ('-p', '--plain_text'):
                is_encrypt = False
            if o in ('-t','--to'):
                for c_t in a.split(','):
                    to_add = _get_profile(c_t, peh, 'to profile %s not found' % c_t)
                    if to_add:
                        to_users.append(to_add)
                    elif not ignore_missing:
                        print('to profile missing and ignore_missing not set')
                        sys.exit(2)


        if not as_user and len(args)>0:
            a = args.pop(0)
            as_user = _get_profile(a, peh,'args[] %s not found' % a)

        if not as_user:
            print('no profile to post as supplied or unable to find')
            sys.exit(2)

        if not to_users and is_encrypt:
            print('to users must be defined for encrypted posts')
            sys.exit(2)

        if not len(args) > 0:
            print('no message supplied!!!')
            sys.exit(2)

        msg = ' '.join(args)

        show_post_info(as_user, msg, to_users, is_encrypt)
        do_post(as_user, msg, to_users, is_encrypt)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_post()

    # def my_connect(the_client: Client):
    #     print('connect')
    #     the_client.subscribe(handlers=[PrintEventHandler()], filters={
    #         'kinds': [1],
    #         'authors': ['0a6a0b8d3c024faa8c5b944dbcd88173fd0978a57700be17e681f6ee572205ec']
    #     })
    #
    #
    # my_client = Client('wss://rsslay.fiatjaf.com', on_connect=my_connect).start()