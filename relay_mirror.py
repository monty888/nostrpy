"""
watches one relay and post what it sees into another
TODO: use ClientPool for multiple)

"""
import logging
import time
from datetime import datetime,timedelta
from nostr.util import util_funcs
from nostr.client.client import Client, ClientPool
from nostr.client.event_handlers import RepostEventHandler

def do_mirror(from_relay, to_relay, filter=None):
    if filter is None:
        filter = {
            'since': util_funcs.date_as_ticks(datetime.now()-timedelta(days=30)),
            # 'kinds': 1
        }

    # where we're posting to
    to_relay = ClientPool(to_relay)
    to_relay.start()

    # TODO add EOSE support
    def on_connect(the_from_relay):
        reposter = RepostEventHandler(to_relay)
        the_from_relay.subscribe(handlers=reposter, filters=filter)

    from_relay = ClientPool(from_relay, on_connect=on_connect)
    from_relay.start()

    print('starting mirror \nfrom %s to %s \nwith filter=%s' % (from_relay, to_relay, filter))

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.WARN)

    from_relay = ['wss://nostr-pub.wellorder.net', 'wss://nostr.bitcoiner.social',
                  'wss://rsslay.fiatjaf.com','wss://nostr.rocks','wss://nostr-relay.wlvs.space',
                  'wss://nostrrr.bublina.eu.org','wss://expensive-relay.fiatjaf.com']
    # from_relay = ['ws://localhost:8082/','ws://localhost:8083/']
    to_relay = ['ws://localhost:8081/']
    do_mirror(from_relay, to_relay)
