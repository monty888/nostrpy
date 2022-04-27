"""
our profile pub/private key along, aswell as profile of others we see by looking at event types 0
and contact lists as NIP2

FIXME: the import methods should be moved to persist, this will allow us to add typehints there which we can't do
at the moment because of circular references

FIXME: methods that we have as from_db are actually just sql lite... eventually would want to be able to sub a
different db/persistance layer with min code changes

"""
import json
from json import JSONDecodeError
import secp256k1
import logging

from data.data import DataSet
from db.db import Database, SQLiteDatabase
from nostr.client.client import Event
from nostr.client.persist import ClientEventStoreInterface, SQLiteEventStore
from datetime import datetime
from nostr.util import util_funcs

class UnknownProfile(Exception):
    pass


class Profile:

    @classmethod
    def get_new_key_pair(cls, priv_key=None):
        if priv_key is None:
            pk = secp256k1.PrivateKey()
        else:
            pk = secp256k1.PrivateKey(priv_key)

        return {
            'priv_k' : pk.serialize(),
            'pub_k' : pk.pubkey.serialize(compressed=True).hex()
        }

    # @classmethod
    # def load_from_db(cls, db: Database, key):
    #     """
    #         load a single profile from db using key which should be either profilename, private key, or publickey
    #         where it's profilename or privatekey then we're able to sign, its a local/users profile
    #         if the match is found on pubkey then it's a remote key and can't be used to post messages
    #         match must be exact
    #     """
    #     sql = """
    #         select * from profiles
    #             -- see why we have profiles that are emptystr? anyway we want one with a priv_k if its us to sign key
    #             where profile_name=:? or priv_k=:? or pub_k=:?
    #             --and priv_k NOTNULL
    #             order by updated_at desc
    #     """
    #
    #     profiles = db.select_sql(sql, [key, key, key])
    #     if not profiles:
    #         raise UnknownProfile('Profile::load_from_db using key=%s, not found' % key)
    #     p = profiles[0]
    #     return Profile(
    #         priv_k=p['priv_k'],
    #         pub_k=p['pub_k'],
    #         profile_name=p['profile_name'],
    #         attrs=p['attrs'],
    #         update_at=p['updated_at']
    #     )

    def __init__(self, priv_k=None, pub_k=None, attrs=None, profile_name='', update_at=None):
        """
            create a new ident/person that posts can be followed etc.
            having the priv key means we can sign and so post (it's us)
            whilst only having the public key means it must be some one else e.g. someone/thing we might follow

            attrb are things such as name, profile pic for this ident see NIP set via event 0, where it us when we change
            we should send a event 0 to update on relay

            also somewhat related to NIP2 follower list events - note we could have local, we only need to post if we'd
            want to recreated from scratch without our data but only with privkey

        """

        self._profile_name = profile_name
        self._priv_k = priv_k
        self._pub_k = pub_k
        self._attrs = attrs
        if self._attrs is None:
            self._attrs = {}
        else:
            # if is str rep e.g. directly from event turn it to {}
            if isinstance(self._attrs, str):
                try:
                    self._attrs = json.loads(self._attrs)
                except JSONDecodeError as e:
                    logging.debug(e)

        # we'll always want a date when this profile was valid, if its not provided then its now
        self._update_at = update_at
        if update_at is None:
            self._update_at = datetime.now()
        elif not isinstance(self._update_at, datetime):
            self._update_at = util_funcs.ticks_as_date(self._update_at)

    """
        only exists if us, we use this name to load the profile from db, it doesn't have to match
        any name attr defined in tag 
    """
    @property
    def profile_name(self):
        return self._profile_name

    @profile_name.setter
    def profile_name(self, name):
        self._profile_name = name

    @property
    def name(self):
        ret = None
        if 'name' in self.attrs:
            ret = self.attrs['name']
        return ret

    @name.setter
    def name(self, name):
        self._attrs['name'] = name

    # only exists if us
    @property
    def private_key(self):
        return self._priv_k

    @private_key.setter
    def private_key(self, priv_key):
        self._priv_k = priv_key

    @property
    def public_key(self):
        # profile must have be created only with priv_k
        # work out corresponding pub_k
        if not self._pub_k and self._priv_k:
            pk = secp256k1.PrivateKey(bytes(bytearray.fromhex(self._priv_k)), raw=True)
            self._pub_k = pk.pubkey.serialize(compressed=True).hex()[2:]

        return self._pub_k

    @property
    def attrs(self):
        return self._attrs

    @attrs.setter
    def attrs(self, attrs):
        self._attrs = attrs

    def get_attr(self, name):
        # returns vale for named atr, None if it isn't defined
        ret = None
        if name in self._attrs:
            ret = self._attrs[name]
        return ret

    def set_attr(self, name, value):
        self._attrs[name] = value

    @property
    def update_at(self):
        # note as datetime - convert to ticks before storing in dd
        return self._update_at

    def get_meta_event(self):
        """
            returns a meta event for this profile that once signed can be posted to relay for update
        """
        return Event(kind=Event.KIND_META,
                     # possible only output a sub section of the attrs?
                     content=json.dumps(self.attrs, separators=[',', ':']),
                     pub_key=self.public_key)

    def __str__(self):

        can_sign = False
        if self.private_key:
            can_sign = True

        return '%s %s %s can sign=%s' % (self.display_name(False), self.public_key, self.attrs, can_sign)

    def display_name(self, with_pub=False):
        # any thing with profile is assumed to be local
        ret = self.profile_name
        if not ret:
            # loc = 'remote'
            # if self.private_key:
            #     loc = 'local'
            name = self.name
            if not name:
                name = util_funcs.str_tails(self.public_key, 4)
            # ret = '%s/%s' % (loc, name)
            ret = name

        if with_pub and self.name:
            ret = '%s<%s>' % (ret, util_funcs.str_tails(self.public_key, 4))

        return ret

    def as_dict(self):
        ret = {
            'pub_k': self.public_key,
            'attrs': self.attrs
        }
        return ret

    def sign_event(self, e: Event):
        """
            signs a given event, note this will set the events pub_key, if the pub_key has been previously set it'll
            be overwritten with our pub key, a new id will be created also
        :param e:
        :return:
        """
        if self.private_key is None:
            raise Exception('Profile::sign_event don\'t have private key to sign event, is remote profile?')

        e.pub_key = self.public_key
        e.sign(self.private_key)
        return e


