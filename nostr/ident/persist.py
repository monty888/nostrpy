import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from nostr.ident.profile import Profile, ProfileList, Contact, ContactList
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
    def select(self) -> ProfileList:
        """
        :return: returns all profiles in store -
        TODO: add filter so we don't have to return everything...
        """

    @abstractmethod
    def contacts(self):
        """
        working on not sure
        :return:
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

        for p in profiles:
            try:
                self.add(Profile(
                    priv_k=p['priv_k'],
                    pub_k=p['pub_k'],
                    profile_name=p['profile_name'],
                    # probably some issue with csv/json together code work out why just the attrs str is no good at some point
                    attrs=p['attrs'].replace('""', '"').replace('"{', "{").replace('}"', "}"),
                    update_at=util_funcs.date_as_ticks(datetime.now())
                ))
            except Exception as e:
                # already exists?
                logging.debug('Profile::import_from_file - profile: %s - %s' % (p['profile_name'], e))


class SQLProfileStore(ProfileStoreInterface):
    """
        SQL implementation of ProfileStoreInterface
    """
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

    def contacts(self):
        return self._db.select_sql('select * from contacts')

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