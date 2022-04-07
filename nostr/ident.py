"""
our profile pub/private key along, aswell as profile of others we see by looking at event types 0
and contact lists as NIP2

FIXME: the import methods should be moved to persist, this will allow us to add typehints there which we can't do
at the moment because of circular references

FIXME: methods that we have as from_db are actually just sql lite... eventually would want to be able to sub a
different db/persistance layer with min code changes

"""
import json
import sys
from json import JSONDecodeError
import secp256k1
import logging

from data.data import DataSet
from db.db import Database, SQLiteDatabase
from nostr.client.client import Event
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
            pk =secp256k1.PrivateKey(priv_key)

        return {
            'priv_k' : pk.serialize(),
            'pub_k' : pk.pubkey.serialize(compressed=True).hex()
        }

    @classmethod
    def new_profile(cls, name, db_file, attrs=None, priv_key=None):
        """
        creates a new profile and adds it to the db
        TODO: we should probably check that name+pubkey doesn't already exists
        :param name:
        :param attrs:
        :param db_file:
        :return:
        """
        s = Store(db_file)
        keys = Profile.get_new_key_pair(priv_key=priv_key)
        p = Profile(priv_k=keys['priv_k'],
                    pub_k=keys['pub_k'],
                    profile_name=name,
                    attrs=attrs)

        # because we load using the name it needs to be unique, in future we might have versions
        exists = DataSet.from_sqlite(db_file, 'select profile_name from profiles where profile_name=?', [name])
        if exists:
            raise Exception('Profile:new_profile %s already exists' % name)

        s.add_profile(p)

    @classmethod
    def import_from_events(cls, db_file, since=None):
        """
        :param db_file:
        :param since: ticks or datetime
        :return:

        """
        s = Store(db_file)

        # profiles from events
        profile_updates = s.load_events(Event.KIND_META, since)
        # profile info as we have it, ignore are local profiles
        profiles = DataSet.from_sqlite(db_file, 'select * from profiles --where priv_k isNull')

        """
            now cycle through either adding or inserting only the most recent profile update
        """
        updated = set()

        for c_p in profile_updates:
            p = Profile(pub_k=c_p['pubkey'],attrs=c_p['content'],update_at=c_p['created_at'])
            if p.public_key not in updated:

                exists = profiles.matches('pub_k', p.public_key)
                if not exists:
                    s.add_profile(p)
                else:
                    if(util_funcs.date_as_ticks(p.update_at) > exists[0]['updated_at']):
                        s.update_profile(p)
                    else:
                        logging.debug('Profile:import_from_events %s already up to date, ignored' % p.public_key)

                # done with this key, any other events are older
                updated.add(p.public_key)

    @classmethod
    def load_from_db(cls, db: Database, key):
        """
            load a single profile from db using key which should be either profilename, private key, or publickey
            where it's profilename or privatekey then we're able to sign, its a local/users profile
            if the match is found on pubkey then it's a remote key and can't be used to post messages
            match must be exact
        """
        sql = """
            select * from profiles 
                -- see why we have profiles that are emptystr? anyway we want one with a priv_k if its us to sign key 
                where profile_name=:? or priv_k=:? or pub_k=:? 
                --and priv_k NOTNULL
                order by updated_at desc
        """

        profiles = db.select_sql(sql, [key, key, key])
        if not profiles:
            raise UnknownProfile('Profile::load_from_db using key=%s, not found' % key)
        p = profiles[0]
        return Profile(
            priv_k=p['priv_k'],
            pub_k=p['pub_k'],
            profile_name=p['profile_name'],
            attrs=p['attrs'],
            update_at=p['updated_at']
        )

    @classmethod
    def export_from_db(cls, filename, db_file, names=None):
        """
        export local profiles to backup file in csv format

        :param filename:    csv export file
        :param db_file:     sql_lite db file
        :param names:       if supplied only these profiles will be exported
        :return:
        """
        sql = 'select priv_k,pub_k,profile_name,attrs from profiles where priv_k is not null'
        profiles = DataSet.from_sqlite(db_file, sql)
        if names:
            profiles = profiles.value_in('profile_name', names)

        profiles.save_csv(filename)

    @classmethod
    def import_from_file(cls, filename, db, names=None):
        profiles = DataSet.from_CSV(filename)
        if names:
            profiles = profiles.value_in('profile_name', names)

        for p in profiles:
            try:
                profile_store = SQLProfileStore(db)
                profile_store.add_profile(Profile(
                    priv_k=p['priv_k'],
                    pub_k=p['pub_k'],
                    profile_name=p['profile_name'],
                    attrs=p['attrs'],
                    update_at=util_funcs.date_as_ticks(datetime.now())
                ))
            except Exception as e:
                # already exists?
                logging.debug('Profile::import_from_file - profile: %s - %s' % (p['profile_name'], e))

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

    @property
    def name(self):
        ret = None
        if 'name' in self.attrs:
            ret = self.attrs['name']
        return ret

    # only exists if us
    @property
    def private_key(self):
        return self._priv_k

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

    def get_attr(self, name):
        # returns vale for named atr, None if it isn't defined
        ret = None
        if name in self._attrs:
            ret = self._attrs[name]
        return ret

    @property
    def update_at(self):
        # note as datetime - convert to ticks before storing in dd
        return self._update_at

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

    @classmethod
    def create_profiles_from_db(cls, db: Database):
        """
        loads all profiles from db, at somepoint this might not be a good idea but OK for now
        includes local profiles also
        :param db_file:
        :return:
        """
        # data = db.select_sql('select * from profiles --where priv_k isnull')
        return SQLProfileStore(db).select()

    @classmethod
    def add_profile_db(cls, db: Database, p: Profile):
        SQLProfileStore(db).add(p)

    @classmethod
    def update_profile_db(cls, db: Database, p: Profile):
        SQLProfileStore(db).update(p)

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

    @classmethod
    def import_from_events(cls, db_file, since=None):
        """
        :param db_file:
        :param since: ticks or datetime
        :return:

        TODO: we probably want to have create_at in profile so we don't end up rolling back if we get data from older
        source. Also this would allow update of local profile if pushed from somewhere else

        """
        s = Store(db_file)
        # contact lists from events
        c_list_updates = s.load_events(Event.KIND_CONTACT_LIST,since)
        # to check if event is newer than what we already have if any
        existing = DataSet.from_sqlite(db_file, 'select pub_k_owner, updated_at from contacts')

        """
            in the case of contact list when a user updates its done from fresh so we just check that the list
            event is newer then any contact we have if any for the owner and if so delete all thier contacts and import 
            from the new list...
        """

        for c_p in c_list_updates:
            exists = existing.matches('pub_k_owner', c_p['pubkey'])
            is_newer = True
            if exists and exists[0]['updated_at']<=c_p['created_at']:
                is_newer = False

            if is_newer:
                contacts = []
                try:
                    tag_str = c_p['tags'].replace('\'','"')
                    tags = json.loads(tag_str)

                    for c_con in tags:
                        contacts.append(Contact(c_p['pubkey'], c_p['created_at'], c_con))

                    s.update_contact_list(c_p['pubkey'], contacts)

                except JSONDecodeError as e:
                    logging.debug('ContactList::import_from_events error with tags %s' % e)


