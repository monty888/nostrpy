import json
import logging
import time
from datetime import datetime, timedelta
import cmd
import hashlib
import base64
from db.db import SQLiteDatabase as Database
from nostr.client.client import Client
from nostr.event.event import Event
from nostr.client.event_handlers import PrintEventHandler, PersistEventHandler, EventHandler
# from nostr.client.persist import SQLLiteEventStore
from nostr.util import util_funcs
# from nostr.ident import ProfileList, Profile
from nostr.encrypt import SharedEncrypt

def test_client_publish(relay_url):
    """
        opens a connection to a single relay and prints out text events as they come in starting from now -1 day
    """
    import rel
    rel.safe_read()

    my_client = Client(relay_url)
    filter = {
        'since' : util_funcs.date_as_ticks(datetime.now()-timedelta(days=1)),
        'kinds' : [Event.KIND_TEXT_NOTE]
    }

    def do_event(evt):
        print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                               evt['pubkey'],
                               evt['content']))

    my_client.subscribe('test_sub', do_event, filter)
    print('started')






def test_client_publish_with_persist(relay_url, db_file):
    """
        as above but now persisting all events
    """

    my_client = Client(relay_url)
    my_store = Store(db_file)
    # so we can replace pub_keys with name if we have
    profiles = ProfileList.create_others_profiles_from_db(db_file)

    filter = {
        'since' : my_store.get_oldest()-10000
        # 'since' : util_funcs.date_as_ticks(datetime.now() - timedelta(days=1))
    }


    def do_event(evt):
        nonlocal profiles

        try:
            my_store.add_event(evt)
        except:
            # most likely because we already have, we could though add a table that
            # linking evets with every relay we saw them from
            pass

        # if we have the profile and that contains a name then replace pubkey with that
        pubkey = created_by = evt['pubkey']
        c_profile = profiles.lookup(pubkey)
        if c_profile and c_profile.get_attr('name'):
            created_by = c_profile.get_attr('name')

        kind = evt['kind']
        if kind == Event.KIND_TEXT_NOTE or kind == Event.KIND_ENCRYPT:
            print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                                   created_by,
                                   evt['content']))
        elif kind == Event.KIND_META:
            c_profile = profiles.lookup(pubkey)
            if c_profile:
                my_store.update_profile(c_profile)
            else:
                c_profile = Profile(pub_k=pubkey,attrs=evt['content'],update_at=evt['created_at'])
                my_store.add_profile(c_profile)

            # for now we just reload the whole lot from db rather then just updating what we have
            profiles = ProfileList.create_others_profiles_from_db(db_file)

    my_client.subscribe('test_sub', do_event, filter)

