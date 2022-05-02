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
RELAYS = ['ws://localhost:8081']
AS_PROFILE = None
VIEW_PROFILE = None

def usage():
    print("""
usage:



    """)
    sys.exit(2)

from cmd_post import prompt_loop


def await_run():
    config = {
        'as_user': 'monty2',
        'await_user': 'monty1'
    }

    peh = ProfileEventHandler(PROFILE_STORE)
    as_user = peh.profiles.get_profile(config['as_user'],
                                       create_type=ProfileList.CREATE_PUBLIC)

    await_user = peh.profiles.get_profile(config['await_user'],
                                          create_type=ProfileList.CREATE_PUBLIC)

    print('running as: %s' % as_user.display_name())
    print('awaiting: %s' % await_user.display_name())
    since = datetime.now()

    class my_handler:

        def do_event(self, sub_id, evt: Event, relay):
            if evt.pub_key == await_user.public_key and evt.created_at >= since:
                if evt.kind == Event.KIND_ENCRYPT:
                    try:
                        content = evt.decrypted_content(as_user.private_key, await_user.public_key)

                        def my_chat(evt: Event, cmd_args):

                            to_users = []
                            to_users.append(peh.profiles.get_profile(evt.pub_key,
                                                                     create_type=ProfileList.CREATE_PUBLIC))
                            for p in evt.p_tags:
                                if p != as_user.public_key:
                                    to_users.append(
                                        peh.profiles.get_profile(p,
                                                                 create_type=ProfileList.CREATE_PUBLIC)
                                    )

                            subject = None
                            if evt.get_tags('subject'):
                                subject = evt.get_tags('subject')[1]
                            logging.debug(to_users)
                            try:
                                prompt_loop(as_user, None, to_users, True, subject)
                            except Exception as e:
                                print(e)

                        def my_file(evet, cmd_args):
                            print('worm file')

                        cmd_map = {
                            'chat': my_chat,
                            'worm': my_file
                        }

                        words = content.split(' ')
                        if words:
                            cmd = words[0]
                            cmd_args = words[1:]
                            if cmd in cmd_map:
                                cmd_map[cmd](evt, cmd_args)

                    except:
                        pass


    def on_connect(the_client:Client):
        print('connected %s ' % the_client.url)
        the_client.subscribe(handlers=my_handler())

    Client('ws://localhost:8081', on_connect=on_connect).start()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    await_run()

    # def my_connect(the_client: Client):
    #     print('connect')
    #     the_client.subscribe(handlers=[PrintEventHandler()], filters={
    #         'kinds': [1],
    #         'authors': ['0a6a0b8d3c024faa8c5b944dbcd88173fd0978a57700be17e681f6ee572205ec']
    #     })
    #
    #
    # my_client = Client('wss://rsslay.fiatjaf.com', on_connect=my_connect).start()