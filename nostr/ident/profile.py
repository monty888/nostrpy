"""
our profile pub/private key along, aswell as profile of others we see by looking at event types 0
and contact lists as NIP2

FIXME: the import methods should be moved to persist, this will allow us to add typehints there which we can't do
at the moment because of circular references

FIXME: methods that we have as from_db are actually just sql lite... eventually would want to be able to sub a
different db/persistance layer with min code changes

"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.ident.persist import ProfileStoreInterface

import json
from json import JSONDecodeError
import logging
from nostr.event.event import Event
from datetime import datetime
from nostr.util import util_funcs
from nostr.encrypt import Keys


class UnknownProfile(Exception):
    pass


class Profile:

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

        self._contacts = None
        self._followed_by = None
        self._priv_k = priv_k
        self._pub_k = pub_k
        self._attrs = {}
        if attrs is not None:
            if isinstance(attrs, dict):
                self._attrs = attrs
            # if is str rep e.g. directly from event turn it to {}
            elif isinstance(attrs, str):
                try:
                    self._attrs = json.loads(attrs)
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

    def load_contacts(self, profile_store: ProfileStoreInterface, reload=False) -> ContactList:
        if self._contacts is None or reload is True:
            self._contacts = profile_store.contacts({
                'owner': self.public_key
            })

        return self._contacts

    def load_followers(self, profile_store: ProfileStoreInterface, reload=False) -> ContactList:
        # TODO: actually load_contacts and load_followers could be done in a single call
        #  and then just split the contact list ourself?
        #  also add method to set_profile_store then contacts/followed_by could just attempt the loads adhoc?
        if self._followed_by is None or reload is True:
            self._followed_by = profile_store.contacts({
                'contact': self.public_key
            })

        return self._followed_by

    @property
    def contacts(self) -> ContactList:
        if self._contacts is None:
            raise Exception('Profile::contacts - load contacts hasn\'t been called yet for contact %s' % self.display_name())
        return self._contacts

    @contacts.setter
    def contacts(self, contacts: ContactList):
        self._contacts = contacts

    @property
    def followed_by(self) -> ContactList:
        if self._followed_by is None:
            raise Exception(
                'Profile::followed_by - load contacts hasn\'t been called yet for contact %s' % self.display_name())
        return self._followed_by

    @followed_by.setter
    def followed_by(self, contacts: ContactList):
        self._followed_by = contacts

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
            # this probably should be part of key in encrypt then we can get rid of secp256 from this file
            # pk = secp256k1.PrivateKey(bytes(bytearray.fromhex(self._priv_k)), raw=True)

            key_pair = Keys.get_new_key_pair(self._priv_k)
            self._pub_k = key_pair['pub_k'][2:]

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

    @update_at.setter
    def update_at(self, at_date):
        self._update_at = at_date

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

        if with_pub and ret:
            ret = '%s<%s>' % (ret, util_funcs.str_tails(self.public_key, 4))

        return ret

    def as_dict(self, with_private_key=False):
        ret = {
            'pub_k': self.public_key,
            'attrs': self.attrs,
            'can_sign': self.private_key is not None
        }
        if with_private_key:
            ret['private_key'] = self.private_key

        if self.profile_name:
            ret['profile_name'] = self.profile_name

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

    CREATE_PRIVATE = 'private'
    CREATE_PUBLIC = 'public'

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

    def add(self, profile: Profile):
        self._profiles.append(profile)
        self._pub_key_lookup[profile.public_key] = profile
        self._priv_key_lookup[profile.private_key] = profile
        if profile.profile_name is not None:
            self._pname_lookup[profile.profile_name] = profile

    def update(self, profile: Profile):
        our_p = self.lookup_pub_key(profile.public_key)
        if our_p:
            our_p.attrs = profile.attrs
            our_p.update_at = profile.update_at

            # this only happens for our local updates, not those that happen because of type 0 meta events
            if profile.profile_name:
                # profile name changed, delete old lookup
                if our_p.profile_name and our_p.profile_name in self._pname_lookup:
                    del self._pname_lookup[our_p.profile_name]
                our_p.profile_name = profile.profile_name
                self._pname_lookup[our_p.profile_name] = our_p

            # priv key added, its not possible to change a priv k
            # at least it shouldn't be
            if profile.private_key:
                our_p.private_key = profile.private_key

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

    def get_profile(self, profile_key,
                    create_type=None,
                    create_profile_name='adhoc_profile') -> Profile:
        """
        :param profile_key: either priv_key, profile_name or pub_key
        :param create_type: None, 'private' or 'public' if we don't find then an empty profile will be created
                            with profile_key as either public/private ot not if None. This is enough for use in many
                            cases.
        :return: Hopefully found Profile, or if create_type then stub Profile assuming key looked correct else None

        FIXME... as we don't specify key type if there ever ended up bing profile with pub key same as priv key
        it'd never get found using this code....

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
            if not ret and create_type != ProfileList.CREATE_PRIVATE:
                ret = self.lookup_pub_key(profile_key)

        # we didn't find a profile but we'll see if we can just use as priv key...
        # also fallback we don't have db
        if not ret and create_type is not None and Keys.is_key(profile_key):
            if len(profile_key) == 64:
                if create_type == ProfileList.CREATE_PRIVATE:
                    ret = Profile(priv_k=profile_key,
                                  profile_name=create_profile_name)
                elif create_type == ProfileList.CREATE_PUBLIC:
                    ret = Profile(pub_k=profile_key)

        return ret

    def __getitem__(self, item):
        return self._profiles[item]

    def __len__(self):
        return len(self._profiles)


