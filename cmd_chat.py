"""
    very simple command program that does a chat between 2 people other nostr
    TODO
        plain text chat
        nip04 encrypted chat
        wrapped encryped chat via public inboc
    This it to get the basics together before doing a gui based chat app probably using Kivy

"""
from gevent import monkey
monkey.patch_all()
import logging
import sys
import time

from prompt_toolkit import prompt
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window, VSplit
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.key_binding import KeyBindings


from nostr.ident import Profile, UnknownProfile
from nostr.client.client import Client
from nostr.client.persist import ClientStoreInterface, SQLStore
from nostr.client.event_handlers import PersistEventHandler
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


class MessageThread:

    def __init__(self, from_p:Profile,
                 to_p: Profile,
                 evt_store: ClientStoreInterface,
                 on_message=None):
        self._from = from_p
        self._to = to_p
        self._msgs = []
        self._msg_lookup = set()
        self._evt_store = evt_store

        # this will get msgs where either of our users published and the
        # other was mentioned, because we're only interested in 1-1 we'll
        # have to further restict ourself by making sure there is only 1 #p
        self._msg_filter = {
            'kinds': Event.KIND_TEXT_NOTE,
            'authors': [
                self._from.public_key,
                self._to.public_key
            ],
            '#p': [
                self._from.public_key,
                self._to.public_key
            ]
        }

        self.load_local()
        self._on_message = on_message

    def load_local(self):
        """
        load the already seen msgs from what we've already seen locally
        """

        # we have no local store of events, completely reliant on fetch from relay
        if not self._evt_store:
            return

        # this will
        all_evts = self._evt_store.get_filter(self._msg_filter)
        # make sure it was 1-1
        for c_evt in all_evts:
            if len(c_evt.get_tags('p')) == 1:
                self._msgs.append(c_evt)
                self._msg_lookup.add(c_evt.id)

    def do_event(self, sub_id, evt: Event, relay):
        if len(evt.get_tags('p')) == 1 and not evt.id in self._msg_lookup:
            self._msgs.append(evt)
            self._msg_lookup.add(evt.id)
            if self._on_message:
                self._on_message()
        # print(self._msgs)


def post_message(the_client: Client, from_user:Profile, to_user:Profile, msg):
    n_event = Event(kind=Event.KIND_TEXT_NOTE,
                    content=msg,
                    pub_key=from_user.public_key,
                    tags=[
                        ['p', to_user.public_key]
                    ])
    n_event.sign(from_user.private_key)
    the_client.publish(n_event)


class BasicScreenApp:

    def __init__(self):
        kb = KeyBindings()

        @kb.add('c-q')
        def do_quit(e):
            self._app.exit()


        self._prompt =  Buffer()  # Editable buffer.
        self._main_window = Window(content=FormattedTextControl(text='nothing yet'))

        # struct
        self._root_container = HSplit([
            # content
            ScrollablePane(self._main_window),
            # msg entry

            VSplit([
                Window(height=1, width=20, content=FormattedTextControl('PROMPOT>>>')),
                Window(height=1, content=BufferControl(buffer=self._prompt))
            ])


        ])
        self._layout = Layout(self._root_container)
        self._app = Application(layout=self._layout, full_screen=True, key_bindings=kb
                                , mouse_support=True)

    def run(self):
        self._app.run()

    def set_main_content(self, content):
        self._main_window.content = FormattedTextControl(text=content)
        self._app.invalidate()

def plain_text_chat(from_user, to_user, db: Database=None):
    # with what we've been given attempt to get profiles for the from and to users
    # will just exit if it can't create from user with priv_k and to_user with pub_k
    profiles = get_profiles(from_user=from_user,
                            to_user=to_user,
                            db=db)
    from_p: Profile = profiles['from']
    to_p: Profile = profiles['to']
    ident_lookup = {
        from_p.public_key: from_p,
        to_p.public_key: to_p
    }
    my_store = None
    if db:
        my_store = SQLStore(db)

    my_display = BasicScreenApp()

    def draw_msgs():
        c_msg: Event
        msg_arr = []
        for c_msg in my_msg_thread._msgs:
            msg_from = ident_lookup[c_msg.pub_key]
            msg_arr.append(('%s@%s: %s' % (msg_from.display_name(),
                                             c_msg.created_at,
                                             c_msg.content)))
        my_display.set_main_content('\n'.join(msg_arr))


    my_msg_thread = MessageThread(from_p=from_p,
                                  to_p=to_p,
                                  evt_store=my_store,
                                  on_message=draw_msgs)

    def my_subscribe(the_client: Client):
        # sub for messages we don't have
        handlers = [my_msg_thread]
        if my_store:
            handlers.append(PersistEventHandler(my_store))

        # important, on_connect is current called without spawning off so if you don't return from here
        # handlers won't see anything... or at least things will get odd
        the_client.subscribe(handlers=handlers,
                             filters={
                                 'kinds': Event.KIND_TEXT_NOTE,
                                 'authors': [
                                     from_p.public_key, to_p.public_key
                                 ],
                                 '#p': [
                                     from_p.public_key, to_p.public_key
                                 ]
                             })





    my_client = Client('ws://localhost:8082', on_connect=my_subscribe).start()

    # look to write our messages until exit
    # draw_msgs()
    # while True:
    #     text = prompt('%s: ' % from_p.display_name())
    #     if text == 'exit':
    #         break
    #     post_message(my_client,
    #                  from_user=from_p,
    #                  to_user=to_p,
    #                  msg=text)

    draw_msgs()
    my_display.run()


    my_client.end()




if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    #
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