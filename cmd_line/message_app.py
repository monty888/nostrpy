import os
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window, VSplit
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.key_binding import KeyBindings
from nostr.ident import Profile
from nostr.event import Event

class MessageApp:
    """
        interface for a simple 1 page app for viewing messages in the terminal
        using python prompt-toolkit
    """
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