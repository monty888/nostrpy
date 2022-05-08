import asyncio
import logging
import os
import time

from abc import abstractmethod
from prompt_toolkit import Application
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.layout.containers import HSplit, Window, VSplit, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import FloatContainer, Float
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.widgets import VerticalLine, Button,TextArea, HorizontalLine, Dialog, \
    SearchToolbar, Frame, RadioList
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
from prompt_toolkit.mouse_events import MouseEvent, MouseButton, MouseEventType
from nostr.ident.profile import Profile, ProfileEventHandler, UnknownProfile, ProfileList
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.event_handlers import PersistEventHandler
from nostr.event import Event
from nostr.client.client import Client
from nostr.client.persist import SQLEventStore, TransientEventStore
from nostr.client.messaging import MessageThreads
from db.db import Database

def is_left_click(e):
    return e.event_type == MouseEventType.MOUSE_DOWN and e.button == MouseButton.LEFT


class DialogBase:

    def __init__(self, title,
                 app: Application,
                 on_close=None):
        # screen layout obj, we'll get root con from here
        self._app = app
        # root con, it should be FloatContainer, maybe throw here if not...
        self._con = self._app.layout.container

        self._kb = KeyBindings()
        # probably at the least you'll want to focus somewhere
        self._on_close = on_close

        # key short cur to close the dialog
        @self._kb.add('c-c')
        def _(e):
            self.hide()

        self._title = title
        self._content = None
        self._my_diag = None
        self._my_float = None

    # the actual dialog obj that contains our content as it's body
    @abstractmethod
    def create_content(self):
        pass

    def show(self):
        self.create_content()
        # it seems these need to be recreated all the time
        self._my_diag = Dialog(title=self._title,
                               body=self._content)

        self._my_float = Float(self._my_diag)

        self._con.floats.append(self._my_float)

        self._app.layout.focus(self._my_diag)

    def hide(self):
        self._con.floats = []
        if self._on_close:
            self._on_close()


class SearchContactDialog(DialogBase):

    def __init__(self, app: Application,
                 profiles: ProfileList,
                 on_close=None):

        # inputs/widget
        # text area input contact search


        def my_cancel():
            self.hide()

        def my_select():
            if len(self._search_in.text) == 64:
                self._profile_key = self._search_in.text
            self.hide()

        self._search_in = None
        self._search_in_buf_con = None

        self._cancel_but = Button('cancel', handler=my_cancel)
        self._select_but = Button('select', handler=my_select)

        self._profiles = profiles
        self._highlight_index = 0
        super().__init__(title='start messaging contact',
                         app=app,
                         on_close=on_close)

        # couldn't work out how to get the autocomplete working in prompt toolkit in full screen app
        # so we'll do it ourself, maybe revisit in future

        self._match_con = None
        self._suggest_con = None
        self._matches = []
        self._search_text = ''

        # set when a valid key is entered and dialog closed with select
        self._profile_key = None

        @self._kb.add('down')
        def _(e):
            self._highlight_index += 1
            if self._highlight_index>=len(self._matches):
                self._highlight_index = 0
            self._prep_suggest_con()

        @self._kb.add('up')
        def _(e):
            self._highlight_index -= 1
            if self._highlight_index<0:
                self._highlight_index = len(self._matches)-1
            self._prep_suggest_con()


    def _prep_suggest_con(self):
        self._matches = []
        self._suggest_con = []
        in_str = self._search_text
        if len(in_str.replace(' ', '')) > 0:
            self._matches = self._profiles.matches(self._search_text, 20)

        to_add = []

        def get_complete(item_index):
            def my_complete(e):
                if is_left_click(e):
                    self._highlight_index = item_index
                    self._search_in.text = self._matches[self._highlight_index].public_key
                    self._app.layout.focus(self._select_but)
                    return True
            return my_complete

        for i, c_p in enumerate(self._matches):
            color = ''
            if i == self._highlight_index:
                color = 'green'

            to_add.append(Window(
                content=FormattedTextControl(text=[(color, c_p.display_name(with_pub=True), get_complete(i))]),
                height=1
            ))

        self._match_con.children = to_add

    def create_content(self):
        @Condition
        def _():
            return len(self._matches) > 0

        def my_change(buf: Buffer):
            self._highlight_index = 0
            self._search_text = buf.text
            self._prep_suggest_con()

        def my_complete(buf: Buffer):
            if self._matches:
                buf.text = self._matches[self._highlight_index].public_key
            self._app.layout.focus(self._select_but)
            return True

        self._search_in = Buffer(on_text_changed=my_change,
                                 multiline=False,
                                 accept_handler=my_complete)
        self._search_in_buf_con = BufferControl(self._search_in,
                                                preview_search=True)
        self._match_con = HSplit(children=[])
        self._suggest_con = ConditionalContainer(content=self._match_con, filter=_)

        self._content = HSplit(children=[
                Window(content=self._search_in_buf_con, width=32, height=1),
                self._suggest_con,
                Window(content=FormattedTextControl(text=''), width=32),
                VSplit(children=[
                    self._select_but,
                    Window(content=FormattedTextControl(text='')),
                    self._cancel_but
                ], height=1)
            ],
            key_bindings=self._kb)
        self._app.invalidate()

    def show(self):
        super().show()
        self._app.layout.focus(self._search_in)

    def hide(self):
        self._search_in.text = ''
        super().hide()

    @property
    def selected_profile_key(self):
        return self._profile_key


