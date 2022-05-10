"""
    prompt_toolkit front end to from app.post import PostApp

"""
import logging

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, ScrollablePane
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from nostr.ident.profile import ProfileEventHandler
from nostr.event.event import Event
from nostr.util import util_funcs
from app.post import PostApp
import os


class PostAppGui:

    def __init__(self,
                 post_app: PostApp,
                 profile_handler: ProfileEventHandler):
        # gui parts
        self._post_app = post_app
        self._profile_handler = profile_handler
        self._app = None
        self._msg_split_con = HSplit([])
        self._msg_scroll_con = ScrollablePane(self._msg_split_con)
        self._make_gui()
        self._post_app.set_on_message(self._on_msg)
        self._msg_display_height = 0

    def _make_gui(self):
        kb = KeyBindings()
        buffer1 = Buffer()

        self._make_msg_split()
        self._scroll_bottom()
        root_con = HSplit([
            self._msg_scroll_con,
            Window(content=BufferControl(buffer1), height=3)
        ])
        my_layout = Layout(root_con)

        # ctrl-q to quit, also type exit
        @kb.add('c-q')
        def exit_(event):
            self._app.exit()

        @kb.add('c-up')
        def do_up(e):
            pos = self._msg_scroll_con.vertical_scroll-1
            if pos < 0:
                pos = 0
            self._msg_scroll_con.vertical_scroll = pos

        @kb.add('c-down')
        def do_down(e):
            pos = self._msg_scroll_con.vertical_scroll

            if (self._msg_display_height + 3 - pos) > os.get_terminal_size().lines:
                pos += 1

            self._msg_scroll_con.vertical_scroll = pos

        @kb.add('c-s')
        def post_(event):
            msg = buffer1.text
            if msg.replace(' ', ''):

                if self._post_app.connection_status:
                    self._post_app.do_post(msg)
                else:
                    'in someway make user aware that we dont have a connection to relay...'
                    pass

                buffer1.text = ''

        self._app = Application(full_screen=True,
                                layout=my_layout,
                                key_bindings=kb)

    def _scroll_bottom(self):

        pos = self._msg_scroll_con.vertical_scroll
        d_h = os.get_terminal_size().lines
        if self._msg_display_height + 3 - pos > d_h:
            pos = (self._msg_display_height + 3) - d_h
        self._msg_scroll_con.vertical_scroll = pos

    def draw_messages(self):
        self._make_msg_split()
        self._app.invalidate()
        self._scroll_bottom()

    def _on_msg(self, evt):
        self.draw_messages()

    def _make_msg_split(self):
        """
        make up the components to display the posts on screen
        note that though that though we can only send post of type encrypt/plaintext dependent
        on start options, here the view will show both and user won't can't tell the difference.
        Probably should only show encrypt if in encrypt and vice versa

        :return:
        """
        c_m: Event
        to_add = []

        as_user = self._post_app.as_user
        self._msg_display_height = 0
        for c_m in self._post_app.message_events:
            content = c_m.content

            prompt_col = 'red'
            content_col = ''
            if c_m.pub_key == as_user.public_key:
                prompt_col = 'green'
            if not self._post_app.connection_status:
                content_col = prompt_col = 'gray'

            if c_m.kind == Event.KIND_ENCRYPT:
                priv_key = as_user.private_key
                use_pub_key = c_m.p_tags[0]

                # its a message to us
                if c_m.pub_key != as_user.public_key:
                    use_pub_key = c_m.pub_key

                try:
                    content = c_m.decrypted_content(priv_key, use_pub_key)
                except Exception as e:
                    # currently in the case of group messages we'd expect this except on those we create
                    # and the 1 msg that was encrypted for us... we can't tell which that is until we try to decrypt
                    content = None
                    # content = str(e)

            if content:
                msg_height = len(content.split('\n'))
                if self._profile_handler:
                    msg_profile = self._profile_handler.profiles.lookup_pub_key(c_m.pub_key)

                prompt_user_text = util_funcs.str_tails(c_m.pub_key, 4)
                if msg_profile:
                    prompt_user_text = msg_profile.display_name()

                to_add.append(
                    HSplit([
                        Window(FormattedTextControl(text=[(prompt_col, '%s@%s' % (prompt_user_text, c_m.created_at))]),
                               height=1),
                        Window(FormattedTextControl(text=[(content_col,content)]), height=msg_height)
                    ])

                )
                self._msg_display_height += msg_height + 1

        self._msg_split_con.children = to_add


    def run(self):
        self._app.run()

