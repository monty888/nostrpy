# nostrpy
some stuff written in python for the nostr protocol  

- relay, relay implementation - basically working not really tested
- client, client pool - classes that implement the client side part of the nostr protocol for apps to be built on - very rough but working
- cmd_chat, example currently 1-1 cli chat app, partially implemented
- mirror_relay, mirror nostr events from one set of nostr relays to another


# relay
> cd nostrpy  
> python3 -m venv venv  
> source venv/bin/activate  
> pip install -r requirements.txt

## run relay ##
> python3 run_relay.py 

The default is to run the relay at ws://localhost:8081 with an sqlite db at /home/.nostrpy/nostr-client.db, the directry and db will be created if it doesn't exist.

> python run_relay -h for other options

