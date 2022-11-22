import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from enum import Enum
from nostr.ident.profile import Profile, ProfileList, Contact, ContactList
# from nostr.client.persist import ClientEventStoreInterface
from nostr.event.persist import ClientEventStoreInterface
from nostr.event.event import Event
from db.db import Database, SQLiteDatabase, QueryFromFilter
from data.data import DataSet
from nostr.util import util_funcs
from nostr.encrypt import Keys
from copy import copy


class ProfileType(Enum):
    LOCAL = 0       # ours/ profile with priv_k
    REMOTE = 1      # not ours/profile without priv_k
    ANY = 2         # either of the above


class ProfileStoreInterface(ABC):
    """
        interface to implement for storage of nostr profiles,
        maybe we'll only have the sql version anyhow...but hopefully this
        will stop us putting SQL all over the place...

    """

    # @abstractmethod
    # def add(self, p: Profile):
    #     """
    #     :param p: add profile to the store
    #     :return:
    #     """
    #
    # @abstractmethod
    # def update(self, p: Profile):
    #     """
    #     :param p: update profile in store
    #     :return:
    #     """
    #
    # @abstractmethod
    # def update_profile_local(self, p: Profile):
    #     """
    #     associates a profile with a local name
    #     :param profile_name:
    #     :param private_key:
    #     :return:
    #     """

    @abstractmethod
    def put_profile(self, p: Profile, is_local=False):
        """
        replaces add, update and update_profile_local
        :param p:
        :param is_local:
        :return:
        """

    @abstractmethod
    def select_profiles(self, filter={}, profile_type=ProfileType.ANY) -> ProfileList:
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
    def select_contacts(self, filter):
        """
        :return: contact list that owner_pk is following
        """

    # @abstractmethod
    # def set_contacts(self, contacts: ContactList):
    #     """ TODGO
    #         inserts a contact list into the db, note that all contacts for the listowner are first deleted.
    #         this is as expected for when we recieve a contact list via a relay. We're also going to have local contacts
    #         (followed but not published to relay) in that case maybe we won't want to rewrite the entire contact list
    #         on update. For now we'll just keep it simple so both done the same.
    #     """
    @abstractmethod
    def put_contacts(self, contacts: ContactList):
        """
        replaces set_contacts
        :param contacts:
        :return:
        """

    @abstractmethod
    def newest(self):
        """
        returns the date of the most recently updated profile...
        note as this is self reported care should be taken not to accept profiles with update_at set too far in the futre
        alternatively we can just set any future dated to the date when we receive?
        :return: time in ticks
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

        keys = Keys.get_new_key_pair(priv_key=priv_key)
        p = Profile(priv_k=keys['priv_k'],
                    pub_k=keys['pub_k'][2:],
                    profile_name=name,
                    attrs=attrs,
                    # update_at as zero so attrs will be update over if we get anything from relay
                    update_at=0)

        all = self.select_profiles()

        if all.lookup_profilename(name) or all.lookup_priv_key(keys['priv_k']):
            raise Exception('Profile:new_profile %s already exists' % name)

        self.put_profile(p, is_local=True)

        return p

    def export_file(self, filename, names=None):
        """
        export local profiles to backup file in csv format

        :param filename:    csv export file
        :param db_file:     sql_lite db file
        :param names:       if supplied only these profiles will be exported
        :return:
        """

        profiles = self.select_profiles()
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
                        c_p.update_at
                    ])

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
                                    evts: [Event] = None,
                                    since = None):
        """
        :param evts:
        :param event_store:
        :param since:
        :return:
        """

        # if no events given then events since from events_store
        if evts is None:
            evt_filter = {
                'kinds': [Event.KIND_META]
            }
            if since is not None:
                evt_filter['since'] = since
                evts = event_store.get_filter(evt_filter)
        else:
            def my_sort(evt:Event):
                return evt.created_at_ticks
            evts.sort(key=my_sort, reverse=True)

        profiles = self.select_profiles()
        """
            now cycle through either adding or inserting only the most recent profile update
        """
        updated = set()
        evt: Event
        existing_p: Profile
        for evt in evts:
            # ignore anything other than meta events
            if evt.kind != Event.KIND_META:
                continue

            p = Profile(pub_k=evt.pub_key,
                        attrs=evt.content,
                        update_at=evt.created_at)
            if p.public_key not in updated:

                existing_p = profiles.lookup_pub_key(p.public_key)
                if not existing_p:
                    self.add(p)
                else:
                    if p.update_at > existing_p.update_at:
                        self.update(p)
                    else:
                        logging.debug('Profile:import_from_events %s already up to date, ignored' % p.public_key)

                # done with this key, any other events are older
                updated.add(p.public_key)

    def import_contacts_from_events(self,
                                    event_store: ClientEventStoreInterface,
                                    evts: [Event] = None,
                                    since=None):
        """
        look other events we have in db and create contacts from these
        """

        # contact lists from events
        if evts is None:
            my_event_filter = {
                'kinds': Event.KIND_CONTACT_LIST
            }
            if since is not None:
                my_event_filter['since'] = since

            evts = event_store.get_filter(my_event_filter)
        else:
            def my_sort(evt:Event):
                return evt.created_at_ticks
            evts.sort(key=my_sort, reverse=True)

        # to check if event is newer than what we already have if any
        existing = self.select_contacts({})
        lookup = {}
        c_c: Contact
        for c_c in existing:
            lookup[c_c.owner_public_key] = c_c

        """
            in the case of contact list when a user updates its done from fresh so we just check that the list
            event is newer then any contact we have if any for the owner and if so delete all thier contacts and import 
            from the new list...
        """
        c_evt: Event
        existing_contact: Contact

        for c_evt in evts:
            if c_evt.kind != Event.KIND_CONTACT_LIST:
                continue
            existing_contact = None
            is_newer = True
            if c_evt.pub_key in lookup:
                existing_contact = lookup[c_evt.pub_key]

            # the contact info we already have is newer
            if existing_contact is not None and existing_contact.updated_at <= c_evt.created_at_ticks:
                is_newer = False

            if is_newer:
                self.set_contacts(ContactList.create_from_event(c_evt))


class MemoryProfileStore(ProfileStoreInterface):
    """
        in memory profile store - normally we wouldn't use,
        you'd have to request all META, CONTACT_LIST events
        from relays again on start up

        is this almost the samething as ProfileList? merge or
    """

    def __init__(self):
        self._profiles = {}
        self._contacts = {}

    def select_profiles(self, filter={}, profile_type=ProfileType.ANY) -> ProfileList:
        c_p: Profile
        profiles: [Profile] = []

        for i, pub_k in enumerate(self._profiles):
            c_p = self._profiles[pub_k]

            matches = 'public_key' in filter and pub_k in filter['public_key'] \
                      or 'private_key' in filter and c_p.private_key in filter['private_key'] \
                      or 'profile_name' in filter and c_p.profile_name in filter['profile_name'] \
                      or len(filter) == 0

            if matches:
                c_p = copy(c_p)
                if profile_type == ProfileType.ANY:
                    profiles.append(c_p)
                elif profile_type == ProfileType.LOCAL and c_p.private_key is not None:
                    profiles.append(c_p)
                elif profile_type == ProfileType.REMOTE and c_p.private_key is None:
                    profiles.append(c_p)
        return ProfileList(profiles)

    def select_contacts(self, filter):
        """
        :return: contact list that owner_pk is following
        """
        ret = []
        cl: ContactList

        if 'owner' in filter:
            owner = filter['owner']
            if not hasattr(owner, '__iter__') or isinstance(owner, str):
                owner = [owner]

            for c_owner in owner:
                if c_owner in self._contacts:
                    cl = self._contacts[c_owner]
                    ret = ret + cl.contacts

        # look into better way to do this then looking throught who everyone is following
        if 'contact' in filter:
            contact = filter['contact']
            if not hasattr(contact, '__iter__') or isinstance(contact, str):
                contact = [contact]
            follow_lookup = {}
            for i, owner_k in enumerate(self._contacts):
                cl = self._contacts[owner_k]
                for f_k in cl.follow_keys():
                    if f_k not in follow_lookup:
                        follow_lookup[f_k] = set()
                    follow_lookup[f_k].add(cl.owner_public_key)
            now = datetime.now()
            for c_contact in contact:
                if c_contact in follow_lookup:
                    for c_k in follow_lookup[c_contact]:
                        ret.append(Contact(
                            owner_pub_k=c_k,
                            contact_pub_k=c_contact,
                            updated_at=now
                        ))

        return ret

    def _put_profile(self, p: Profile, is_local=False):
        if is_local or not p.public_key in self._profiles:
            self._profiles[p.public_key] = copy(p)
        else:
            o_p: Profile = self._profiles[p.public_key]
            o_p.attrs = p.attrs
            o_p.update_at = p.update_at

    def put_profile(self, p: Profile, is_local=False):
        if hasattr(p, '__iter__'):
            for c_p in p:
                self._put_profile(c_p, is_local)
        else:
            self._put_profile(p, is_local)

    def _put_contacts(self, contacts: ContactList):
        # TODO: this is only a shallow copy, changing a contact would change it in the store
        #  which is not the same as we'd get with an SQL based store... should probably fix this!
        #  implement deepcopy on contactlist
        self._contacts[contacts.owner_public_key] = copy(contacts)

    def put_contacts(self, contacts: ContactList):
        if hasattr(contacts, '__iter__'):
            for c_c in contacts:
                self._put_contacts(c_c)
        else:
            self.put_contacts(contacts)

    def newest(self):
        """
            TODO: actually implement, though in most cases if we're looking for newest it will be at startup
             in which case mem store would be empty and so 0 is correct
        """
        return 0


class SQLProfileStore(ProfileStoreInterface):
    """
        SQL implementation of ProfileStoreInterface
        NOTE: batch methods are only correct if events are ordered old>newest

    """

    def __init__(self, db: Database):
        self._db = db

    @staticmethod
    def _get_profile_sql_filter(filter={},
                                profile_type=ProfileType.ANY,
                                placeholder='?'):

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

        my_q = QueryFromFilter(select_sql='select * from profiles',
                               filter=filter,
                               placeholder=placeholder,
                               alias={
                                   'public_key': 'pub_k',
                                   'private_key': 'priv_k'
                               }).get_query()

        join = my_q['join']
        if join == ' or ':
            join = ' and '
        if profile_type == ProfileType.LOCAL:
            my_q['sql'] = my_q['sql'] + (' %s priv_k is not null ' % join)
        elif profile_type == ProfileType.REMOTE:
            my_q['sql'] = my_q['sql'] + (' %s priv_k is null ' % join)

        # for now we're ordering what we return
        my_q['sql'] = my_q['sql'] + """
        order by 
            case when profile_name ISNULL or profile_name='' then 1 else 0 end, trim(profile_name) COLLATE NOCASE,
            case when name ISNULL or name='' then 1 else 0 end, trim(name)  COLLATE NOCASE
        """

        return {
            'sql': my_q['sql'],
            'args': my_q['args']
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

    def _prepare_put_profile(self, p: Profile, is_local=False, batch=None):
        if batch is None:
            batch = []

        if is_local:
            sql = """
                insert or replace into 
                    profiles 
                        (priv_k, pub_k, profile_name, attrs, name, picture, updated_at)
                        values(?,?,?,?,?,?,?)
                on conflict(pub_k)
                do update set 
                    priv_k = excluded.priv_k,
                    profile_name = excluded.profile_name,
                    attrs = excluded.attrs,
                    name = excluded.name,
                    picture = excluded.picture,
                    updated_at = excluded.updated_at
                where excluded.updated_at > updated_at
                    
            """
            args = [
                p.private_key, p.public_key,
                p.profile_name, json.dumps(p.attrs),
                p.get_attr('name'), p.get_attr('picture'),
                p.update_at
            ]
        else:
            sql = """
                insert or replace into 
                    profiles (pub_k, attrs, name, picture, updated_at) 
                            values(?,?,?,?,?)
                on conflict(pub_k)
                do update set 
                    attrs = excluded.attrs,
                    name = excluded.name,
                    picture = excluded.picture,
                    updated_at = excluded.updated_at
                where excluded.updated_at > updated_at
            """
            args = [
                p.public_key,
                json.dumps(p.attrs),
                p.get_attr('name'), p.get_attr('picture'),
                p.update_at
            ]
        batch.append({
            'sql': sql,
            'args': args
        })

        return batch

    def put_profile(self, p: Profile, is_local=False):
        """
        replace add/update/update_profile_local with single put method
        :param p: p single or [] of profiles batches have to be all of same type and expect we'd only use for nonlocal
        :param is_local: if local profile name,prov_k also included in update
        :return:
        """
        batch = []
        if not hasattr(p, '__iter__'):
            p = [p]

        for c_p in p:
            self._prepare_put_profile(c_p, is_local, batch)

        return self._db.execute_batch(batch)

    def select_profiles(self, filter={}, profile_type=ProfileType.ANY) -> ProfileList:
        filter_query = SQLProfileStore._get_profile_sql_filter(filter,
                                                               profile_type=profile_type,
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

    def select_contacts(self, filter):
        """
            returned as a list of contacts rather than a contact as the contacts may belong to more than
            one profile dependent on the filter. Up to the caller to make sense of things, if know that
            the query can only return for one then can just do ContactList(contacts)
        """

        filter_query = self._get_contacts_sql_filter(filter,
                                                     placeholder=self._db.placeholder)

        data = self._db.select_sql(sql=filter_query['sql'],
                                   args=filter_query['args'])

        # convert what we got from db into contactlist
        ret = []

        for c_contact in data:
            ret.append(
                Contact(owner_pub_k=c_contact['pub_k_owner'],
                        updated_at=c_contact['updated_at'],
                        contact_pub_k=c_contact['pub_k_contact']
                        # TODO: relay and petname
                        )
            )

        return ret

    # def set_contacts(self, contacts: ContactList):
    #     sql_batch = [
    #             {
    #                 'sql': 'delete from contacts where pub_k_owner=%s' % self._db.placeholder,
    #                 'args': [contacts.owner_public_key]
    #             }
    #         ]
    #
    #     # if 0 then you're just deleting any contacts that exist
    #     if len(contacts) > 0:
    #         c_contact: Contact
    #         add_data = []
    #         for c_contact in contacts:
    #             add_data.append([
    #                 contacts.owner_public_key,
    #                 c_contact.contact_public_key,
    #                 contacts.updated_at
    #             ])
    #         sql_batch.append(
    #             {
    #                 'sql': """insert into contacts (pub_k_owner, pub_k_contact, updated_at)
    #                                         values (%s)""" % ','.join([self._db.placeholder] * 3),
    #                 'args': add_data
    #             }
    #         )
    #
    #     return self._db.execute_batch(sql_batch)

    def _prepare_contacts_put(self, contacts: ContactList, batch=None):
        if batch is None:
            batch = []

        # delete existing
        batch.append(
            {
                'sql': 'delete from contacts where pub_k_owner=%s and updated_at<%s' % (self._db.placeholder,
                                                                                        self._db.placeholder),
                'args': [contacts.owner_public_key, contacts.updated_at]
            }
        )

        # if 0 then you're just deleting any contacts that exist
        if len(contacts) > 0:
            c_contact: Contact
            add_data = []
            for c_contact in contacts:
                add_data.append([
                    contacts.owner_public_key,
                    c_contact.contact_public_key,
                    contacts.updated_at
                ])
            batch.append(
                {
                    'sql': """insert into contacts (pub_k_owner, pub_k_contact, updated_at) 
                                                    values (%s)
                            on conflict (pub_k_owner, pub_k_contact) do NOTHING                             
                            """ % ','.join([self._db.placeholder] * 3),
                    'args': add_data
                }
            )

        return batch

    def put_contacts(self, contacts: ContactList):
        if hasattr(contacts, '__iter__'):
            batch = []
            for c_c in contacts:
                self._prepare_contacts_put(c_c, batch)
        else:
            batch = self._prepare_contacts_put(contacts)

        return self._db.execute_batch(batch)

    @property
    def newest(self):
        ret = self._db.select_sql('select updated_at from profiles order by updated_at desc limit 1')
        if ret:
            ret = ret[0][0]
        else:
            ret = 0
        return ret


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
                        name text collate nocase,
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
                        updated_at int,
                        UNIQUE(pub_k_owner, pub_k_contact) ON CONFLICT IGNORE
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