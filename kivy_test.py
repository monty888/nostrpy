"""
test area for the kivy components we need (aswell as to test that are underlying nostr client components
do what we need) going to write a encrypted nostr chat app

we'll need
address/profile search      -   for adding people to chat to
relay details               -   whre chats are to be posted/ we'll subscribe to get replies

basic encrypted type 4 messages
1 to 1 chat


further dev
wrapped encrypt as clust
group chat via mutiple posts, using clust it might be possible that only orignator know who everyone is...



"""
import time

from kivymd.app import MDApp
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import Screen
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRectangleFlatButton

# importing all necessary modules
# like MDApp, MDLabel Screen, MDTextField
# and MDRectangleFlatButton
from kivymd.app import MDApp
from kivy.clock import Clock
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import Screen
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRectangleFlatButton
from kivy.lang.builder import Builder
from kivymd.uix.list import OneLineListItem, TwoLineListItem, \
    OneLineAvatarIconListItem, TwoLineAvatarIconListItem, ImageLeftWidget
from kivy.uix.screenmanager import ScreenManager

from nostr.ident import ProfileEventHandler, ProfileList, Profile
from nostr.client.client import Client
from db.db import SQLiteDatabase
from nostr.util import util_funcs

DB = SQLiteDatabase('/home/shaun/.nostrpy/nostr-client.db')

Builder.load_string("""
<MyContactScreen>:
    BoxLayout:
        orientation: "vertical"
        MDTextField:
            hint_text: "search profiles"
            focus: True
            id: psearch
        ScrollView:
            id: scroll
            MDList:
                id: container
                
<MessageScreen>:
    BoxLayout:
        orientation: "vertical"
        MDLabel:
            id: msg_name_label
            text: "name of conversation"
        ScrollView:
            id: scroll
            MDList:
                id: msg_con
        MDTextField:
            hint_text: "type here"     
""")


class MyContactScreen(Screen):

    def __init__(self, **kargs):
        self._peh = None
        self._started = False

        # timer for partial list redraws, cancel when start new draw
        self._draw_timer = None
        # current search text
        self._search_text = ''
        # list container for profile matches
        self._list_con = None

        self._max_draw = 20
        super().__init__(**kargs)
        # check why having to call self, thought this was called for you?
        self.build()

    def build(self):

        self._started = True
        def on_search_change(instance, value):
            self._search_text = value
            self.draw_matches(0.2)



        self.ids.psearch.bind(text=on_search_change)
        self._list_con = self.ids.container

        self._scroll_con = self.ids.scroll

    def draw_matches(self, delay=None):
        profiles: ProfileList
        if not self._peh:
            return

        profiles = self._peh.profiles.matches(self._search_text)

        to_draw = len(profiles)
        if to_draw>self._max_draw:
            to_draw = self._max_draw

        c_pos = 0
        parts = 2
        self._scroll_con.scroll_y = 1
        if self._draw_timer:
            self._draw_timer.cancel()
            self._list_con.clear_widgets()

        def draw_part(dt):
            def my_touch_down(item):
                # work on multi select for group convs
                if self._contact_selected:
                    p = self._peh.profiles.lookup(item.secondary_text)
                    self._contact_selected(p)

            nonlocal c_pos, parts, to_draw, profiles
            c_p: Profile

            for i in range(c_pos,c_pos+parts):
                if i >= to_draw:
                    break
                try:
                    c_p = profiles[i]
                    pic = c_p.get_attr('picture')
                    name = c_p.name
                    if not name:
                        name = '?'


                    item = TwoLineAvatarIconListItem(text=name,
                                                     secondary_text=c_p.public_key)
                    if pic:
                        item.ids._left_container.add_widget(ImageLeftWidget(source=pic))
                        # bad image??

                    self._list_con.add_widget(
                        item
                    )
                    item.bind(on_press=my_touch_down)

                except:
                    print('we are having to surpress something')
                    pass

            # more to draw?
            c_pos=i+1
            if c_pos < to_draw:
                self._draw_timer = Clock.schedule_once(draw_part, 0.05)



        draw_part(delay)


        # for i in range(20):
        #     self.root.ids.container.add_widget(
        #         OneLineListItem(text=f"Single-line item {i}")
        #     )

    def connect(self, the_client):
        def do_draw(dt):
            self.draw_matches()

        def my_update(evt_profile, c_profile):
            """
            this might be done by updating inplace but for now we just redraw the lot
            :param evt_profile:
            :param c_profile:
            :return:
            """
            if self._draw_timer:
                self._draw_timer.cancel()

            self._draw_timer = Clock.schedule_once(do_draw, 0.3)

        self._peh = ProfileEventHandler(DB, on_update=my_update)

        the_client.subscribe(handlers=self._peh)
        # can we do this better....
        while not self._started:
            print('wait start')
            time.sleep(0.1)

        Clock.schedule_once(do_draw, 0)

    def set_contact_selected(self, sel_func):
        self._contact_selected = sel_func



class MessageScreen(Screen):
    def __init__(self, **kargs):
        super().__init__(**kargs)
        self._msg_label = self.ids.msg_name_label

    def set_converstion(self, p: Profile):
        name = '?'
        if p.name:
            name = p.name
            key = util_funcs.str_tails(p.public_key)
        else:
            key = p.public_key

        self._msg_label.text = '%s/%s' % (name, key)




class Demo(MDApp):

    def __init__(self, **kargs):
        self._scr_man = None
        self._con_sel_screen = None

        super().__init__(**kargs)

    def build(self):
        self._scr_man = ScreenManager()

        self._con_sel_screen = MyContactScreen(name='contact_select')
        self._con_sel_screen.set_contact_selected(self.contact_selected)
        self._scr_man.add_widget(self._con_sel_screen)

        self._msg_screen = MessageScreen(name='message_screen')
        self._scr_man.add_widget(self._msg_screen)

        return self._scr_man

    def contact_selected(self, pub_keys):
        self._msg_screen.set_converstion(pub_keys)
        self._scr_man.current = 'message_screen'

    def connect(self, the_client):
        while not self._con_sel_screen:
            time.sleep(0.1)

        self._con_sel_screen.connect(the_client)



def test_select_contact():
    """
    at most basic the select contact screen needs to have a search and allow selection of a single contact
    contacts should be autosync to most recent profiles (use nostr.profiles)
    """
    from nostr.client.persist import Store
    # s = Store('/home/shaun/.nostrpy/nostr-client.db')
    # s.destroy()
    # s.create()

    my_app = Demo()

    c = Client('ws://localhost:8082/', on_connect=my_app.connect).start()

    my_app.run()
    c.end()

if __name__ == "__main__":
    test_select_contact()