class Contact:

    def __init__(self, owner_pub_k, updated_at, contact_pub_k, relay=None, pet_name=None):
        # see https://github.com/fiatjaf/nostr/blob/master/nips/02.md

        # the pub key of the profile whose contact list the contact has been created from
        self._owner_pub_k = owner_pub_k
        self._updated_at = updated_at

        # this pub key which comes from the event should probably have some basic checks done on it
        # i.e. len, hex str...

        self._contact_pub_k = contact_pub_k
        self._relay = relay
        self._petname = pet_name

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

    @updated_at.setter
    def updated_at(self, at_date):
        self._updated_at = at_date

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

    @staticmethod
    def create_from_event(evt: Event):
        """
        makes the contacts from the data in tags, if there are any problems with a particualr tag it's just skipped
        and won't be added
        :param evt: should be a contact_list (type3 event)
        :return:
        """
        contacts = []

        for c_tag in evt.tags:
            # is it a p type and there is a pubkey
            if c_tag[0] == 'p' and len(c_tag) > 1:
                contact_pub_k = c_tag[1]
                # check the key looks correct
                if Keys.is_key(contact_pub_k):
                    # TODO: relay and pet_name to be added
                    n_contact = Contact(owner_pub_k=evt.pub_key,
                                        updated_at=evt.created_at_ticks,
                                        contact_pub_k=contact_pub_k)
                    contacts.append(n_contact)

        return ContactList(contacts, evt.pub_key)

    def __init__(self, contacts, owner_pub_k):
        self._contacts = contacts
        self._lookup = set()
        self._owner_pub_k = owner_pub_k
        con: Contact
        for con in self._contacts:
            self._lookup.add(con.contact_public_key)

    @property
    def owner_public_key(self):
        return self._owner_pub_k

    @property
    def updated_at(self):
        ret = None
        if self._contacts:
            ret = self._contacts[0].updated_at
        return ret

    @updated_at.setter
    def updated_at(self, at_date):
        c_con: Contact
        for c_con in self._contacts:
            c_con.updated_at = at_date

    def add(self, con: Contact) -> bool:
        ret = False
        if con.contact_public_key not in self._lookup:
            self._lookup.add(con.contact_public_key)
            self._contacts.append(con)
            ret = True
        return ret

    def remove(self, pub_k: str) -> bool:
        ret = False
        if pub_k in self._lookup:
            self._lookup.remove(pub_k)
            for pos in range(0,len(self._contacts)):
                if self._contacts[pos].contact_public_key == pub_k:
                    del self._contacts[pos]
                    break

            ret = True

        return ret

    def follow_keys(self):
        con: Contact
        return [con.contact_public_key for con in self._contacts]

    def diff(self, cmp_contacts: ContactList) -> []:
        """
        :param to_contacts: another contact list
        :return: [pub_ks] that are not in both lists
        """
        con: Contact
        my_keys = [con.contact_public_key for con in self._contacts]
        other_keys = [con.contact_public_key for con in cmp_contacts]

        return list(set(my_keys) - set(other_keys)) + list(set(other_keys) - set(my_keys))


    def __contains__(self, item:Contact):
        return item.contact_public_key in self._lookup

    def get_contact_event(self):
        """
            returns a meta event for this profile that once signed can be posted to relay for update
        """
        c_con: Contact
        contacts = [['p', c_con.contact_public_key] for c_con in self._contacts]
        return Event(kind=Event.KIND_CONTACT_LIST,
                     content='TODO',
                     tags=contacts,
                     pub_key=self.owner_public_key)

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
        FIXME: on_update-> on_profile_update
                add on_contacts_update
    """

    def __init__(self,
                 profile_store: 'ProfileStoreInterface',
                 on_profile_update=None,
                 on_contact_update=None):

        self._store = profile_store
        self._profiles = self._store.select()
        self._on_profile_update = on_profile_update
        self._on_contact_update = on_contact_update

    # update locally rather than via meta 0 event
    # only used to link prov_k or add/change profile name
    def do_update_local(self, p: Profile):
        if self._profiles.lookup_pub_key(p.public_key):
            self._profiles.update(p)
            self._store.update_profile_local(p)
            self._store.update(p)
        else:
            self._profiles.add(p)
            self._store.add(p)

    def do_event(self, sub_id, evt: Event, relay):
        c_profile: Profile
        evt_profile: Profile
        pubkey = evt.pub_key

        if evt.kind == Event.KIND_META:

            c_profile = self._profiles.lookup_pub_key(pubkey)
            evt_profile = Profile(pub_k=pubkey, attrs=evt.content, update_at=evt.created_at_ticks)

            # we only need to do something if the profile is newer than we already have
            if c_profile is None or c_profile.update_at < evt_profile.update_at:
                # not sure about this... probably OK most of the time...
                if c_profile:
                    self._store.update(evt_profile)
                    self._profiles.update(evt_profile)
                else:
                    self._store.add(evt_profile)
                    self._profiles.add(evt_profile)

                # if owner gave us an on_update call with pubkey that has changed, they may want to do something...
                if self._on_profile_update:
                    self._on_profile_update(evt_profile, c_profile)

        elif evt.kind == Event.KIND_CONTACT_LIST:
            # it's not required that we have a profile to import the events
            # though it might be hard to get to the contacts later if we don't as (until we have a profile)
            # as it won't be handing off anything
            existing_contacts = ContactList(contacts=self._store.contacts({'owner': pubkey}),
                                            owner_pub_k=pubkey)

            if existing_contacts.updated_at is None or existing_contacts.updated_at < evt.created_at_ticks:
                c_profile = self._profiles.lookup_pub_key(pubkey)

                # now update
                n_contacts = ContactList.create_from_event(evt)
                self._store.set_contacts(n_contacts)

                # if we do have a profile this will force reload of contacts on next access
                if c_profile:
                    c_profile.contacts = None

                # callback that we updated contacts
                if self._on_contact_update:
                    self._on_contact_update(n_contacts, existing_contacts)

    @property
    def profiles(self) -> ProfileList:
        return self._profiles

    def set_on_update(self, on_update):
        self._on_update = on_update




if __name__ == "__main__":
    from nostr.util import util_funcs
    from pathlib import Path
    from nostr.client.client import Client
    from nostr.client.event_handlers import PrintEventHandler
    from nostr.ident.persist import SQLProfileStore

    logging.getLogger().setLevel(logging.DEBUG)
    nostr_db_file = '%s/.nostrpy/nostrb-client.db' % Path.home()
    backup_dir = '/home/shaun/.nostrpy/'
    my_db = util_funcs.create_sqlite_store(nostr_db_file)
    profile_store = SQLProfileStore(my_db)

    def my_connect(the_client: Client):
        the_client.subscribe(handlers=[PrintEventHandler(),
                                       ProfileEventHandler(profile_store=profile_store)],
                             filters={
                                 'kinds': [Event.KIND_CONTACT_LIST, Event.KIND_META]
                             }
                             )

    c = Client('wss://nostr-pub.wellorder.net', on_connect=my_connect)

    c.start()





    # def my_start(the_client: Client):
    #     the_client.subscribe(handlers=PersistEventHandler(SQLiteEventStore(nostr_db_file)))

    # my_client = Client('wss://nostr-pub.wellorder.net', on_connect=my_start).start()

    # ContactList.import_from_events(SQLLiteStore(nostr_db_file), SQLProfileStore(SQLiteDatabase(nostr_db_file)))
    # Profile.import_from_file('/home/shaun/.nostrpy/local_profiles.csv',SQLProfileStore(SQLiteDatabase(nostr_db_file)))




