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
import os
from pathlib import Path
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
        # TODO:
        #  don't think theres any guarantee of order so we should probably do this ourself
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

    @property
    def messages(self):
        return self._msgs


class MessageThreads:
    """
        keep a track of all 1-1 message for from_p
        if evt_store is given then

    """
    def __init__(self,
                 from_p: Profile,
                 evt_store: ClientStoreInterface,
                 on_message=None,
                 to_pub_k=None,
                 kinds=[Event.KIND_TEXT_NOTE]):
        """

        :param from_p:
        :param evt_store:
        :param on_message:
        :param to_pub_k:
        :param kinds:
        """

        self._from = from_p
        if not to_pub_k:
            to_pub_k = []
        if isinstance(to_pub_k, str):
            to_pub_k = [to_pub_k]

        self._to_puk_key = to_pub_k

        self._kinds = kinds

        self._msg_lookup = set()

        self._evt_store = evt_store

        # messages keyed on pub_key of who they are to
        self._msg_threads = {}

        self.load_local()
        self._on_message = on_message

    def load_local(self):
        """
        load the already seen msgs from what we've already seen locally
        """

        # we have no local store of events, completely reliant on fetch from relay
        if not self._evt_store:
            return

        # get all messages we created all were mentioned in
        all_evts = self._evt_store.get_filter(
            [
                {
                    'kinds': self._kinds,
                    'authors': [self._from.public_key]
                },
                {
                    'kinds': self._kinds,
                    '#p': [self._from.public_key]
                }
            ]
        )
        # we want newest at the bottom
        all_evts.reverse()
        c_evt: Event
        for c_evt in all_evts:
            self._add_msg(c_evt)

    def _add_msg(self, msg_evt):
        tags = msg_evt.get_tags('p')
        # we've already seen this event either from local store or previous sub recieved
        # or it's not 1-1 msg
        if msg_evt.id in self._msg_lookup or len(tags) != 1:
            return False

        to_id = tags[0][0]
        # must be our event to them
        if to_id == self._from.public_key:
            to_id = msg_evt.pub_key

        if to_id not in self._msg_threads:
            """
                seperate store for the different types of notes, dict as we might in future add unread count etc.
            """
            self._msg_threads[to_id] = {
                Event.KIND_TEXT_NOTE: {
                    'msgs': []
                },
                Event.KIND_ENCRYPT: {
                    'msgs': []
                }
            }

        self._msg_threads[to_id][msg_evt.kind]['msgs'].append(msg_evt)
        self._msg_lookup.add(msg_evt.id)
        return True

    def do_event(self, sub_id, evt: Event, relay):
        if self._add_msg(evt) and self._on_message:
            self._on_message()
        # print(self._msgs)

    def post_message(self,
                     the_client: Client,
                     from_user: Profile,
                     to_user: Profile,
                     msg,
                     kind=Event.KIND_TEXT_NOTE):
        """
        :param from_user:
        :param to_user:
        :param msg:
        :param kind:
        :return:
        """
        n_event = Event(kind=kind,
                        content=msg,
                        pub_key=from_user.public_key,
                        tags=[
                            ['p', to_user.public_key]
                        ])
        n_event.sign(from_user.private_key)
        the_client.publish(n_event)

    def messages(self, pub_k, kind):
        return self._msg_threads[pub_k][kind]['msgs']

# def post_message(the_client: Client, from_user:Profile, to_user:Profile, msg):
#     n_event = Event(kind=Event.KIND_TEXT_NOTE,
#                     content=msg,
#                     pub_key=from_user.public_key,
#                     tags=[
#                         ['p', to_user.public_key]
#                     ])
#     n_event.sign(from_user.private_key)
#     the_client.publish(n_event)