class ProfileList:
    """
        collection of profiles, for now were using this for profiles other than us,
        but the user could also have multiple profiles -  that is those profiles for which
        they have the private keep i.e. they can create events

        TODO: change this to be subclass of basic list see https://docs.python.org/3/reference/datamodel.html#emulating-container-types
        actually probbly just implemnt the special methods we need rather than subclass...

    """

    def __init__(self, profiles):
        self._profiles = profiles

        # make some lookups, in most cases pub_key lookup will be the one that gets used
        # it'll also be the one that we should have for everyone
        self._pub_key_lookup = {}
        self._priv_key_lookup = {}
        self._pname_lookup = {}
        c_p: Profile
        for c_p in self._profiles:
            self._pub_key_lookup[c_p.public_key] = c_p
            if c_p.private_key:
                self._priv_key_lookup[c_p.private_key] = c_p
            if c_p.profile_name:
                self._pname_lookup[c_p.profile_name] = c_p

    def append(self, profile: Profile):
        self._profiles.append(profile)
        self._pub_key_lookup[profile.public_key] = profile

    # TODO: remove this and see if it breaks anyhting...
    def as_arr(self):
        ret = []
        for c_p in self._profiles:
            ret.append(c_p.as_dict())
        return ret

    def lookup_pub_key(self, key):
        """
            return profile obj for pubkey if we have it
        """
        ret = None
        if key in self._pub_key_lookup:
            ret = self._pub_key_lookup[key]
        return ret

    def lookup_priv_key(self, key):
        """
            return profile obj for pubkey if we have it
        """
        ret = None
        if key in self._priv_key_lookup:
            ret = self._priv_key_lookup[key]
        return ret

    def lookup_profilename(self, key):
        """
            return profile obj for pubkey if we have it
        """
        ret = None
        if key in self._pname_lookup:
            ret = self._pname_lookup[key]
        return ret

    def matches(self, m_str, max_match=None):
        if m_str.replace(' ','') == '':
            ret = self._profiles
            if max_match:
                ret = ret[:max_match]
            return ret

        # simple text text lookup against name/pubkey
        ret = []
        # we're going to ignore case
        m_str = m_str.lower()
        for c_p in self._profiles:
            # pubkey should be lowercase but name we convert
            if m_str in c_p.public_key or c_p.name and m_str in c_p.name.lower():
                ret.append(c_p)

            # found enough matches
            if max_match and len(ret) >= max_match:
                break
        return ret

    def get_profile(self, profile_key, create_type=None) -> Profile:
        """
        :param profile_key: either priv_key, profile_name or pub_key
        :param create_type: None, 'private' or 'public' if we don't find then an empty profile will be created
                            with profile_key as either public/private ot not if None. This is enough for use in many
                            cases.
        :return: Hopefully found Profile, or if create_type then stub Profile assuming key looked correct else None
        """

        ret = None

        # we were handed a profile obj so everything is probably cool...
        if isinstance(profile_key, Profile):
            ret = profile_key
        # ok assuming we have a db lets see if we can find this profile
        elif isinstance(profile_key, str) and self._profiles:
            ret = self.lookup_priv_key(profile_key)
            if not ret:
                ret = self.lookup_profilename(profile_key)
            if not ret:
                ret = self.lookup_pub_key(profile_key)

        # we didn't find a profile but we'll see if we can just use as priv key...
        # also fallback we don't have db
        if not ret and create_type is not None and util_funcs.is_nostr_key(profile_key):
            if len(profile_key) == 64:
                if create_type == 'private':
                    ret = Profile(priv_k=profile_key,
                                  profile_name='adhoc_user')
                elif create_type == 'public':
                    ret = Profile(pub_k=profile_key)

        return ret

    def __getitem__(self, item):
        return self._profiles[item]

    def __len__(self):
        return len(self._profiles)