class SwitchProfileDialog(DialogBase):

    def __init__(self, app: Application,
                 on_profile_change,
                 on_close=None):
        self._on_profile_change = on_profile_change
        # inputs/widget
        # text area input contact search
        super().__init__(title='switch user',
                         app=app,
                         on_close=on_close)

    def create_content(self):
        to_add = []
        lookup = {}
        c_p: Profile
        for c_p in self._profiles:
            to_add.append(
                (c_p.public_key, c_p.display_name)
            )
            lookup[c_p.public_key] = c_p

        n_radio = RadioList(to_add, default=self._from_p.public_key)
        n_radio.show_scrollbar = False

        def is_changed():
            s_p = lookup[n_radio.current_value]
            if s_p != self._from_p:
                self._on_profile_change(s_p)
            self.hide()

        self._content = HSplit(children=[n_radio,
                                         VSplit(children=[
                                             Button(text='ok', handler=is_changed),
                                             Window(content=[], width=5),
                                             Button(text='cancel',handler=self.hide),
                                         ])],
                               key_bindings=self._kb)
        # self._content.children.append(TextArea())

    def show(self, from_p, all_profiles):
        self._from_p = from_p
        self._profiles = all_profiles
        super().show()


class RelayInfoDialog(DialogBase):

    def __init__(self, app: Application,
                 chat_app,
                 on_close=None):

        self._chat_app = chat_app
        self._relay_con = None
        super().__init__(title='relay status',
                         app=app,
                         on_close=on_close)

    def create_content(self):
        def do_close():
            self.hide()

        self._relay_con = HSplit([])
        self._content = HSplit([
            self._relay_con,
            VSplit([
                Window(),
                Button('ok', handler=do_close)
            ])
        ])
        self.update_relay_status()

    def update_relay_status(self):
        if self._content is None:
            return

        c_client: Client
        relay_info = []
        for c_client in self._chat_app.client:
            color = ''
            info_text = '%s - OK' % c_client.url
            if not c_client.connected:
                info_text = '%s - %s' % (c_client.url, c_client.last_error)
                color = 'red'

            relay_info.append(Window(FormattedTextControl(text=[(color, info_text)])))
        self._relay_con.children = relay_info

    def show(self):
        super().show()


