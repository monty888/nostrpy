import logging
import os
import time

from abc import abstractmethod
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window, VSplit, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import FloatContainer, Float
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.widgets import VerticalLine, Button,TextArea, HorizontalLine, Dialog, \
    SearchToolbar, Frame, RadioList
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
from prompt_toolkit.mouse_events import MouseEvent,MouseButton, MouseEventType
from nostr.ident import Profile, ProfileEventHandler, UnknownProfile
from nostr.client.event_handlers import PersistEventHandler
from nostr.event import Event
from nostr.client.persist import SQLStore
from nostr.client.messaging import MessageThreads
from nostr.util import util_funcs
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

    def __init__(self, app: Application, on_close=None):

        # inputs/widget
        # text area input contact search
        self._search_in = None

        super().__init__(title='start messaging contact',
                         app=app,
                         on_close=on_close)

    def create_content(self):
        self._search_in = TextArea(width=32)
        self._content = HSplit(children=[
                self._search_in,
                Window(content=FormattedTextControl(text='findings!!!!'))
            ],
            key_bindings=self._kb)


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


class ChatGui:
    """
        interface for a simple 1 page app for viewing messages in the terminal
        using python prompt-toolkit
    """
    def __init__(self, chat_app):

        # app logic
        self._chat_app = chat_app

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
        self._p_switch_dialog = SwitchProfileDialog(self._app,
                                                    on_close=self._focus_prompt,
                                                    on_profile_change=self._chat_app.set_from_profile)

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
        self._title['update'](self._chat_app.profile)

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
        my_con = FormattedTextControl('')
        my_win = Window(
            height=1,
            content=my_con,
            align=WindowAlign.CENTER
        )

        def switch_profile(e):
            if is_left_click(e):

                self._p_switch_dialog.show(from_p=self._chat_app.profile,
                                           all_profiles=self._chat_app.get_local_profiles())

        def update(from_p: Profile):
            profile_text = '<no profile>'
            if from_p:
                profile_text = self._chat_app.profile.display_name(with_pub=True)

            child_arr = [
                ('', 'Nostrpy CLI message v0.1, user: '),
                ('green', profile_text, switch_profile)
            ]
            my_con.text = child_arr

        return {
            'title_con': my_win,
            'update': update
        }

    def update_title(self):
        self._title['update'](self._chat_app.profile)

    def _create_nav_pane(self):
        def new_contact():
            self._new_contact_dialog.show()

        self._new_contact_dialog = SearchContactDialog(self._app, on_close=self._focus_prompt)

        self._nav_contacts = HSplit([])
        self._nav_controls = HSplit([
            Button(text='new contact', handler=new_contact),
            Button(text='relays'),
            Button(text='switch user')
        ])

        self._nav_pane = HSplit([
            ScrollablePane(content=self._nav_contacts),
            HorizontalLine(),
            self._nav_controls
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
        # we store we only have to subscribe for event since we have local
        self._event_store = None

        if self._db:
            # we'll want to listen eventually and add as handler to client sub
            self._profiles = ProfileEventHandler(db, None)
            # TODO: we'll need to create a transient version now we can switch profiles,
            #  else
            self._event_store = SQLStore(self._db)

        self._profile = self._get_profile(as_profile,
                                          key_type='private')

        if not self._profile or not self._profile.private_key:
            raise UnknownProfile('unable to find profile %s or we don\'t have the private key for it')
        logging.debug('starting chat app using profile: %s' % self._profile)

        # standard txt or encrypted, to add wrapped inbox
        self._kind = kind

        # init gui
        self._display = ChatGui(chat_app=self)

        # track messages for my profile
        self._threads = MessageThreads(from_p=self._profile,
                                       evt_store=self._event_store,
                                       on_message=self._new_message,
                                       kinds=self._kind)

        # self._current_to = self._get_profile('3648e5c206883d9118d9c19a01ddde96059c5f46a89444b252e247ca9b9270e3')
        self._current_to = None
        # move to connect...
        self._contacts = {}
        self._update_contacts()
        self._draw_contacts()

        self._draw_messages()

        self._start_client()

    def _start_client(self):
        # at the moment we're passing in actual client obj, think better to pass in urls and create ourself

        def my_connect(the_client):
            handlers = [self]
            if self._event_store:
                handlers.append(PersistEventHandler(self._event_store))

            the_client.subscribe(handlers=handlers,
                                 filters=[
                                     {
                                         'kinds': self._kind,
                                         'authors': [
                                             self._profile.public_key
                                         ]
                                     },
                                     {
                                         'kinds': self._kind,
                                         '#p': [
                                             self._profile.public_key
                                         ]
                                     }
                                 ]
                                 )

        self._client.set_on_connect(my_connect)
        self._client.start()

    def do_event(self, sub_id, evt: Event, relay):
        self._threads.do_event(sub_id, evt, relay)

    def do_message(self, text):
        self._threads.post_message(the_client=self._client,
                                   from_user=self._profile,
                                   to_user=self._current_to,
                                   text=text,
                                   kind=self._kind)

    def _update_contacts(self):
        for c_key in self._threads.messaged():
            if c_key not in self._contacts:
                self._contacts[c_key] = {
                    'last_view': None
                }

        # in case wehere we start open with current to that we never msged before
        if self._current_to and self._current_to.public_key not in self._contacts:
            self._contacts[self._current_to.public_key] = {
                'last_view': None
            }

    def _draw_contacts(self):
        profiles = []
        for c_key in self._contacts:
            profiles.append({
                'profile': self._get_profile(c_key),
                'new_count': len(self._threads.messages(pub_k=c_key,
                                                        kind=self._kind,
                                                        since=self._contacts[c_key]['last_view'],
                                                        received_only=True))
            })

        self._display.set_contacts(profiles)

    def _new_message(self, msg: Event):
        if msg.pub_key not in self._contacts \
                or msg.get_tags('p')[0][0] not in self._contacts:
            self._update_contacts()

        # new message on profile we're looking at
        if self._current_to and msg.pub_key == self._current_to.public_key or msg.pub_key == self._profile.public_key:
            self._draw_messages()
        else:
            self._draw_contacts()

    def _draw_messages(self):
        if self._current_to:
            msgs = self._threads.messages(self._current_to.public_key,
                                          self._kind)
            if msgs:
                self._contacts[self._current_to.public_key]['last_view'] = msgs[len(msgs) - 1].created_at

        self._display.update_messages()

    def set_view_profile(self, p: Profile):
        if p != self._current_to:
            self._current_to = p
            self._draw_messages()
            self._draw_contacts()

    def set_from_profile(self, p: Profile):
        self._profile = p

        # change the msg thread/ maybe add multi profile support to message thread?
        self._threads = MessageThreads(from_p=self._profile,
                                       evt_store=self._event_store,
                                       on_message=self._new_message,
                                       kinds=self._kind)
        # to back to nothing
        self._current_to = None
        # contacts back to nothing and update for this profile
        self._contacts = {}
        self._update_contacts()

        # update display for this new profile
        self._draw_messages()
        self._draw_contacts()
        self._display.update_title()

    @property
    def profile(self):
        return self._profile

    @property
    def view_profile(self):
        return self._current_to

    @property
    def messages(self):
        return self._threads.messages(self._current_to.public_key,
                                      kind=self._kind)

    def get_local_profiles(self):
        # profiles where we have a provate key, i.e. we can make posts
        ret = [pp for pp in self._profiles.profiles if pp.private_key]
        return ret

    def _get_profile(self, as_profile, key_type='public'):
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
        if not ret:
            if len(as_profile) == 64:
                # and also hex, will throw otherwise
                bytearray.fromhex(as_profile)
                if key_type=='private':
                    ret = Profile(priv_k=as_profile,
                                  profile_name='adhoc_user')
                else:
                    ret = Profile(pub_k=as_profile)

        return ret

    def start(self):
        self._display.run()

