"""
    very simple command program that does a chat between 2 people other nostr
    TODO
        plain text chat
        nip04 encrypted chat
        wrapped encryped chat via public inboc
    This it to get the basics together before doing a gui based chat app probably using Kivy

"""
# from gevent import monkey
# monkey.patch_all()
import logging
import sys

from nostr.ident import Profile, UnknownProfile
from nostr.client.client import Client
from nostr.client.persist import  SQLStore
from nostr.client.event_handlers import PersistEventHandler
from nostr.client.messaging import MessageThreads
from nostr.event import Event
from db.db import Database, SQLiteDatabase
from cmd_line.message_app import MessageApp

# TODO: also postgres
DB = SQLiteDatabase('/home/shaun/.nostrpy/nostr-client.db')

def get_profiles(from_user, to_user, db: Database=None):
    from_p: Profile = None
    to_p: Profile = None

    def create_from_hex(key, is_priv_key):
        ret = None
        priv_key = None
        pub_key = None
        try:
            # we're expecting a key so it better be 64bytes
            if len(key) == 64:
                # and also hex, will throw otherwise
                bytearray.fromhex(from_user)
                # needs to priv_key if it's out local profile
                if is_priv_key:
                    priv_key = key
                else:
                    pub_key = key
                ret = Profile(profile_name=None,
                              priv_k=priv_key,
                              pub_k=pub_key)

        # can't be private key as not hex
        except ValueError:
            pass

        # all being well this should be a profile
        return ret

    if db:
        try:
            from_p = Profile.load_from_db(db, from_user)
        except UnknownProfile:
            pass

        try:
            to_p = Profile.load_from_db(db, to_user)
        except UnknownProfile:
            pass

    if not from_p:
        from_p = create_from_hex(from_user, True)
    if not to_p:
        to_p = create_from_hex(to_user, False)

    if from_p is None:
        print('unable to create local user with key=%s' % from_user)
        sys.exit(2)
    if to_p is None:
        print('unable to create local user with key=%s' % from_user)
        sys.exit(2)

    return {
        'from' : from_p,
        'to' : to_p
    }

# TODO: most of this can probably be moved to cmd_line/message_app.py too
def plain_text_chat(from_user, to_user, db: Database=None):
    # with what we've been given attempt to get profiles for the from and to users
    # will just exit if it can't create from user with priv_k and to_user with pub_k
    profiles = get_profiles(from_user=from_user,
                            to_user=to_user,
                            db=db)
    from_p: Profile = profiles['from']
    to_p: Profile = profiles['to']

    note_kind = Event.KIND_ENCRYPT

    my_store = None
    if db:
        my_store = SQLStore(db)

    def do_message(text):
        my_msg_thread.post_message(my_client, from_p, to_p, text,kind=note_kind)

    my_display = MessageApp(from_p=from_p,
                            to_p=to_p,
                            on_message_enter=do_message)

    def draw_msgs():
        my_display.set_messages(my_msg_thread.messages(to_p.public_key,
                                                       note_kind))

    my_msg_thread = MessageThreads(from_p=from_p,
                                   evt_store=my_store,
                                   on_message=draw_msgs,
                                   kinds=note_kind)

    def my_subscribe(the_client: Client):
        # sub for messages we don't have
        handlers = [my_msg_thread]
        if my_store:
            handlers.append(PersistEventHandler(my_store))

        # important, on_connect is current called without spawning off so if you don't return from here
        # handlers won't see anything... or at least things will get odd
        the_client.subscribe(handlers=handlers,
                             filters={
                                 'kinds': note_kind,
                                 'authors': [
                                     from_p.public_key, to_p.public_key
                                 ],
                                 '#p': [
                                     from_p.public_key, to_p.public_key
                                 ]
                             })

    my_client = Client('ws://192.168.0.17:8081', on_connect=my_subscribe).start()
    draw_msgs()

    # import signal
    # def sigint_handler(signal, frame):
    #     logging.debug('RESIZED!!!!!!')
    # signal.signal(signal.SIGWINCH, sigint_handler)

    my_display.run()
    my_client.end()

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)

    plain_text_chat(
        from_user='firedragon888',
        to_user='3648e5c206883d9118d9c19a01ddde96059c5f46a89444b252e247ca9b9270e3',
        db=DB
    )

    #
    # def my_connect(the_client):
    #     the_client.subscribe('web', None, {
    #         'since': 1000000
    #     })
    #
    #
    # Client('ws://localhost:8082/', on_connect=my_connect).start()