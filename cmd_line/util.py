from __future__ import annotations
from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from nostr.ident.profile import

from nostr.event import Event
from app.post import PostApp
from nostr.ident.profile import ProfileList, ProfileEventHandler, Profile
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText


class EventPrinter:

    def __init__(self,
                 profile_handler: ProfileEventHandler,
                 as_user: Profile = None,
                 inbox_keys=None,
                 share_keys=None):

        self._profile_handler = profile_handler
        self._as_user = as_user
        self._inbox_keys = inbox_keys
        if inbox_keys is None:
            self._inbox_keys = []
        self._share_keys = share_keys
        if share_keys is None:
            self._share_keys = []

    def print_event(self, evt: Event):
        self.print_event_header(evt)
        self.print_event_content(evt)

    def print_event_header(self,
                           evt: Event,
                           depth=0):
        p: Profile

        ret_arr = []
        p = self._profile_handler.profiles.get_profile(evt.pub_key,
                                                       create_type=ProfileList.CREATE_PUBLIC)
        depth_align = ''.join(['\t'] * depth)
        ret_arr.append('%s-- %s --' % (depth_align, p.display_name()))

        to_list = []
        for c_pk in evt.p_tags:
            to_list.append(self._profile_handler.profiles.get_profile(c_pk,
                                                                      create_type=ProfileList.CREATE_PUBLIC).display_name())
        if to_list:
            ret_arr.append('%s-> %s' % (depth_align, to_list))

        ret_arr.append('%s%s@%s' % (depth_align, evt.id, evt.created_at))

        print('\n'.join(ret_arr))

    def print_event_content(self, evt: Event):

        def nip_decode(the_evt: Event):
            pub_key = evt.p_tags[0]
            if pub_key == self._as_user.public_key:
                pub_key = evt.pub_key

            return evt.decrypted_content(self._as_user.private_key, pub_key)

        if evt.kind == Event.KIND_TEXT_NOTE:
            print(evt.content)
        elif evt.kind == Event.KIND_ENCRYPT:
            content = evt.content
            try:
                # basic NIP4 encrypted event from/to us
                if evt.pub_key == self._as_user.public_key or self._as_user.public_key in evt.p_tags:
                    content = nip_decode(evt)
                # clust style wrapped NIP4 event
                elif evt.pub_key in self._inbox_keys:
                    evt = PostApp.clust_unwrap_event(evt, self._as_user, self._share_keys)
                    if evt:
                        self.print_event_header(evt, depth=1)
                        content = '\t' + nip_decode(evt)
            except:
                pass

            print(content)


class FormattedEventPrinter:

    def __init__(self,
                 profile_handler: ProfileEventHandler,
                 as_user: Profile = None,
                 inbox_keys=None,
                 share_keys=None):

        self._profile_handler = profile_handler
        self._as_user = as_user
        self._inbox_keys = inbox_keys
        if inbox_keys is None:
            self._inbox_keys = []
        self._share_keys = share_keys
        if share_keys is None:
            self._share_keys = []

        self._as_user_color = 'green'
        self._other_user_key = 'green'
        self._full_keys = False

    def print_event(self, evt: Event):
        self.print_event_header(evt)
        self.print_event_content(evt)

    def _get_profile(self, key):
        return self._profile_handler.profiles.get_profile(key,
                                                        create_type=ProfileList.CREATE_PUBLIC)

    def _is_user(self, key):
        return self._as_user is not None and self._as_user.public_key == key

    def print_event_header(self,
                           evt: Event,
                           depth=0):
        p: Profile

        txt_arr = []
        depth_align = ''.join(['\t'] * depth)
        txt_arr.append(('', '\n%s--- ' % depth_align))
        create_p = self._get_profile(evt.pub_key)
        style = 'FireBrick bold'
        if self._is_user(evt.pub_key):
            style = 'green bold'

        txt_arr.append((style, create_p.display_name()))
        if self._full_keys and create_p.name and not create_p.profile_name:
            txt_arr.append(('', '[%s]' % create_p.public_key))

        txt_arr.append(('',' ---'))

        to_list = []
        for c_pk in evt.p_tags:
            style = ''
            if self._is_user(c_pk):
                style = 'bold ForestGreen'
            to_p = self._get_profile(c_pk)
            if not self._full_keys:
                to_list.append((style, to_p.display_name()))
            else:
                if to_p.name or to_p.profile_name:
                    to_list.append((style, to_p.display_name()))
                to_list.append(('', '[%s]' % to_p.public_key))

        if to_list:
            txt_arr.append(('', '\n%s-> ' % depth_align, ))
            txt_arr = txt_arr + to_list

        # if to_list:
        #     ret_arr.append('%s-> %s' % (depth_align, to_list))
        #
        # ret_arr.append('%s%s@%s' % (depth_align, evt.id, evt.created_at))
        txt_arr.append(('','\n%s' % depth_align))
        txt_arr.append(('cyan', evt.id))
        txt_arr.append(('','@'))
        txt_arr.append(('', '%s' % evt.created_at))

        print_formatted_text(FormattedText(txt_arr))

    def print_event_content(self, evt: Event):

        def nip_decode(the_evt: Event):
            pub_key = evt.p_tags[0]
            if pub_key == self._as_user.public_key:
                pub_key = evt.pub_key

            return evt.decrypted_content(self._as_user.private_key, pub_key)

        if evt.kind == Event.KIND_TEXT_NOTE:
            print(evt.content)
        elif evt.kind == Event.KIND_ENCRYPT:
            style = ''
            content = evt.content
            try:
                # basic NIP4 encrypted event from/to us
                if evt.pub_key == self._as_user.public_key or self._as_user.public_key in evt.p_tags:
                    content = nip_decode(evt)
                # clust style wrapped NIP4 event
                elif evt.pub_key in self._inbox_keys:
                    evt = PostApp.clust_unwrap_event(evt, self._as_user, self._share_keys)
                    if evt:
                        print('wrapped evt-->')
                        self.print_event_header(evt, depth=1)
                        content = '\t' + nip_decode(evt)
            except:
                style = 'gray'
                pass

            print_formatted_text(FormattedText([(
                style, content
            )]))