def command_line(relay_url, db_file):
    """
        do some basics from the cmd line
    """
    class MyShell(cmd.Cmd):
        intro = 'Welcome to the nostrpy shell.   Type help or ? to list commands.\n'
        prompt = '%s : ' %relay_url
        file = None

        def __init__(self):
            self._c_profile = None
            self._db_file = db_file
            self._db = Database(self._db_file)
            self._store = SQLLiteEventStore(db_file)

            self._print_view = PrintEventHandler(False)
            self._event_handler = [PersistEventHandler(self._store),
                                   self._print_view]
            self._set_relay()
            super().__init__()

        def _set_relay(self):
            def my_connect(the_client):
                filter = {
                    'since': self._store.get_oldest(),
                    'kinds': [Event.KIND_TEXT_NOTE]
                }

                the_client.subscribe('testid', self._event_handler, filter)

            self._relay = Client(relay_url, on_connect=my_connect).start()


        def do_post(self, arg):
            'Post text as not to relay'
            if self._c_profile:
                n_event = Event(kind=Event.KIND_TEXT_NOTE,content=arg, pub_key=self._c_profile.public_key)
                n_event.sign(self._c_profile.private_key)
                self._relay.publish(n_event)
            else:
                print('no profile, use set_profile %name%')

        def do_encrypt_post(self, arg):
            """
send encrypted msg like NIP4 but via public inbox see:
https://github.com/vinliao/clust
encrypt_post <pubkey> <msg>

            """
            arg = arg.split(' ')
            if self._c_profile:
                my_enc = SharedEncrypt(self._c_profile.private_key)
                my_enc.derive_shared_key(arg[0])
                # now make the event
                shared = [
                    ['shared',hashlib.sha256(my_enc.shared_key().encode()).hexdigest()]
                ]
                crypt_message = my_enc.encrypt_message(b'a very simple message to test encrypt')
                enc_message = base64.b64encode(crypt_message['text'])
                iv_env = base64.b64encode(crypt_message['iv'])
                full_enc_message = '%s?iv=%s' % (enc_message.decode(), iv_env.decode())

                public_box = Profile.load_from_db(self._db, 'anonmailbox')
                n_evt = Event(kind=Event.KIND_ENCRYPT,
                              tags=shared,
                              content=full_enc_message,
                              pub_key=public_box.public_key[2:])

                n_evt.sign(public_box.private_key)
                self._relay.publish(n_evt)
            else:
                print('no profile, use set_profile %name%')


        def do_set_profile(self, arg):
            'set the profile to use'
            try:
                self._c_profile = Profile.load_from_db(self._db, arg)
                self.prompt = '%s@%s : ' % (self._c_profile.profile_name,
                                            self._relay.url)
            except Exception as e:
                logging.debug(e)

        def do_show_keys(self, arg):
            'shows the public and private key of currently selected profile'
            if self._c_profile:
                print('%s : %s' % ('public_key'.ljust(20), self._c_profile.public_key[2:]))
                print('%s : %s' % ('private_key'.ljust(20), self._c_profile.private_key))
            else:
                print('no profile, use set_profile %name%')

        def do_set_meta(self,arg):
            """
set meta data for this profile using name=value pairs
example common tags name, picture, about
FIXME: needs to support quoting for strings with spaces!
            """
            if self._c_profile:
                splits = arg.split(' ')
                contents = {}
                for c_split in splits:
                    n, v = c_split.split('=')
                    contents[n] = v

                # and publish
                n_event = Event(kind=Event.KIND_META, content=json.dumps(contents,separators=[',',':']), pub_key=self._c_profile.public_key)
                n_event.sign(self._c_profile.private_key)
                self._relay.publish(n_event)
            else:
                print('no profile, use set_profile %name%')

        def do_view_all(self, arg):
            self._print_view.view_on()
            input('press any key to exit view\n')
            self._print_view.view_off()
            print('exit view_all')

        def do_delete(self, arg):
            'send delete event for event_ids'
            if self._c_profile:
                tags = []
                for c_id in arg.split(' '):
                    tags.append(['e', c_id])

                n_evt = Event(kind=Event.KIND_DELETE,
                              tags=tags,
                              content='delete from nostrpy shell',
                              pub_key=self._c_profile.public_key[2:])

                n_evt.sign(self._c_profile.private_key)
                self._relay.publish(n_evt)

            else:
                print('no profile, use set_profile %name%')

        def do_exit(self, arg):
            'exit back to shell'
            return True

    MyShell().cmdloop()

def test_encrypt():
    """
        TO come back to, getting encrypted messages working and compatable with CLUST
    """
    from nostr.encrypt import SharedEncrypt
    a_priv = '9b0d918c24fd415f5dc3e9d65656dc0d75734ac9aa19df9a5d3775e62768813d'
    b_priv = 'c3c8d77bcc8bd0d1942a965848432c110cfaa896c08db6f888b5ce7fc8b5a3e9'

    sea = SharedEncrypt(a_priv)
    seb = SharedEncrypt(b_priv)
    sea.derive_shared_key('40e162e0a8d139c9ef1d1bcba5265d1953be1381fb4acd227d8f3c391f9b9486')
    seb.derive_shared_key(sea.public_key_hex)

    print('>>>',sea.shared_key())

    # encrypted = sea.encrypt_message(b'i am master of all I survey', pub_key_hex=seb.public_key_hex)
    # print(seb.decrypt_message(encrypted['text'],encrypted['iv'], pub_key_hex=sea.public_key_hex))


    print(hashlib.sha256(sea.shared_key().encode()).hexdigest())
    print(hashlib.sha256(seb.shared_key().encode()).hexdigest())

    # decode our messages
    full_enc_message = '12G/rN2/w4orzQ7U7TyLXw==?iv=ovjfKmTNe+fGDH61orkZiQ=='
    #full_enc_message = 'whHAIP8olIEOJmfBComxdw==?iv=mkkwrgCPT4CIdVZ+7p90yA=='

    msg_split = full_enc_message.split('?iv')
    text = base64.b64decode(msg_split[0])
    iv = base64.b64decode(msg_split[1])

    enc = sea.encrypt_message(b'wtf')

    print(seb.decrypt_message(enc['text'], enc['iv']))
    print(seb.decrypt_message(text, iv))