class BasicScreenApp:

    def __init__(self,
                 from_p: Profile,
                 to_p: Profile,
                 on_message_enter):
        self._from_p = from_p
        self._to_p = to_p

        self._ident_lookup = {
            from_p.public_key: from_p,
            to_p.public_key: to_p
        }

        self._enter_prompt = '%s: ' % self._from_p.display_name()
        self._msgs_height = 0

        self._name_prompt_width = len(from_p.display_name())
        if len(to_p.display_name()) > self._name_prompt_width:
            self._name_prompt_width = len(to_p.display_name())
        if self._name_prompt_width > 10:
            self._name_prompt_width = 10

        kb = KeyBindings()

        @kb.add('c-q')
        def do_quit(e):
            self._app.exit()

        @kb.add('c-up')
        def do_up(e):
            pos = self._scroll.vertical_scroll-1
            if pos<0:
                pos = 0
            self._scroll.vertical_scroll = pos

        @kb.add('c-down')
        def do_up(e):
            pos = self._scroll.vertical_scroll + 1

            if pos > self._msgs_height - os.get_terminal_size().lines+3:
                pos = self._msgs_height - os.get_terminal_size().lines+3

            self._scroll.vertical_scroll = pos

        def my_change(buffer):
            on_message_enter(buffer.text)
            buffer.text = ''
            return True

        self._prompt = Buffer(accept_handler=my_change,
                              multiline=True)  # Editable buffer.

        self._msg_area = HSplit([])
        self._scroll = ScrollablePane(content=self._msg_area,
                                      keep_cursor_visible=True)

        self._enter_bar = VSplit([
            Window(height=1,
                   width=len(self._enter_prompt),
                   content=FormattedTextControl(self._enter_prompt)),
            Window(height=3, content=BufferControl(buffer=self._prompt))
        ])

        # struct
        self._root_container = HSplit([
            # content
            # ScrollablePane(self._main_window, keep_cursor_visible=True),
            self._scroll,
            # msg entry

            self._enter_bar


        ])
        self._layout = Layout(self._root_container)
        self._app = Application(layout=self._layout,
                                full_screen=True,
                                key_bindings=kb,
                                mouse_support=True)

    def run(self):
        self._app.run()

    def set_messages(self, msgs):
        self._msg_area.children = []
        c_msg: Event
        total_height = 0
        for c_msg in msgs:
            c_msg_arr = []
            msg_from = self._ident_lookup[c_msg.pub_key]

            user = msg_from.display_name()
            if len(user) > self._name_prompt_width:
                user = user[:self._name_prompt_width-2] + '..'

            prompt_text = '%s@%s:' % (user.rjust(self._name_prompt_width),
                                       c_msg.created_at)

            prompt_col = 'gray'
            if c_msg.pub_key != self._from_p.public_key:
                prompt_col = 'green'

            c_msg_arr.append((prompt_col, prompt_text))

            first_line = True
            for c_line in c_msg.content.split('\n'):
                if first_line:
                    c_msg_arr.append(('', c_line))
                    first_line = False
                else:
                    c_msg_arr.append(('', '\n' + ''.join([' ']*len(prompt_text)) + c_line))

            # c_msg_arr.append(('', '\n'))
            # msg_arr.append('[SetCursorPosition]', '')
            win_height = len(c_msg_arr)-1
            n_win = Window(content=FormattedTextControl(text=c_msg_arr), height=win_height)
            total_height += win_height
            self._msg_area.children.append(n_win)

        self._msgs_height = total_height
        self._app.invalidate()
        self._scroll.vertical_scroll = self._msgs_height - os.get_terminal_size().lines+3

def plain_text_chat(from_user, to_user, db: Database=None):
    # with what we've been given attempt to get profiles for the from and to users
    # will just exit if it can't create from user with priv_k and to_user with pub_k
    profiles = get_profiles(from_user=from_user,
                            to_user=to_user,
                            db=db)
    from_p: Profile = profiles['from']
    to_p: Profile = profiles['to']

    my_store = None
    if db:
        my_store = SQLStore(db)

    def do_message(text):
        my_msg_thread.post_message(my_client, from_p, to_p, text)

    my_display = BasicScreenApp(from_p=from_p,
                                to_p=to_p,
                                on_message_enter=do_message)

    def draw_msgs():
        my_display.set_messages(my_msg_thread.messages(to_p.public_key,Event.KIND_TEXT_NOTE))

    my_msg_thread = MessageThreads(from_p=from_p,
                                  # to_p=to_p,
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

    my_client = Client('ws://192.168.0.16:8081', on_connect=my_subscribe).start()

    draw_msgs()
    my_display.run()


    my_client.end()

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)

    plain_text_chat(
        from_user='3648e5c206883d9118d9c19a01ddde96059c5f46a89444b252e247ca9b9270e3',
        to_user='firedragon888',
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