class ChatGui:
    """
        interface for a simple 1 page app for viewing messages in the terminal
        using python prompt-toolkit
    """
    def __init__(self, chat_app):

        # app logic
        self._chat_app: ChatApp = chat_app

        self._msgs_height = 0

        # the root for everything, it's a float container so we can add dialogs
        self._root_con = FloatContainer(
            # main contents here
            content=Window(content=[]),
            # add dialogs here
            floats=[]
        )
        self._layout = Layout(self._root_con)

        kb = KeyBindings()

        @kb.add('c-q')
        def do_quit(e):
            self._app.exit()

        @kb.add('c-up')
        def do_up(e):
            pos = self._scroll.vertical_scroll-1
            if pos < 0:
                pos = 0
            self._scroll.vertical_scroll = pos

        @kb.add('c-down')
        def do_down(e):
            pos = self._scroll.vertical_scroll

            if (self._msgs_height + 4 - pos) > os.get_terminal_size().lines:
                pos += 1

            self._scroll.vertical_scroll = pos

        @kb.add('tab')
        def do_tab(e):
            self._layout.focus_next()

        @kb.add('s-tab')
        def do_tab(e):
            self._layout.focus_previous()

        self._app = Application(layout=self._layout,
                                full_screen=True,
                                key_bindings=kb,
                                mouse_support=True)
        # create our dialogs
        # profile switch dialog
        self._p_switch_dialog = SwitchProfileDialog(self._app,
                                                    on_close=self._focus_prompt,
                                                    on_profile_change=self._chat_app.set_from_profile)
        # relay info dialog
        self._relay_info_dialog = RelayInfoDialog(self._app,
                                                  self._chat_app,
                                                  on_close=self._focus_prompt)

        # events
        def msg_entered(buffer):
            self._chat_app.do_message(buffer.text)
            buffer.text = ''
            return True

        def my_send():
            msg_entered(self._prompt.buffer)
            self._layout.focus(self._prompt)

        # self._prompt = Buffer(accept_handler=my_change,
        #                       multiline=True)  # Editable buffer.

        # msg text entered here

        self._prompt = TextArea(height=3,
                                accept_handler=msg_entered)

        self._msg_area = HSplit([])
        self._scroll = ScrollablePane(content=self._msg_area,
                                      keep_cursor_visible=True)

        # creates the struct for the left hand bar of screen
        self._nav_area = None
        self._nav_contacts = None
        self._nav_controls = None
        self._create_nav_pane()

        self._enter_bar = VSplit([
            # Window(height=3, content=BufferControl(buffer=self._prompt)),
            self._prompt,
            Button(text='send', handler=my_send)
        ])

        self._title = self._create_title()
        self._title['update_profile'](self._chat_app.profile)

        # now we have the parts ready actually construct the screen
        self._root_con.content = HSplit([
            self._title['title_con'],
            # content
            # ScrollablePane(self._main_window, keep_cursor_visible=True),
            # self._scroll,
            VSplit([
                # profile data here
                self._nav_pane,
                VerticalLine(),
                self._scroll
            ]),
            # msg entry
            self._enter_bar
        ])

        self._layout.focus(self._prompt)

    def _focus_prompt(self):
        self._layout.focus(self._prompt)

    def _create_title(self):
        profile_con = FormattedTextControl('')
        profile_win = Window(
            content=profile_con,
            align=WindowAlign.LEFT
        )
        status_con = FormattedTextControl('<connection status>')
        status_win = Window(
            content=status_con,
            align=WindowAlign.RIGHT
        )

        con_con = VSplit(children=[
            profile_win,
            status_win
        ], height=1)

        def switch_profile(e):
            if is_left_click(e):

                self._p_switch_dialog.show(from_p=self._chat_app.profile,
                                           all_profiles=self._chat_app.get_local_profiles())

        def relay_click(e):
            if is_left_click(e):
                self._relay_info_dialog.show()

        def update_profile(from_p: Profile):
            profile_text = '<no profile>'
            if from_p:
                profile_text = self._chat_app.profile.display_name(with_pub=True)

            child_arr = [
                ('', 'Nostrpy CLI message v0.1, user: '),
                ('green', profile_text, switch_profile)
            ]
            profile_con.text = child_arr

        def update_status():
            status_text = [('red', 'not connected!', relay_click)]
            if self._chat_app.connected:
                con_counts = self._chat_app.connect_count
                if con_counts[0] == con_counts[1]:
                    status_text = [('green', 'connected', relay_click)]
                else:
                    status_text = [('orange', 'connected %s/%s' % (con_counts[1], con_counts[0]), relay_click)]

            status_con.text = status_text

        return {
            'title_con': con_con,
            'update_profile': update_profile,
            'update_status': update_status
        }

    def update_title(self):
        # we could expose this seperately but doesn't seem worth it
        self._title['update_profile'](self._chat_app.profile)
        self._title['update_status']()
        self._relay_info_dialog.update_relay_status()
        self._app.invalidate()

    def _create_nav_pane(self):
        def new_contact():
            self._new_contact_dialog.show()

        def contact_selected():
            if self._new_contact_dialog.selected_profile_key:
                self._chat_app.set_view_profile(self._new_contact_dialog.selected_profile_key)


            self._focus_prompt()

        self._new_contact_dialog = SearchContactDialog(self._app,
                                                       profiles=self._chat_app.get_profile_lookup(),
                                                       on_close=contact_selected)

        self._nav_contacts = HSplit([])
        self._nav_controls = HSplit([
            Button(text='new contact', handler=new_contact),
            # Button(text='relays'),
            # Button(text='switch user')
        ])

        self._nav_pane = HSplit([
            self._nav_controls,
            HorizontalLine(),
            ScrollablePane(content=self._nav_contacts),

        ], width=24)

    def set_contacts(self, contacts):
        to_add = []

        def get_click(p: Profile):
            def my_click(e: MouseEvent):
                if is_left_click(e) and self._chat_app.set_view_profile:
                    self._chat_app.set_view_profile(p)

            return my_click

        for c in contacts:
            c_p = c['profile']
            n_count = ''
            if c['new_count']:
                n_count = '(%s)' % c['new_count']

            c_text = '%s %s' % (c_p.display_name(), n_count)
            color = ''
            if self._chat_app.view_profile and c_p.public_key == self._chat_app.view_profile.public_key:
                color = 'green'

            to_add.append(Window(content=FormattedTextControl(text=
            [
                (color, c_text, get_click(c_p))
            ])
                , height=1)
            )
        # just added to extend to the bottom of the screen
        to_add.append(Window())
        self._nav_contacts.children = to_add
        self._app.invalidate()

    def run(self):
        self._app.run()

    def _get_msg_prompt(self, msg: Event, to: Profile):
        to_display = to.display_name()
        from_p = self._chat_app.profile
        from_display = from_p.display_name()

        prompt_width = max(
            len(from_display),
            len(to_display),
            10
        )

        messager = from_p
        if msg.pub_key != from_p.public_key:
            messager = to

        u_dispay = messager.display_name()

        if len(u_dispay) > prompt_width:
            u_dispay = u_dispay[:u_dispay - 2] + '..'

        prompt_text = '%s@%s:' % (u_dispay.rjust(prompt_width),
                                  msg.created_at)

        prompt_col = 'gray'
        if messager != self._chat_app.profile:
            prompt_col = 'green'

        return prompt_col, prompt_text

    def update_messages(self):
        """
            redraws the message for chat_apps current view (to) profile
        """
        self._msg_area.children = []
        to_p = self._chat_app.view_profile
        c_msg: Event
        if not to_p:
            self._msgs_height = 1
            self._scroll.vertical_scroll = 0
            self._msg_area.children.append(
                Window(content=FormattedTextControl(text='click on a user or create new contact'), height=1)
            )
        else:
            msgs = self._chat_app.messages
            # height calc based on \n line count, going to be a bit flaky, there must be a better way?!
            total_height = 0
            for c_msg in msgs:
                c_msg_arr = []
                prompt_col, prompt_text = self._get_msg_prompt(c_msg, to_p)
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

            if self._msgs_height + 4 <= os.get_terminal_size().lines:
                self._scroll.vertical_scroll = 0
            else:
                self._scroll.vertical_scroll = self._msgs_height - os.get_terminal_size().lines + 4