def events_backup(relay_url, filename, since=None):
    Client.relay_events_to_file(relay_url, filename)

def events_import(relay_url, filename):
    Client.post_events_from_file(relay_url, filename)

def backfill_test():
    print('lets check batch compared to single if we can....')

    # url = 'wss://nostr-pub.wellorder.net'
    url = 'ws://localhost:8081/'
    # url = 'wss://relay.damus.io'

    is_done = False
    events = []
    start_time:datetime = None
    since = util_funcs.date_as_ticks(datetime.now()-timedelta(days=5))
    from nostr.event.persist import ClientSQLiteEventStore
    from nostr.ident.persist import SQLiteProfileStore
    from nostr.ident.profile import Profile,ContactList, ProfileEventHandler
    db_file = '/home/shaun/performance_test/test.db'
    util_funcs.create_sqlite_store(db_file)
    event_store = ClientSQLiteEventStore(db_file=db_file)
    profile_store = SQLiteProfileStore(db_file=db_file)
    peh =ProfileEventHandler(profile_store)

    def on_eose(the_client: Client, sub_id):
        nonlocal is_done
        nonlocal start_time
        profiles = []
        contacts = []
        # no events!!!
        if start_time is None:
            start_time = datetime.now()

        print('%s' % (datetime.now() - start_time).total_seconds())
        print('n events %s' % len(events))

        try:
            event_store.add_event_relay(events, the_client.url)
            c_evt: Event
            for c_evt in events:
                if c_evt.kind == Event.KIND_META:
                    p = Profile.from_event(c_evt)
                    if peh.is_newer_profile(p):
                        profiles.append(p)
                elif c_evt.kind == Event.KIND_CONTACT_LIST:
                    contacts_list = ContactList.create_from_event(c_evt)
                    if peh.is_newer_contacts(contacts_list):
                        contacts.append(contacts_list)

            profile_store.put_profile(profiles)
            profile_store.put_contacts(contacts)

        except Exception as e:
            print(e)

        is_done = True
        print('%s' % (datetime.now() - start_time).total_seconds())

    class my_event(EventHandler):

        def do_event(self, sub_id, evt: Event, relay):
            nonlocal start_time
            nonlocal events
            nonlocal event_store
            if start_time is None:
                start_time = datetime.now()
            events.append(evt)

    def my_connected(the_client: Client):
        since  = event_store.get_newest(for_relay=the_client.url, filter={
            # 'kinds': [Event.KIND_CONTACT_LIST]
        })
        the_client.subscribe(handlers=[my_event()], filters={
            # 'kinds': [Event.KIND_CONTACT_LIST],
            'since': since
        })

    with Client(url, on_connect=my_connected, on_eose=on_eose) as c:
        while is_done is False:
            print('client is busy')
            time.sleep(1)

