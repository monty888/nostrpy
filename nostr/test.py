import rel
import logging
import secp256k1
from nostr.persist import Store
from nostr.network import Client,Event
import datetime

rel.safe_read()

def ticks_as_date(ticks):
    return datetime.datetime.now() + datetime.timedelta(microseconds=ticks / 10)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)


    nostr_db_file = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
    relay = 'wss://nostr-pub.wellorder.net'
    # relay = 'wss://relayer.fiatjaf.com'

    # relay = 'ws://127.0.0.1:7000'
    # websocket.enableTrace(True)


    my_store = Store(nostr_db_file)
    # my_store.delete()
    # my_store.create('profiles')

    my_network = Client(relay)

    def event(evt):
        logging.debug('event: %s' % evt)
        try:
            my_store.add_event(evt)
        # duplicate events are valid exception that we don't care about... but what about overs?
        except Exception as e:
            print(e)

    oldest = my_store.get_oldest()
    filter = {}
    if oldest:
        print('subscribing, pre existing events, setting since as %s' % ticks_as_date(oldest))
        filter = {
            'since' : oldest
        }
    else:
        # probably we should just do a minimal lookback?
        print('subscribing, looks like db is empty, non since filter applied')

    from ident import Profile

    me = Profile.load_from_db('firedragon888', nostr_db_file)

    n_evt = Event(kind=Event.KIND_TEXT_NOTE, content='monkies are cool')
    me.sign_event(n_evt)

    # only one sub at the moment but we'll probably end up subed to multiple replays where subs are stored in db
    #
    my_network.subscribe('my_sub', event, filter)
    #
    # # this runs forever more
    my_network.publish(n_evt)
    rel.signal(2, rel.abort)  # Keyboard Interrupt
    rel.dispatch()

    pk = secp256k1.PrivateKey(secp256k1.PrivateKey().deserialize(me.private_key))

    evt_id = n_evt.event_data()['id']
    id_bytes = (bytes(bytearray.fromhex(evt_id)))

    the_sig = pk.schnorr_sign(id_bytes,'', raw=True)


    print('the_sig',the_sig, the_sig.hex())
    print('event sig', n_evt.event_data()['sig'])



    print(pk.pubkey.schnorr_verify(id_bytes,the_sig,'',True))










