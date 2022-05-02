"""
    outputs evetns as they're seen from connected relays
"""

import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile, ProfileEventHandler, ProfileList
from nostr.ident.persist import SQLProfileStore, TransientProfileStore
from nostr.client.client import ClientPool, Client
from nostr.client.persist import SQLEventStore, TransientEventStore
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler
from nostr.util import util_funcs
from nostr.event import Event

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
EVENT_STORE = SQLEventStore(DB)
# EVENT_STORE = TransientEventStore()
PROFILE_STORE = SQLProfileStore(DB)
# RELAYS = ['wss://rsslay.fiatjaf.com','wss://nostr-pub.wellorder.net']
# RELAYS = ['wss://rsslay.fiatjaf.com']
RELAYS = ['ws://localhost:8081']


def usage():
    print("""
usage:

    """)
    sys.exit(2)


def _get_profile(key, peh, err_str):
    ret = peh.profiles.get_profile(key,
                                   create_type=ProfileList.CREATE_PRIVATE)
    if not ret:
        print(err_str)

    return ret


def make_post(as_user, msg, to_users, is_encrypt, subject=None) -> Event:
    """
    makes post events, a single event if plaintext or 1 per to_user if encrypted
    :param as_user:
    :param msg:
    :param to_users:
    :param is_encrypt:
    :param subject:
    :return:
    """
    tags = [['p', p.public_key] for p in to_users]

    if subject is not None:
        tags.append(['subject', subject])

    if not is_encrypt:
        evt = Event(kind=Event.KIND_TEXT_NOTE,
                    content=msg,
                    pub_key=as_user.public_key,
                    tags=tags)

        evt.sign(as_user.private_key)
        post = [evt]
    else:
        post = []
        for c_post in tags:
            if c_post[0] == 'subject':
                continue
            evt = Event(kind=Event.KIND_ENCRYPT,
                        content=msg,
                        pub_key=as_user.public_key,
                        tags=tags)
            evt.content = evt.encrypt_content(priv_key=as_user.private_key,
                                              pub_key=c_post[1])
            evt.sign(as_user.private_key)
            post.append(evt)

    return post


def do_post(relays, as_user, msg, to_users, is_encrypt, subject=None):
    done_count = 0

    def my_connect(the_client: Client):
        nonlocal done_count
        for c_post in make_post(as_user, msg, to_users, is_encrypt, subject):
            the_client.publish(c_post)
        done_count += 1

    my_clients = ClientPool(relays, on_connect=my_connect)
    my_clients.start()
    while done_count < len(my_clients):
        time.sleep(0.2)

    my_clients.end()


def show_post_info(as_user, msg, to_users, is_encrypt, subject):
    if msg is None:
        msg = '<no msg supplied>'
    just = 10
    print('from:'.rjust(just), as_user.display_name())
    if to_users:
        p: Profile
        print('to:'.rjust(just), [p.display_name() for p in to_users])

    if subject:
        print('subject:'.rjust(just), subject)

    enc_text = 'encrypted'
    if not is_encrypt:
        enc_text = 'plain_text'
    print('format:'.rjust(just), enc_text)

    print('%s\n%s\n%s' % (''.join(['-'] * 10),
                          msg,
                          ''.join(['-'] * 10)))


def _is_chat(as_user, to_keys, msg: Event, subject):
    """
    is this msg part of the chat we're looking at, currently this is just made
    up by have all the correct members in it, so if all the members are the same
    then you're looking in that group...
    TODO: look at proper group chat NIP and implement
    :param as_user:
    :param to_keys:
    :param msg:
    :return:
    """
    chat_members = set([as_user.public_key])

    if to_keys:
        chat_members = chat_members.union(set(to_keys))
    chat_members = list(chat_members)
    chat_members.sort()

    msg_members = list(set([msg.pub_key]).union(msg.p_tags))
    msg_members.sort()

    is_subject = True
    if subject and msg.get_tags('subject'):
        is_subject = subject in [s[0] for s in msg.get_tags('subject')]

    # if to_keys is None - only allowed when sending plain txts,
    # then every post is in view
    # subject is just used as a further restriction
    return (chat_members == msg_members or to_keys is None) \
           and is_subject


