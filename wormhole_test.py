import logging
import wormhole
from twisted.internet import reactor
from time import sleep

RENDEZVOUS_RELAY = u"ws://relay.magic-wormhole.io:4000/v1"
TRANSIT_RELAY = u"tcp:transit.magic-wormhole.io:4001"


class MyDelegate:
    def wormhole_got_welcome(self, welcome):
        print('wormhole started %s '% welcome)

    def wormhole_got_code(self, code):
        print("code: %s" % code)

    def wormhole_got_message(self, msg): # called for each message
        print("got data, %d bytes" % len(msg))
        i = w.get_message()
        yield w.close()

    def wormhole_closed(self, result):
        print('done')


w = wormhole.create('nostrpy', RENDEZVOUS_RELAY, reactor)
x = w.get_code()

def the_code(code):
    print(code)

x.addCallback(the_code)

print(w.send_message(b'hello there you'))
print(w.close())



reactor.run()





