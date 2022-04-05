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
from db.db import Database, SQLiteDatabase
from cmd_line.message_app import ChatApp

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

def run_chat_app():
    from nostr.client.client import ClientPool
    my_client = ClientPool('ws://192.168.0.17:8081')
    ChatApp('message_to', my_client, DB).start()
    my_client.end()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_chat_app()

    # plain_text_chat(
    #     from_user='firedragon888',
    #     to_user='3648e5c206883d9118d9c19a01ddde96059c5f46a89444b252e247ca9b9270e3',
    #     db=DB
    # )



    #
    # def my_connect(the_client):
    #     the_client.subscribe('web', None, {
    #         'since': 1000000
    #     })
    #
    #
    # Client('ws://localhost:8082/', on_connect=my_connect).start()