class Contact:

    def __init__(self, owner_pub_k, updated_at, args):
        # see https://github.com/fiatjaf/nostr/blob/master/nips/02.md

        # the pub key of the profile whose contact list the contact has been created from
        self._owner_pub_k = owner_pub_k
        self._updated_at = updated_at

        # this pub key which comes from the event should probably have some basic checks done on it
        # i.e. len, hex str...

        self._contact_pub_k = args[1]

        self._relay = None
        if len(args) > 2:
            self._relay = args[2]

        self._petname = None
        if len(args) > 3:
            self._petname = args[3]

    @property
    def owner_public_key(self):
        return self._owner_pub_k

    @property
    def contact_public_key(self):
        return self._contact_pub_k

    @property
    def petname(self):
        return self._petname

    @property
    def relay(self):
        return self._relay

    @property
    def updated_at(self):
        return self._updated_at

    def __str__(self):
        ret = []
        if self.petname:
            ret.append('%s(%s)' % (self.petname, self.contact_public_key))
        else:
            ret.append(self.contact_public_key)

        if self._relay:
            ret.append('@%s' % self.relay)

        return ''.join(ret)


class ContactList:

    def __init__(self, contacts):
        self._contacts = contacts

    # because a list should only contain the contacts for a single profile
    # this methods jsut look at the 0 element if it exists and return value from there
    @property
    def owner_public_key(self):
        ret = None
        if self._contacts:
            ret = self._contacts[0].owner_public_key
        return ret

    @property
    def updated_at(self):
        ret = None
        if self._contacts:
            ret = self._contacts[0].updated_at
        return ret

    def __len__(self):
        return len(self._contacts)

    def __iter__(self):
        for c in self._contacts:
            yield c


class ProfileEventHandler:
    """
        loads all profiles from db and then keeps that mem copy up to date whenever any meta events are recieved
        obvs at some point keeping all profiles in memory might not work so well but OK at the moment....
        TODO: check and verify NIP05 if profile has it
    """

    def __init__(self,
                 profile_store: 'ProfileStoreInterface',
                 on_update=None):

        self._store = profile_store
        self._profiles = self._store.select()
        self._on_update = on_update

    def do_event(self, sub_id, evt: Event, relay):
        c_profile: Profile
        evt_profile: Profile

        if evt.kind == Event.KIND_META:
            pubkey = evt.pub_key
            c_profile = self._profiles.lookup_pub_key(pubkey)
            evt_profile = Profile(pub_k=pubkey, attrs=evt.content, update_at=evt.created_at_ticks)

            # we only need to do something if the profile is newer than we already have
            if c_profile is None or c_profile.update_at < evt_profile.update_at:
                # not sure about this... probably OK most of the time...
                if c_profile:
                    self._store.update(evt_profile)
                else:
                    self._store.add(evt_profile)
                    self._profiles.append(evt_profile)

                # if owner gave us an on_update call with pubkey that has changed, they may want to do something...
                if self._on_update:
                    self._on_update(evt_profile, c_profile)

    @property
    def profiles(self) -> ProfileList:
        return self._profiles

    def set_on_update(self, on_update):
        self._on_update = on_update




if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    nostr_db_file = '/home/shaun/.nostrpy/nostr-client.db'
    backup_dir = '/home/shaun/.nostrpy/'
    ps = SQLLiteEventStore(nostr_db_file)

    from nostr.client.client import Client
    from nostr.client.event_handlers import PersistEventHandler

    def my_start(the_client: Client):
        the_client.subscribe(handlers=PersistEventHandler(SQLLiteEventStore(nostr_db_file)))

    # my_client = Client('wss://nostr-pub.wellorder.net', on_connect=my_start).start()

    # ContactList.import_from_events(SQLLiteStore(nostr_db_file), SQLProfileStore(SQLiteDatabase(nostr_db_file)))
    Profile.import_from_file('/home/shaun/.nostrpy/local_profiles.csv',SQLProfileStore(SQLiteDatabase(nostr_db_file)))




