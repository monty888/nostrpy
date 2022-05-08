import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from nostr.ident.profile import Profile, ProfileList, Contact, ContactList
from nostr.client.persist import ClientEventStoreInterface
from nostr.event import Event
from db.db import Database, SQLiteDatabase
from data.data import DataSet
from nostr.util import util_funcs


class ProfileStoreInterface(ABC):
    """
        interface to implement for storage of nostr profiles,
        maybe we'll only have the sql version anyhow...but hopefully this
        will stop us putting SQL all over the place...

    """

    @abstractmethod
    def add(self, p: Profile):
        """
        :param p: add profile to the store
        :return:
        """

    @abstractmethod
    def update(self, p: Profile):
        """
        :param p: update profile in store
        :return:
        """

    @abstractmethod
    def update_profile_local(self, p: Profile):
        """
        associates a profile with a local name
        :param profile_name:
        :param private_key:
        :return:
        """

    @abstractmethod
    def select(self, filter={}) -> ProfileList:
        """
        TODO : filter support
        :param filter: [
            {
                'public_key' : [],
                'private_key' : [],
                'profile_name' : []
            },...
        ]
        :return: returns all profiles in store -
        """

    @abstractmethod
    def contacts(self):
        """
        :return: contact list that owner_pk is following
        """

    @abstractmethod
    def set_contacts(self, contacts: ContactList):
        """
            inserts a contact list into the db, note that all contacts for the listowner are first deleted.
            this is as expected for when we recieve a contact list via a relay. We're also going to have local contacts
            (followed but not published to relay) in that case maybe we won't want to rewrite the entire contact list
            on update. For now we'll just keep it simple so both done the same.
        """


    # method below should work as long as the abstract methods have been implemented
    def new_profile(self,
                    name,
                    attrs=None,
                    priv_key=None) -> Profile:
        """
        creates a new profile and adds it to the db
        TODO: we should probably check that name+pubkey doesn't already exists
        :param profile_store:
        :param priv_key:
        :param name:
        :param attrs:
        :return:
        """

        keys = Profile.get_new_key_pair(priv_key=priv_key)
        p = Profile(priv_k=keys['priv_k'],
                    pub_k=keys['pub_k'][2:],
                    profile_name=name,
                    attrs=attrs,
                    # update_at as zero so attrs will be update over if we get anything from relay
                    update_at=0)

        all = self.select()

        if all.lookup_profilename(name) or all.lookup_priv_key(keys['priv_k']):
            raise Exception('Profile:new_profile %s already exists' % name)

        self.add(p)

        return p

    def export_file(self, filename, names=None):
        """
        export local profiles to backup file in csv format

        :param filename:    csv export file
        :param db_file:     sql_lite db file
        :param names:       if supplied only these profiles will be exported
        :return:
        """

        profiles = self.select()
        c_p: Profile
        to_output = []
        for c_p in profiles:
            if c_p.private_key:
                if names is None or c_p.profile_name in names:
                    to_output.append([
                        c_p.private_key,
                        c_p.public_key,
                        c_p.profile_name,
                        json.dumps(c_p.attrs),
                        util_funcs.date_as_ticks(c_p.update_at)
                    ])

        if to_output:
            DataSet([
                'priv_k', 'pub_k', 'profile_name', 'attrs', 'updated_at'
            ], to_output).save_csv(filename)

    def import_file(self,
                    filename,
                    names=None):
        """
        import profiles into a db that were previously output to file using <name>
        :param filename:
        :param profile_store:
        :param names:
        :return:
        """
        profiles = DataSet.from_CSV(filename)
        if names:
            profiles = profiles.value_in('profile_name', names)

        ret = {
            'added': set(),
            'existed': set()
        }
        for p in profiles:
            try:
                to_add = Profile(
                    priv_k=p['priv_k'],
                    pub_k=p['pub_k'],
                    profile_name=p['profile_name'],
                    # probably some issue with csv/json together code work out why just the attrs str is no good at some point
                    attrs=p['attrs'].replace('""', '"').replace('"{', "{").replace('}"', "}"),
                    update_at=util_funcs.date_as_ticks(datetime.now())
                )
                self.add(to_add)
                ret['added'].add(to_add)
            except Exception as e:
                # already exists?
                ret['existed'].add(to_add)
                logging.debug('Profile::import_from_file - profile: %s - %s' % (p['profile_name'], e))

        return ret

    def import_profiles_from_events(self,
                                    event_store: ClientEventStoreInterface,
                                    since=None):
        """
        :param event_store:
        :param since:
        :return:
        """

        # get profile update events
        evts = event_store.get_filter({
            'kinds': [Event.KIND_META],
            'since': since
        })

        profiles = self.select()
        """
            now cycle through either adding or inserting only the most recent profile update
        """
        updated = set()
        evt : Event
        for evt in evts:
            p = Profile(pub_k=evt.pub_key,
                        attrs=evt.content,
                        update_at=evt.created_at)
            if p.public_key not in updated:

                exists = profiles.matches('pub_k', p.public_key)
                if not exists:
                    self.add(p)
                else:
                    if (util_funcs.date_as_ticks(p.update_at) > exists[0]['updated_at']):
                        self.update(p)
                    else:
                        logging.debug('Profile:import_from_events %s already up to date, ignored' % p.public_key)

                # done with this key, any other events are older
                updated.add(p.public_key)

    def import_contacts_from_events(self,
                                    event_store: ClientEventStoreInterface,
                                    since=None):
        """
        look other events we have in db and create contacts from these
        TODO: client currently doesnt delete old contact events like the relay does so it probable that more updates
                are being done then required..FIX
                in anycase it's likely we wouldn't normally use this and it'd be done adhoc in the same way we build up
                profiles as event handler on client
        """

        # contact lists from events
        c_list_updates = event_store.get_filter({
            'since': since,
            'kinds': Event.KIND_CONTACT_LIST
        })

        # to check if event is newer than what we already have if any
        existing = self.contacts()

        """
            in the case of contact list when a user updates its done from fresh so we just check that the list
            event is newer then any contact we have if any for the owner and if so delete all thier contacts and import 
            from the new list...
        """
        c_evt: Event
        for c_evt in c_list_updates:
            exists = existing.matches('pub_k_owner', c_evt.pub_key)
            is_newer = True
            if exists and exists[0]['updated_at'] <= c_evt.created_at_ticks:
                is_newer = False

            contacts = []
            if is_newer:

                for c_tag in c_evt.tags:
                    contacts.append(Contact(c_evt.pub_key,
                                            c_evt.created_at_ticks,
                                            c_tag))
                if contacts:
                    profile_contacts = ContactList(contacts)
                    self.set_contacts(profile_contacts)


