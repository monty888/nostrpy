# nostrpy

cd nostrpy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

== run relay ==
python3 run_relay.py 

The default is to run the relay at ws://localhost:8081 with an sqlite db at /home/.nostrpy/nostr-client.db, the directry and db will be created if it doesn't exist.

python run_relay -h for other options