def prompt_loop(as_user, msg, to_users, is_encrypt, subject):
    """
    keeps a prompt open to type more messages util user types exit
    """

    from prompt_toolkit import Application
    from prompt_toolkit.layout import Layout, ScrollablePane
    from prompt_toolkit.layout.containers import HSplit, Window, VSplit
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.key_binding import KeyBindings
    from collections import OrderedDict

    kb = KeyBindings()
    buffer1 = Buffer()
    msg_events = []
    to_keys = None
    if to_users:
        to_keys = [p.public_key for p in to_users]

    peh = ProfileEventHandler(PROFILE_STORE)

    msg_split_con = HSplit([])

    class my_evt_handler:
        def __init__(self):
            self._duplicates = OrderedDict()
            self._max_dedup = 1000

        def do_event(self, sub_id, evt: Event, relay):
            # we likely to need to do this on all event handlers except those that would be
            # expected to deal with duplciates themselves e.g. persist
            if evt.id not in self._duplicates:
                self._duplicates[evt.id] = True
                if len(self._duplicates) >= self._max_dedup:
                    self._duplicates.popitem(False)

                if _is_chat(as_user, to_keys, evt, subject):
                    msg_events.append(evt)
                    make_msg_split()
                    app.invalidate()

    scr_print = (my_evt_handler())

    def on_connect(the_client: Client):
        the_client.subscribe(filters={
            'since': util_funcs.date_as_ticks(datetime.now() - timedelta(hours=1))
        }, handlers=[peh, scr_print])

    con_status = None

    def on_status(status):
        nonlocal con_status
        if con_status != status['connected']:
            con_status = status['connected']
            make_msg_split()
            app.invalidate()

    my_client = Client('ws://localhost:8081/',
                       on_connect=on_connect,
                       on_status=on_status).start()

    def make_msg_split():
        """
        make up the components to display the posts on screen
        note that though that though we can only send post of type encrypt/plaintext dependent
        on start options, here the view will show both and user won't can't tell the difference.
        Probably should only show encrypt if in encrypt and vice versa

        :return:
        """
        c_m: Event
        to_add = []

        for c_m in msg_events:
            content = c_m.content

            color = 'red'
            if c_m.pub_key == as_user.public_key:
                color = 'green'
            if not con_status:
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
                msg_profile = peh.profiles.lookup_pub_key(c_m.pub_key)
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
        msg_split_con.children = to_add

    # ctrl-q to quit, also type exit
    @kb.add('c-q')
    def exit_(event):
        my_client.end()
        app.exit()

    @kb.add('c-s')
    def post_(event):
        msg = buffer1.text
        if msg.replace(' ', ''):

            if my_client.connected:
                for evt in make_post(as_user=as_user,
                                     msg=msg,
                                     to_users=to_users,
                                     is_encrypt=is_encrypt):
                    my_client.publish(evt)
            else:
                'in someway make user aware that we dont have a connection to relay...'
                pass

            buffer1.text = ''

    root_con = HSplit([
        ScrollablePane(msg_split_con),
        Window(content=BufferControl(buffer1), height=3)
    ])
    my_layout = Layout(root_con)

    app = Application(full_screen=True,
                      layout=my_layout,
                      key_bindings=kb)
    app.run()


def run_post():
    relays = RELAYS
    as_user = None
    is_encrypt = True
    ignore_missing = False
    is_loop = False
    subject = None
    event = None
    peh = ProfileEventHandler(PROFILE_STORE)
    to_users = []

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ha:t:piles:r:e:', ['help',
                                                                     'relay='
                                                                     'as_profile=',
                                                                     'plain_text',
                                                                     'to=',
                                                                     'ignore_missing',
                                                                     'loop',
                                                                     'subject=',
                                                                     'event='])

        for o, a in opts:
            if o in ('-i', '--ignore_missing'):
                ignore_missing = True
            if o in ('-e','--event'):
                the_event = EVENT_STORE.get_filter({
                    'ids' : [a]
                })
                if not the_event:
                    print('no event found %s' % a)
                    sys.exit(2)
                else:
                    to_users.append(peh.profiles.get_profile(the_event[0].pub_key,
                                                             create_type=ProfileList.CREATE_PUBLIC))
                    for c_pk in the_event[0].p_tags:
                        to_users.append(peh.profiles.get_profile(c_pk,
                                                                 create_type=ProfileList.CREATE_PUBLIC))

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            elif o in ('-r', '--relay'):
                relays = a.split(',')
            elif o in ('-a', '--as_profile'):
                as_user = _get_profile(a, peh, '--as_profile %s not found' % a)
                if to_users:
                    if as_user in to_users:
                        to_users.remove(as_user)
            elif o in ('-p', '--plain_text'):
                is_encrypt = False
            elif o in ('-t', '--to'):
                for c_t in a.split(','):
                    to_add = _get_profile(c_t, peh, 'to profile %s not found' % c_t)
                    if to_add:
                        to_users.append(to_add)
                    elif not ignore_missing:
                        print('to profile missing and ignore_missing not set')
                        sys.exit(2)
            elif o in ('-s', '--s'):
                subject = a
            elif o in ('-l', '--loop'):
                is_loop = True

        if not as_user and len(args) > 0:
            a = args.pop(0)
            as_user = _get_profile(a, peh, 'args[] %s not found' % a)

        if not as_user:
            print('no profile to post as supplied or unable to find')
            sys.exit(2)

        if not to_users and is_encrypt:
            print('to users must be defined for encrypted posts')
            sys.exit(2)

        msg = None
        if len(args) > 0:
            msg = ' '.join(args)

        if is_loop:
            prompt_loop(as_user, msg, to_users, is_encrypt, subject)
        else:
            if msg is None:
                print('no message supplied!!!')
                sys.exit(2)
            else:
                show_post_info(as_user, msg, to_users, is_encrypt, subject)
                do_post(relays, as_user, msg, to_users, is_encrypt, subject)

    except getopt.GetoptError as e:
        print(e)
        usage()


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    run_post()

    # def my_connect(the_client: Client):
    #     print('connect')
    #     the_client.subscribe(handlers=[PrintEventHandler()], filters={
    #         'kinds': [1],
    #         'authors': ['0a6a0b8d3c024faa8c5b944dbcd88173fd0978a57700be17e681f6ee572205ec']
    #     })
    #
    #
    # my_client = Client('wss://rsslay.fiatjaf.com', on_connect=my_connect).start()
