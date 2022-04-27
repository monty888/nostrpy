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
from datetime import datetime, timedelta
from nostr.ident import ProfileEventHandler, ProfileList, Profile
from nostr.client.client import Client
from nostr.client.event_handlers import PersistEventHandler
from db.db import SQLiteDatabase
from kivy_components.screens import SearchContactScreen, MessageScreen
from nostr.event import Event
from nostr.util import util_funcs
from nostr.client.persist import SQLLiteEventStore

DB = SQLiteDatabase('/home/shaun/.nostrpy/nostr-client.db')

class Demo(MDApp):

    def __init__(self, **kargs):
        self._scr_man = None
        self._con_sel_screen = None
        self._client = None
        self._store = SQLLiteEventStore(DB.file)

        self._c_profile = Profile.load_from_db(DB,'firedragon888')

        # get current profiles and track any changes
        def my_update(evt_p, old_p):
            pass
        self._peh = ProfileEventHandler(DB, on_update=my_update)
        super().__init__(**kargs)

    def build(self):
        self._scr_man = ScreenManager()

        self._con_sel_screen = SearchContactScreen(name='contact_select', contact_selected=self.contact_selected)
        # self._con_sel_screen.set_contact_selected(self.contact_selected)
        self._scr_man.add_widget(self._con_sel_screen)

        def ret_contact_search():
            self._scr_man.current = 'contact_select'

        def do_message(text, to_profile):

            n_event = Event(kind=Event.KIND_TEXT_NOTE,
                            content=text,
                            pub_key=self._c_profile.public_key,
                            tags=[
                                '#p', to_profile.public_key
                            ])
            n_event.sign(self._c_profile.private_key)
            self._client.publish(n_event)


        self._msg_screen = MessageScreen(name='message_screen',
                                         on_back=ret_contact_search,
                                         on_message=do_message)
        self._scr_man.add_widget(self._msg_screen)

        self._con_sel_screen.set_profiles(self._peh.profiles)
        return self._scr_man

    def contact_selected(self, p: Profile):
        self._msg_screen.set_converstion(p)
        self._scr_man.current = 'message_screen'

    def connect(self, the_client):
        self._client = the_client
        while not self._con_sel_screen:
            time.sleep(0.1)

        # TODO: to store add method to get the latest tick for event matching filter
        the_client.subscribe(handlers=self._peh, filters={
            'kinds': Event.KIND_META
            # 'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=1))
        })


        the_client.subscribe(handlers=PersistEventHandler(self._store), filters={
            'kinds': Event.KIND_TEXT_NOTE,
            'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=1))
        })


def test_select_contact():
    """
    at most basic the select contact screen needs to have a search and allow selection of a single contact
    contacts should be autosync to most recent profiles (use nostr.profiles)
    """
    # s = Store('/home/shaun/.nostrpy/nostr-client.db')
    # s.destroy()
    # s.create()

    my_app = Demo()

    c = Client('ws://localhost:8082/', on_connect=my_app.connect).start()

    my_app.run()
    c.end()


if __name__ == "__main__":
    test_select_contact()
