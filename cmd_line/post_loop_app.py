"""
    Fullscreen command line app for making a series of posts.

"""
import json
import logging
import hashlib
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, ScrollablePane
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from collections import OrderedDict
from nostr.ident.profile import Profile, ProfileEventHandler
from nostr.ident.persist import TransientProfileStore, ProfileStoreInterface
from nostr.event import Event
from nostr.util import util_funcs
from nostr.encrypt import SharedEncrypt


class PostApp:

    def __init__(self,
                 use_relay,
                 as_user: Profile,
                 to_users: [Profile],
                 public_inbox: Profile = None,
                 subject=None,
                 is_encrypt=True
                 ):
        """
        :param as_user:     posts made as this user
        :param to_users:    posts will be made to these users, required if doing encrypted posts but can be set to None
                            when is_encrypt is False - in this case you'll just be in broadcast sending posts out
        :param public_inbox: if set then posts will be wrapped and sent via this inbox which all users will need the
                            private key to, as CLUST see ....
        :param subject:     subject tag will be added to msgs and used as a filter also to see replies
        :param is_encrypt:  if true then NIP4 encoded

        TODO: we should probably do some checking on init values, at the moment we're expecting th ecaller to do

        """
        self._client = use_relay
        self._as_user = as_user
        self._to_users = to_users
        self._chat_members = self._create_chat_members()
        self._public_inbox = None
        self._shared_keys = None
        self._set_public_inbox(public_inbox)

        self._subject = subject
        self._is_encrypt = is_encrypt

        # de-duplicating of events for when we're connected to multiple relays
        self._duplicates = OrderedDict()
        self._max_dedup = 1000

        # all the mesages we've seen, if since and event store then may be some from before we started
        self._msg_events = []
        self._on_msg = None

    def _create_chat_members(self):
        ret = set([self._as_user.public_key])

        if self._to_users:
            ret = ret.union(set([p.public_key for p in self._to_users]))
        ret = list(ret)
        ret.sort()
        return ret

    @staticmethod
    def _get_shared(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def _set_public_inbox(self, public_inbox):
        self._public_inbox = public_inbox
        if public_inbox is None:
            self._public_shared_encrypt = None
            self._shared_keys = None
        else:
            se = SharedEncrypt(self.as_user.private_key)

            self._shared_keys = [self._get_shared(se.derive_shared_key(self._as_user.public_key))]
            if self._to_users:
                self._shared_keys = self._shared_keys + [self._get_shared(se.derive_shared_key(p.public_key))
                                                         for p in self._to_users]

    def _is_chat(self, msg: Event):
        """
        is this msg part of the chat we're looking at, currently this is just made
        up by have all the correct members in it, so if all the members are the same
        then you're looking in that group...
        TODO: look at proper group chat NIP and implement

        :param msg:
        :return:
        """

        msg_members = list(set([msg.pub_key]).union(msg.p_tags))
        msg_members.sort()

        is_subject = True
        if self._subject and msg.get_tags('subject'):
            is_subject = self._subject in [s[0] for s in msg.get_tags('subject')]

        return self._chat_members == msg_members and is_subject or (self._is_encrypt is False and self._to_users is None)

    def do_event(self, sub_id, evt: Event, relay):
        # we likely to need to do this on all event handlers except those that would be
        # expected to deal with duplciates themselves e.g. persist
        if evt.id not in self._duplicates:
            self._duplicates[evt.id] = True
            if len(self._duplicates) >= self._max_dedup:
                self._duplicates.popitem(False)


            # unwrap if evt is shared
            if self._public_inbox:
                shared_tags = evt.get_tags('shared')
                if shared_tags and shared_tags[0][0] in self._shared_keys:
                    for c_member in self._chat_members:
                        try:
                            content = evt.decrypted_content(self._as_user.private_key, c_member)
                            evt = Event.create_from_JSON(json.loads(content))
                            break
                        except Exception as e:
                            pass

            if self._is_chat(evt):
                self._msg_events.append(evt)
                if self._on_msg:
                    self._on_msg(evt)

    def set_on_message(self, callback):
        self._on_msg = callback

    def do_post(self, msg):
        for evt in self.make_post(msg):
            self._client.publish(evt)

    def make_post(self, msg) -> Event:
        """
        makes post events, a single event if plaintext or 1 per to_user if encrypted
        :param public_inbox:
        :param as_user:
        :param msg:
        :param to_users:
        :param is_encrypt:
        :param subject:
        :return:
        """
        tags = [['p', p.public_key] for p in self._to_users]

        if self._subject is not None:
            tags.append(['subject', self._subject])

        if not self._is_encrypt:
            evt = Event(kind=Event.KIND_TEXT_NOTE,
                        content=msg,
                        pub_key=self._as_user.public_key,
                        tags=tags)

            evt.sign(self._as_user.private_key)
            post = [evt]
        else:
            post = []
            for c_post in tags:
                if c_post[0] == 'subject':
                    continue
                evt = Event(kind=Event.KIND_ENCRYPT,
                            content=msg,
                            pub_key=self._as_user.public_key,
                            tags=tags)
                evt.content = evt.encrypt_content(priv_key=self._as_user.private_key,
                                                  pub_key=c_post[1])
                evt.sign(self._as_user.private_key)

                if self._public_inbox:
                    evt = self._inbox_wrap(evt,
                                           to_pub_k=c_post[1])

                post.append(evt)

        return post

    def _inbox_wrap(self, evt, to_pub_k):

        se = SharedEncrypt(self._as_user.private_key)
        se.derive_shared_key(to_pub_k)

        evt = Event(kind=Event.KIND_ENCRYPT,
                    content=json.dumps(evt.event_data()),
                    pub_key=self._public_inbox.public_key,
                    tags=[
                        ['shared', self._get_shared(se.shared_key())]
                    ])
        # evt.content = evt.encrypt_content(self._public_inbox.private_key, to_pub_k)
        evt.content = evt.encrypt_content(self._as_user.private_key, to_pub_k)
        evt.sign(self._public_inbox.private_key)
        return evt


    @property
    def message_events(self):
        return self._msg_events

    @property
    def as_user(self) -> Profile:
        return self._as_user

    @property
    def connection_status(self):
        return self._client.connected


class PostAppGui:

    def __init__(self,
                 post_app: PostApp,
                 profile_handler: ProfileEventHandler):
        # gui parts
        self._post_app = post_app
        self._profile_handler = profile_handler
        self._app = None
        self._msg_split_con = HSplit([])
        self._make_gui()
        self._post_app.set_on_message(self._on_msg)

    def _make_gui(self):
        kb = KeyBindings()
        buffer1 = Buffer()

        self._make_msg_split()
        root_con = HSplit([
            ScrollablePane(self._msg_split_con),
            Window(content=BufferControl(buffer1), height=3)
        ])
        my_layout = Layout(root_con)

        # ctrl-q to quit, also type exit
        @kb.add('c-q')
        def exit_(event):
            self._app.exit()

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

    def draw_messages(self):
        self._make_msg_split()
        self._app.invalidate()

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

        for c_m in self._post_app.message_events:
            content = c_m.content

            color = 'red'
            if c_m.pub_key == as_user.public_key:
                color = 'green'
            if not self._post_app.connection_status:
                color = 'gray'

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
                        Window(FormattedTextControl(text=[(color, '%s@%s' % (prompt_user_text, c_m.created_at))]),
                               height=1),
                        Window(FormattedTextControl(text=content), height=msg_height)
                    ])

                )

        self._msg_split_con.children = to_add

    def run(self):
        self._app.run()

