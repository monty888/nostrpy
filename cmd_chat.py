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

def run_chat_app():
    from nostr.client.client import ClientPool
    # my_client = ClientPool('ws://192.168.0.17:8081')
    # my_client = ClientPool(['ws://localhost:8081'])
    my_client = ClientPool(['wss://nostr-pub.wellorder.net'])
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