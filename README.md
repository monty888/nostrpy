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

## events view ##
live nostr events view from the command line

> python3 cmd_event_view.py 

> python cmd_event_view.py -h for other options


## web ##
web interface to nostr
![alt feed page](feed_page.png "feed")

> python3 cmd_web.py

### todo
#### general
[ ] implement postgres as data store for client
#### cmd_web.py
[ ] settings ...    
[ ] websocket for client probably shouldn't be getting opened each page but be in sharedwebworker  
[ ] enable media available from front end
[ ] url for robos from front end
[ ] connected relays should be being saved and on restart the same relays should be connected to  
[ ] light init mode where we only use a default relay to get relay list and then its all user choice
[ ] boosts  
[ ] make sure the caching of profiles is working correctly and firing/listening for profile changes updates
as expected  
[ ] it should be possible to new/link to a profile that we don't yet have the profile for
, the profile may come in later e.g. when backfill is in progress

#### backfill
[ ] should keep a last backfilled to per relay so we can start from that point rather than the oldest event 
so that we don't needlessly look back through dates for which no events exist
#### clean out
[ ] a job that runs in the background and will clean out old events based on defined rules

### bugs
[ ] profiles only sorted as they come from db and not as new events come in