class ProfileEventHandler:
    """
        loads all profiles from db and then keeps that mem copy up to date whenever any meta events are recieved
        obvs at some point keeping all profiles in memory might not work so well but OK at the moment....
        TODO: check and verify NIP05 if profile has it
    """

    def __init__(self, db: Database, on_update=None):
        self._db = db
        self._profiles = ProfileList.create_profiles_from_db(self._db)
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
                    ProfileList.update_profile_db(self._db, evt_profile)
                else:
                    ProfileList.add_profile_db(self._db, evt_profile)
                    self._profiles.append(evt_profile)

                # if owner gave us an on_update call with pubkey that has changed, they may want to do something...
                if self._on_update:
                    self._on_update(evt_profile, c_profile)

    @property
    def profiles(self):
        return self._profiles

    def set_on_update(self, on_update):
        self._on_update = on_update


class SQLProfileStore:

    def __init__(self, db: Database):
        self._db = db

    def add(self, p: Profile):
        sql = """
            insert into 
                profiles (priv_k, pub_k, profile_name, attrs, name, picture, updated_at) 
                        values(?,?,?,?,?,?,?)
            """
        args = [
            p.private_key, p.public_key,
            p.profile_name, json.dumps(p.attrs),
            p.get_attr('name'), p.get_attr('picture'),
            util_funcs.date_as_ticks(p.update_at)
        ]

        self._db.execute_sql(sql, args)

    def update(self, p: Profile):
        sql = """
                update profiles 
                    set profile_name=?, attrs=?, name=?, picture=?, updated_at=?
                    where pub_k=?
            """
        args = [
            p.profile_name, json.dumps(p.attrs),
            p.get_attr('name'), p.get_attr('picture'),
            util_funcs.date_as_ticks(p.update_at),
            p.public_key
        ]
        logging.debug('SQLProfileStore::update profile sql: %s args: %s' % (sql, args))
        self._db.execute_sql(sql, args)

    def select(self) -> ProfileList:
        data = self._db.select_sql("""
        select * from profiles 
            order by 
            case when profile_name ISNULL or profile_name='' then 1 else 0 end, profile_name,
            case when name ISNULL or name='' then 1 else 0 end, name
        """)
        profiles = []
        for c_r in data:
            profiles.append(Profile(
                priv_k=c_r['priv_k'],
                pub_k=c_r['pub_k'],
                profile_name=c_r['profile_name'],
                attrs=c_r['attrs'],
                update_at=c_r['updated_at']
            ))

        return ProfileList(profiles)


class SQLiteProfileStore(SQLProfileStore):

    def __init__(self, db_file):
        self._db_file = db_file
        super().__init__(SQLiteDatabase(self._db_file))

    def create(self):
        profile_tmpl = DataSet(heads=['priv_k', 'pub_k', 'profile_name', 'attrs', 'name', 'picture', 'updated_at'])
        profile_tmpl.create_sqlite_table(self._db_file, 'profiles', {
            # because we alway have to have
            'pub_k': {
                'type': 'primary key not null'
            },
            'updated_at': {
                'type': 'int'
            }
        })


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    nostr_db_file = '/home/shaun/.nostrpy/nostr-client.db'
    backup_dir = '/home/shaun/.nostrpy/'
    # s = Store(nostr_db_file)
    Profile.import_from_file(backup_dir+'local_profiles.csv', SQLiteDatabase(nostr_db_file))
