# copied from https://kivymd.readthedocs.io/en/latest/themes/icon-definitions/index.html
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.screenmanager import Screen

from kivymd.icon_definitions import md_icons
from kivymd.app import MDApp
from kivymd.uix.list import TwoLineAvatarIconListItem
from nostr.ident import Profile
from nostr.util import util_funcs

Builder.load_string(
"""
#:import images_path kivymd.images_path

<SearchContactScreen>

    MDBoxLayout:
        orientation: 'vertical'
        spacing: dp(10)
        padding: dp(20)

        MDBoxLayout:
            adaptive_height: True

            MDIconButton:
                icon: 'magnify'

            MDTextField:
                id: search_field
                hint_text: 'Search contact'
                on_text: root.set_selected(self.text)
                focus : True

        RecycleView:
            id: rv
            key_viewclass: 'viewclass'
            key_size: 'height'

            RecycleBoxLayout:
                padding: dp(10)
                default_size: None, dp(56)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'

<CustomAvatarTwoLineText>
    text: '?'
    secondary_text: '?'
    source: 'data/logo/kivy-icon-256.png'  
    ImageLeftWidget:
        source: root.source

<MessageItem>
    canvas.before:
        Color:
            rgba: 0, 1, 0, 0.5
        RoundedRectangle:
            size: self.size
            pos: self.pos
            radius: [55]  #---- This rounds the corners --- #
    
<MessageScreen>:
    BoxLayout:
        orientation: 'vertical'
        BoxLayout:
            size_hint : 1,0.2
            orientation: 'horizontal'
            MDIconButton:
                id: back_button
                icon : 'keyboard-backspace'
                on_press : root.back()
            ImageLeftWidget:
                id: contact_image
                source: 'data/logo/kivy-icon-256.png'
            MDLabel:
                id: msg_name_label
                text: '?'

        RecycleView:
            id: msg_rv
            key_viewclass: 'viewclass'
            key_size: 'height'

            RecycleBoxLayout:
                padding: dp(10)
                default_size: None, dp(56)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'

        BoxLayout:
            size_hint : 1,0.2
            MDTextField:
                id: message_text
                multiline: True
                hint_text: "message text"
                focus: True
            MDRoundFlatIconButton:
                text: 'send'
                on_press : root.send_pressed()     

"""
)

class CustomAvatarTwoLineText(TwoLineAvatarIconListItem):
    def __init__(self, **kargs):
        super().__init__(**kargs)

from kivymd.uix.label import MDLabel

class MessageItem(MDLabel):
    def __init__(self, **kargs):
        super().__init__(**kargs)


class SearchContactScreen(Screen):

    def __init__(self, contact_selected, **kargs):
        self._profiles = None
        self._contact_selected = contact_selected
        super().__init__(**kargs)

    def set_selected(self, text=""):
        '''Builds a list of icons for the screen MDIcons.'''

        # not yet loaded
        if self._profiles is None:
            return

        def add_profile_item(p: Profile):

            def get_press(for_p):
                def my_press():
                    self._contact_selected(p)
                return my_press

            to_add = {
                'viewclass': "CustomAvatarTwoLineText",
                'secondary_text': p.public_key,
                'text': '?',
                'source': 'data/logo/kivy-icon-256.png',
                'on_press': get_press(p)
            }
            if p.name:
                to_add['text'] = p.name
            if p.get_attr('picture'):
                to_add['source'] = p.get_attr('picture')


            self.ids.rv.data.append(to_add)

        self.ids.rv.data = []
        for c_p in self._profiles.matches(text):
            add_profile_item(c_p)

    def set_profiles(self, profiles):
        self._profiles = profiles
        self.set_selected(self.ids.search_field.text)


class MessageScreen(Screen):
    def __init__(self, on_back, on_message, **kargs):
        super().__init__(**kargs)
        self._msg_label = self.ids.msg_name_label
        self._img = self.ids.contact_image
        self._to_profile = None
        self._on_back = on_back
        self._on_message = on_message


    def set_converstion(self, p: Profile):
        self._to_profile = p
        name = '?'
        if p.name:
            name = p.name
            key = util_funcs.str_tails(p.public_key)
        else:
            key = p.public_key
        self._msg_label.text = '%s/%s' % (name, key)

        pic = 'data/logo/kivy-icon-256.png'
        if p.get_attr('picture'):
            pic = p.get_attr('picture')
        self._img.source = pic

    def add_message(self, message_text):
        """
            adds message text to message con
        """

        to_add = {
            'viewclass' : 'MessageItem',
            'text' : message_text
        }

        self.ids.msg_rv.data.append(to_add)

    def back(self):
        self._on_back()

    def send_pressed(self):
        msg_text = self.ids.message_text.text
        self.ids.message_text.text = ''

        self._on_message(text=msg_text,
                         to_profile=self._to_profile)

        self.add_message(msg_text)