class ChatApp:

    def __init__(self, as_profile,
                 client,
                 db: Database,
                 kind=Event.KIND_ENCRYPT):

        # either client or client pool (untested..)
        self._client = client

        self._db = db
        # helps us present friendly ident info rather then having to show keys
        self._profiles: ProfileEventHandler = None

        if self._db:
            # we'll want to listen eventually and add as handler to client sub
            self._profiles = ProfileEventHandler(SQLProfileStore(self._db), None)
            self._event_store = SQLEventStore(self._db)
        else:
            self._profiles = ProfileEventHandler(TransientProfileStore(), None)
            self._event_store = TransientEventStore()


        self._profile = self._profiles.profiles.get_profile(as_profile,None)

        # nothing generate either using passed in value as priv_key or if that isn't valid generate one
        if not self._profile:
            if as_profile is not None:
                self._profile = self._profiles.profiles.get_profile(as_profile,
                                                                create_type='private')
            if not self._profile:
                adhoc_keys = Profile.get_new_key_pair()
                self._profile = Profile(priv_k=adhoc_keys['priv_k'],
                                        profile_name='adhoc_profile')
            # needed to show in switch profile
            self._profiles.profiles.add(self._profile)

        if not self._profile or not self._profile.private_key:
            raise UnknownProfile('unable to find profile %s or we don\'t have the private key for it')
        logging.debug('starting chat app using profile: %s' % self._profile)

        # standard txt or encrypted, to add wrapped inbox
        self._kind = kind

        # init gui
        self._display = ChatGui(chat_app=self)

        # in here we keep message threads and contacts per profile
        self._threads = {}
        # we do the same thing for contacts per profile
        self._contacts = {}

        # self._current_to = self._get_profile('3648e5c206883d9118d9c19a01ddde96059c5f46a89444b252e247ca9b9270e3')
        self._current_to = None
        # move to connect...
        self._draw_contacts()
        self._draw_messages()

        self._status = {
            'connected': None,
            'relay_count': 0,
            'connect_count': 0
        }

        self._start_client()

    def _start_client(self):
        # at the moment we're passing in actual client obj, think better to pass in urls and create ourself

        def my_connect(the_client: Client):
            handlers = [self]

            # we always create version of this now they just might not be to perm store
            handlers.append(PersistEventHandler(self._event_store))
            handlers.append(self._profiles)

            # because we added switching profiles simpler just to look at all events of correct kind
            filter = {
                'kinds': [self._kind, Event.KIND_META]
            }
            # to stop us always asking for everything, in the case of using a pool this might result in
            # missing events from certain relays so maybe add as option to Client where it'll get add since as
            # newest events per relay before making the subscribe. To do this clients will need to take the eventstore
            # on init, we could then also then just make some of the persistance stuff as bool flags on create?
            if self._event_store:
                evts = self._event_store.get_filter(filter)
                filter['since'] = self._event_store.get_newest(the_client.url)
                for c_evt in evts:
                    self.do_event(None, c_evt, None)


            the_client.subscribe(handlers=handlers, filters=filter)


        def my_status(status):
            last_connect_count = self.connect_count
            self._status = status
            if last_connect_count != self.connect_count:
                self._display.update_title()


        self._client.set_on_connect(my_connect)
        self._client.set_status_listener(my_status)
        self._client.start()

    @property
    def connected(self):
        return self._status['connected']

    @property
    def connect_count(self):
        return self._status['relay_count'], self._status['connect_count']

    @property
    def client(self):
        return self._client

    def do_event(self, sub_id, evt: Event, relay):
        # we only need to forward evts for profiles we already looked at, as others
        # will be picked up on load from db on create msgthread
        if evt.pub_key in self._threads:
            self._threads[evt.pub_key].do_event(sub_id, evt, relay)
        if evt.p_tags and evt.p_tags[0] in self._threads:
            self._threads[evt.p_tags[0]].do_event(sub_id, evt, relay)

    def do_message(self, text):
        self.profile_threads.post_message(the_client=self._client,
                                          from_user=self._profile,
                                          to_user=self._current_to,
                                          text=text,
                                          kind=self._kind)

    def _draw_contacts(self):
        profiles = []
        for c_key in self.profile_contacts:
            contact = self.profile_contacts[c_key]
            profiles.append({
                'profile': self._get_profile(c_key,
                                             create_type='public'),
                'new_count': len(self.profile_threads.messages(pub_k=c_key,
                                                               kind=self._kind,
                                                               since=contact['last_view'],
                                                               received_only=True))
            })

        self._display.set_contacts(profiles)

    def _new_message(self, msg: Event):
        if msg.pub_key not in self.profile_contacts \
                or msg.p_tags[0] not in self.profile_contacts:
            pub_k = msg.pub_key
            if pub_k == self.profile.public_key:
                pub_k = msg.p_tags[0]

            self.add_contact(pub_k)

        # new message on profile we're looking at
        if self._current_to and msg.pub_key == self._current_to.public_key or msg.pub_key == self._profile.public_key:
            self._draw_messages()
        else:
            self._draw_contacts()

    def _draw_messages(self):
        if self._current_to:
            msgs = self.profile_threads.messages(self._current_to.public_key,
                                                 self._kind)
            if msgs:
                self.profile_contacts[self._current_to.public_key]['last_view'] = msgs[len(msgs) - 1].created_at

        self._display.update_messages()

    def set_view_profile(self, p):
        """
        :param p: key or profile obj
        :return:
        """
        if isinstance(p, str):
            p = self._get_profile(p, create_type='public')

        # nothing to do if we're already msging and setting view to profile we're using not allowed
        if p != self._current_to and p != self._profile:
            # add to contacts if not already there
            self.add_contact(p.public_key)
            self._current_to = p
            self._draw_messages()
            self._draw_contacts()

    def set_from_profile(self, p: Profile):
        self._profile = p
        self._contacts = {}

        # to back to nothing
        self._current_to = None

        # update display for this new profile
        self._draw_messages()
        self._draw_contacts()
        self._display.update_title()

    @property
    def profile(self) -> Profile:
        # profile we're currently logged in as, the from profile
        return self._profile

    @property
    def profile_threads(self) -> MessageThreads:
        # threads for the currently logged in profile
        if self.profile.public_key not in self._threads:
            # creates new thread if we don't already have it for this profile
            self._threads[self.profile.public_key] = MessageThreads(from_p=self._profile,
                                                                    evt_store=self._event_store,
                                                                    on_message=self._new_message,
                                                                    kinds=self._kind)

        return self._threads[self.profile.public_key]

    @property
    def profile_contacts(self):
        if self.profile.public_key not in self._contacts:
            to_add = self._contacts[self.profile.public_key] = {}
            # make the intial list by looking at what messages we've received
            for c_key in self.profile_threads.messaged():
                if c_key not in self._contacts:
                    to_add[c_key] = {
                        'last_view': None
                    }

        return self._contacts[self.profile.public_key]

    def add_contact(self, pub_k):
        # add contact for the profile we're currently using
        if pub_k not in self.profile_contacts:
            self.profile_contacts[pub_k] = {
                'last_view': None
            }

    @property
    def view_profile(self) -> Profile:
        # msgs we're viewing and where any post will be sent, the to profile
        return self._current_to

    def get_profile_lookup(self) -> ProfileList:
        # obj that gives us a way to look up profiles as we currently know them
        return self._profiles.profiles

    @property
    def messages(self):
        # this will return msgs between current from/to profiles
        # at the moment we recreate threads on switching profile
        return self.profile_threads.messages(self._current_to.public_key,
                                             kind=self._kind)

    def get_local_profiles(self):
        # profiles where we have a private key, i.e. we can make posts
        ret = [pp for pp in self._profiles.profiles if pp.private_key]
        return ret

    def _get_profile(self, as_profile, create_type=None):
        # if str maybe its a profile_name, privkey or pubkey
        ret = None

        # we were handed a profile obj so everything is probably cool...
        if isinstance(as_profile, Profile):
            ret = as_profile
        # ok assuming we have a db lets see if we can find this profile
        elif isinstance(as_profile, str) and self._profiles:
            ret = self._profiles.profiles.lookup_priv_key(as_profile)
            if not ret:
                ret = self._profiles.profiles.lookup_profilename(as_profile)
            if not ret:
                ret = self._profiles.profiles.lookup_pub_key(as_profile)

        # we didn't find a profile but we'll see if we can just use as priv key...
        # also fallback we don't have db
        if not ret and create_type is not None:
            if len(as_profile) == 64:
                # and also hex, will throw otherwise
                bytearray.fromhex(as_profile)
                if create_type == 'private':
                    ret = Profile(priv_k=as_profile,
                                  profile_name='adhoc_user')
                elif create_type == 'public':
                    ret = Profile(pub_k=as_profile)

        return ret

    def start(self):
        try:
            self._display.run()
        except Exception as e:
            logging.debug(e)

