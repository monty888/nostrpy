"""
    very simple command program that does a chat between 2 people other nostr
    TODO
        plain text chat
        nip04 encrypted chat
        wrapped encryped chat via public inboc
    This it to get the basics together before doing a gui based chat app probably using Kivy

"""
import logging
import sys
from prompt_toolkit import prompt

from nostr.ident import Profile, UnknownProfile
from nostr.client.client import Client
from nostr.event import Event
from db.db import Database, SQLiteDatabase


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

def get_messages(from_user:Profile, to_user:Profile, the_client):
    pass

def plain_text_chat(from_user, to_user, db: Database=None):
    # with what we've been given attempt to get profiles for the from and to users
    # will just exit if it can't create from user with priv_k and to_user with pub_k
    profiles = get_profiles(from_user=from_user,
                            to_user=to_user,
                            db=db)
    from_p: Profile = profiles['from']
    to_p: Profile = profiles['to']

    class my_handler:

        def do_event(self, sub_id, evt: Event, relay):
            pass


    def my_subscribe(the_client:Client):
        the_client.subscribe(handlers=my_handler(),
                             filters={
                                 'kinds': Event.KIND_TEXT_NOTE,
                                 'authors': [
                                     from_p.public_key, to_p.public_key
                                 ],
                                 # '#p' : [
                                 #     from_p.public_key, to_p.public_key
                                 # ]
                             })

    my_client = Client('ws://localhost:8082', on_connect=my_subscribe).start()

    print(from_p.display_name(True))
    print(to_p.display_name(True))

    text = ''
    while text != 'exit':
        text = prompt('%s: ' % from_p.display_name())
        my_client.publish(Event())

    my_client.end()

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.WARN)

    plain_text_chat(
        from_user='firedragon888',
        to_user='460c25e682fda7832b52d1f22d3d22b3176d972f60dcdc3212ed8c92ef85065c',
        db=DB
    )