def pool_testing():
    from nostr.client.client import ClientPool
    from threading import Thread
    from nostr.client.event_handlers import ProfileEventHandler
    from nostr.ident.persist import SQLiteProfileStore

    def my_connect(the_client:Client):
        print('hi there! from %s' % the_client.url)

    c = ClientPool(clients=[], on_connect=my_connect)
    print(len(c))

    peh = ProfileEventHandler(SQLiteProfileStore(nostr_db_file))
    my_profile = peh.profiles.lookup_profilename('scarjo')




    def my_thread():

        i = 0
        while True:
            n_evt = Event(kind=Event.KIND_TEXT_NOTE,
                          content='test event: %s' % i,
                          pub_key=my_profile.public_key)
            n_evt.sign(my_profile.private_key)

            print('thread runs')
            time.sleep(2)
            print('adding a client')
            c.add('ws://localhost:8081')
            c.add('ws://localhost:8082')
            time.sleep(2)
            c.publish(n_evt)
            time.sleep(1)

            c.remove('ws://localhost:8081')
            c.remove('ws://localhost:8082')
            print(len(c))
            i+=1


    Thread(target=my_thread).start()

    c.start()


if __name__ == "__main__":
    # logging.getLogger().setLevel(logging.DEBUG)
    nostr_db_file = '/home/shaun/.nostrpy/nostr-client.db'
    # nostr_db_file = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr-relay.db'
    # relay_url = 'wss://nostr-pub.wellorder.net'
    # relay_url = 'wss://rsslay.fiatjaf.com'
    # relay_url = 'wss://nostr.bitcoiner.social'
    # relay_url = 'ws://localhost:7000'
    relay_url = 'ws://localhost:8082/'
    backup_dir = '/home/shaun/.nostrpy/'

    # test_client_publish(relay_url)
    # test_client_publish_with_persist(relay_url, nostr_db_file)
    # command_line(relay_url, nostr_db_file)
    # test_encrypt()

    # backfill_test()
    pool_testing()

    # from nostr.ident.profile import Profile,ProfileEventHandler
    # from nostr.ident.persist import SQLiteProfileStore
    #
    # peh = ProfileEventHandler(SQLiteProfileStore(nostr_db_file))
    # my_profile = peh.profiles.lookup_profilename('firedragon888')
    #
    # with Client('ws://localhost:8081') as my_client:
    #     i = 0
    #     while True:
    #         if my_client.connected:
    #             n_evt = Event(kind=Event.KIND_TEXT_NOTE,
    #                           content='test event: %s' % i,
    #                           pub_key=my_profile.public_key)
    #             n_evt.sign(my_profile.private_key)
    #             i += 1
    #             my_client.publish(n_evt)
    #         time.sleep(0.01)

    # NOTE: each event is json but the file structure isn't correct json there are \n between each event
    # events_backup(relay_url, backup_dir+'events.json')
    # from nostr.network import ClientPool
    # s = Store(nostr_db_file)
    # pool = ClientPool(['wss://nostr-pub.wellorder.net', 'ws://localhost:7000'])
    # pool.start()
    # pool.subscribe('pool_test',None,{
    #     'since' : s.get_oldest()-100000
    # })
    #
    # def check_ping():
    #     while True:
    #         time.sleep(0.5)
    #
    # from threading import Thread
    # Thread(target=check_ping()).start()

    # from nostr.event import PersistEventHandler
    # with Client(relay_url) as c:
    #     c.subscribe('x',PersistEventHandler(nostr_db_file),{
    #         'since' : util_funcs.date_as_ticks(datetime.now())-1000000
    #     })
    #     time.sleep(100)

    # Client.post_events_from_file(relay_url, backup_dir+'events2.json')



    # my_filter = {'since': util_funcs.date_as_ticks(datetime.now())-100000, 'kinds': [4]}
    #
    # Client.relay_events_to_file(relay_url,backup_dir+'events2.json')
    # from nostr.persist import RelayStore
    # rs = RelayStore(nostr_db_file)
    # rs.create()
    # from nostr.relay.persist import PostgresStore
    # #
    # my_store = PostgresStore(db_name='nostr-relay',
    #                          user='postgres',
    #                          password='password')
    #
    # my_store.create()
    # my_store.destroy()
    # from nostr.relay.persist import SQLiteStore
    # my_sql = SQLiteStore('/home/shaun/test')
    # print(my_sql.exists())