class TransientProfileStore(ProfileStoreInterface):
    """
        in memory profile store - normally we wouldn't, you have to request all META, CONTACT_LIST events
        from relays again on start up
    """
    def __init__(self):
        self._profiles = {}

    def add(self, p: Profile):
        self._profiles[p.public_key] = p

    def update(self, p: Profile):
        if p.public_key in self._profiles:
            to_update: Profile = self._profiles[p.public_key]
            to_update.attrs = p.attrs
            to_update.update_at = p.update_at

    def update_profile_local(self, p: Profile):
        if p.public_key in self._profiles:
            to_update: Profile = self._profiles[p.public_key]
            to_update.profile_name = p.profile_name
            to_update.private_key = p.private_key

    def select(self, filter={}) -> ProfileList:
        profiles = []
        for i, c_p in enumerate(self._profiles):
            profiles.append(c_p)

        return ProfileList(profiles)

    def contacts(self):
        pass

    def set_contacts(self, contacts: ContactList):
        pass


class SQLProfileStore(ProfileStoreInterface):
    """
        SQL implementation of ProfileStoreInterface
    """
    def __init__(self, db: Database):
        self._db = db

    @staticmethod
    def _get_profile_sql_filter(filter={}, placeholder='?'):
        """
        :param filter: {
            public_key : [],
            profile_name : [],
            private_key : []
        }
        values are or'd

        :return: {
            sql : str
            args :[]
        } to execute the query
        """

        sql_arr = ['select * from profiles']
        args = []

        join = ' where '

        def _add_for_field(f_name, db_field):
            nonlocal args
            nonlocal join

            if f_name in filter:
                values = filter[f_name]
                if not hasattr(values, '__iter__') or isinstance(values, str):
                    values = [values]

                sql_arr.append(
                    ' %s %s in (%s) ' % (join,
                                            db_field,
                                            ','.join([placeholder] * len(values)))
                )

                args = args + values
                join = ' or '

        _add_for_field('public_key','pub_k')
        _add_for_field('profile_name', 'profile_name')
        _add_for_field('private_key', 'priv_k')

        # for now we're ordering what we return
        sql_arr.append("""
        order by 
            case when profile_name ISNULL or profile_name='' then 1 else 0 end, profile_name,
            case when name ISNULL or name='' then 1 else 0 end, name
        """)

        return {
            'sql': ''.join(sql_arr),
            'args': args
        }

    @staticmethod
    def _get_contacts_sql_filter(filter={}, placeholder='?'):
        """
        :param filter: {
            owner : [],
            contact : []
        }
        values are or'd
        probably you'd only use one or the other

        owner, these profile contacts
        contact, returns those that we are contact of (they follow us) at least as best as we can see from relays
        we've used
        NOTE: this all via what has been published as Event kind contact, that is made public but theres no reason that
        user couldn't have many local follow/contact list that they don't publish... we'll want to do that too

        :return: {
            sql : str
            args :[]
        } to execute the query
        """

        sql_arr = ['select * from contacts']
        args = []

        join = ' where '

        # exactly the same as in _get_profile_sql_filter but it's just easier like this
        def _add_for_field(f_name, db_field):
            nonlocal args
            nonlocal join

            if f_name in filter:
                values = filter[f_name]
                if not hasattr(values, '__iter__') or isinstance(values, str):
                    values = [values]

                sql_arr.append(
                    ' %s %s in (%s) ' % (join,
                                            db_field,
                                            ','.join([placeholder] * len(values)))
                )

                args = args + values
                join = ' or '

        _add_for_field('owner','pub_k_owner')
        _add_for_field('contact', 'pub_k_contact')

        # no ordering for contacts currently

        return {
            'sql': ''.join(sql_arr),
            'args': args
        }

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
                    set attrs=?, name=?, picture=?, updated_at=?
                    where pub_k=?
            """
        args = [
            json.dumps(p.attrs),
            p.get_attr('name'), p.get_attr('picture'),
            util_funcs.date_as_ticks(p.update_at),
            p.public_key
        ]
        logging.debug('SQLProfileStore::update sql: %s args: %s' % (sql, args))
        self._db.execute_sql(sql, args)

    def update_profile_local(self, p: Profile):
        sql = """
                update profiles 
                    set profile_name=?, priv_k=?
                    where pub_k=?
            """
        args = [
            p.profile_name, p.private_key,
            p.public_key
        ]
        logging.debug('SQLProfileStore::update_profile_local sql: %s args: %s' % (sql, args))
        self._db.execute_sql(sql, args)

    def select(self, filter={}) -> ProfileList:
        filter_query = self._get_profile_sql_filter(filter,
                                                    placeholder=self._db.placeholder)
        data = self._db.select_sql(sql=filter_query['sql'],
                                   args=filter_query['args'])

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

    # note not returning contact list cause it's shit maybe will do eventually or get
    # rid of contact list class altogether?
    def contacts(self, filter):
        filter_query = self._get_contacts_sql_filter(filter,
                                                     placeholder=self._db.placeholder)

        return self._db.select_sql(sql=filter_query['sql'],
                                   args=filter_query['args'])

    def set_contacts(self, contacts: ContactList):
        c_contact: Contact
        add_data = []
        for c_contact in contacts:
            add_data.append([
                contacts.owner_public_key,
                c_contact.contact_public_key,
                contacts.updated_at
            ])

        self._db.execute_batch(
            [
                {
                    'sql': 'delete from contacts where pub_k_owner=%s' % self._db.placeholder,
                    'args': [contacts.owner_public_key]
                },
                {
                    'sql': """insert into contacts (pub_k_owner, pub_k_contact, updated_at) 
                                values (%s)""" % ','.join([self._db.placeholder]*3),
                    'args': add_data
                }
            ]
        )


class SQLiteProfileStore(SQLProfileStore):
    """
        SQLite specific bits create and destroy. unless doing those SQLProfileStore shouold be fine
    """
    def __init__(self, db_file):
        self._db_file = db_file
        super().__init__(SQLiteDatabase(self._db_file))

    def create(self):
        self._db.execute_batch([
            {
                'sql': """
                    create table profiles(
                        priv_k text,
                        pub_k text primary key,  
                        profile_name text,
                        attrs text,
                        name text,
                        picture text,
                        updated_at int
                    )
            """
            },
            {
                'sql': """
                    create table contacts(
                        pub_k_owner text,
                        pub_k_contact text,
                        alias text,
                        source text,
                        updated_at int
                    )
                """
            }

        ])

    def destroy(self):
        self._db.execute_batch([
            {
                'sql': 'drop table profiles'
            },
            {
                'sql': 'drop table contacts'
            }
        ])