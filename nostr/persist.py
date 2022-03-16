"""
    basic persistance layer for our nostr stuff
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from data.data import DataSet
from db.db import Database
from nostr.util import util_funcs


class Store:

    def __init__(self, db_file):
        self._db_file = db_file
        self._db = Database(db_file)

    def get_oldest(self):
        """
            get the oldest event in the db, this can then be used in filter queries as since
            will return none if we don't have any events yet
        """
        ret = 0
        created_by = DataSet.from_sqlite(self._db_file, 'select created_at from events order by created_at desc limit 1')
        if created_by:
            ret = created_by[0]['created_at']
        else:
            logging.debug('Store::get_oldest - no created_at found, db empty?')

        return ret

    def create(self, tables=['events','profiles','contacts','event_relay']):
        """
            creates the tbls we need, at the moment this will error on exist
        """

        if 'events' in tables:
            evt_tmpl = DataSet(heads=[
                'id','event_id', 'pubkey', 'created_at', 'kind', 'tags', 'content', 'sig'
            ],data=[])

            evt_tmpl.create_sqlite_table(self._db_file, 'events', {
                'id': {
                    'type': 'INTEGER PRIMARY KEY '
                },
                'event_id' : {
                    # not a type but all the underlying does is concat str so will do
                    'type' : 'UNIQUE'
                },
                'created_at' : {
                    'type' : 'int'
                },
                'kind' : {
                    'type' : 'int'
                }
            })

            evt_relay_tmpl = DataSet(heads=['id', 'relay_url'])
            evt_relay_tmpl.create_sqlite_table(self._db_file, 'event_relay', {
                'id': {
                    'type': 'int'
                }
            })


        """
            where we store all profiles, at the moment we'll store both our own and others here
            the difference being that we'll only have a prov_k for our own profiles. 
            For others will just have pub_k and attrs. 
            
            TODO: add create_at and version fields?     
        """
        if 'profiles' in tables:
            # name and picture are extracted from tags if they exist
            profile_tmpl = DataSet(heads=['priv_k','pub_k', 'profile_name', 'attrs', 'name','picture','updated_at'])
            profile_tmpl.create_sqlite_table(self._db_file, 'profiles',{
                # because we alway have to have
                'pub_k' : {
                    'type' : 'primary key not null'
                },
                'updated_at' : {
                    'type' : 'int'
                }
            })

        if 'contacts' in tables:
            contact_tmpl = DataSet(heads=['pub_k_owner','pub_k_contact','relay','petname','updated_at'])
            contact_tmpl.create_sqlite_table(self._db_file, 'contacts', {
                # because we alway have to have
                'pub_k_owner': {
                    'type': 'not null'
                },
                'pub_k_contact': {
                    'type': 'not null'
                },
                'updated_at': {
                    'type': 'int'
                }
            })

    def destroy(self, tables=['events','profiles','contacts', 'event_relay']):
        """
            removes tbls as created in create - currently no key constraints so any table can be droped
        """
        if 'events' in tables:
            # eventually event_relay should have a constraint linking to events
            batch = [
                {
                    'sql' : 'drop table event_relay'
                },
                {
                    'sql' : 'drop table events'
                }
            ]
            self._db.execute_batch(batch)

        if 'profiles' in tables:
            self._db.execute_sql('drop table profiles')
        if 'contacts' in tables:
            self._db.execute_sql('drop table contacts')


    def add_event(self, evt, relay_url='?'):
        batch = [
            {
                'sql': 'insert into events(event_id, pubkey, created_at, kind, tags, content,sig) values(?,?,?,?,?,?,?)',
                'args': [
                    evt['id'], evt['pubkey'], evt['created_at'],
                    evt['kind'], str(evt['tags']), evt['content'], evt['sig']
                ]
            },
            # TODO  rem last_insert_rowid() make like we did for relay event_tags
            {
                'sql' : 'insert into event_relay SELECT last_insert_rowid(), ?',
                'args' : [relay_url]
            }
        ]

        try:
            self._db.execute_batch(batch)
        # probably because already inserted, take a look see if we already have for this relay
        except Exception as e:
            data = DataSet.from_sqlite(self._db_file,
                                       sql='SELECT  e.id, er.relay_url from events e'
                                           ' inner join event_relay er on e.id = er.id'
                                           ' where e.event_id = ?',
                                       args=[evt['id']])
            have_relay = data.value_in('relay_url', relay_url)
            # we recieved event we have seen before but from another relay, just insert into event_relay tbl
            if data and not have_relay:
                self._db.execute_sql('insert into event_relay values (?, ?)',
                                     args=[data[0]['id'], relay_url])

    def load_events(self, kind, since=None):
        """
            :param kind: int type of event
            :param since: events from this time point, all if None either int ticks or datetime
            :return: DataSet of matching events ordered most recent first

            # FIXME: json the tags here?
        """
        sql_arr = ['select * from events where kind=?']
        args = [kind]
        if since:
            sql_arr.append(' and created_at>=?')
            if isinstance(since, datetime):
                since = util_funcs.date_as_ticks(since)

            args.append(since)

        # we order first as in many cases only the newset is of interest per profile
        sql_arr.append(' order by created_at desc')
        event_sql = ''.join(sql_arr)

        return DataSet.from_sqlite(self._db_file, event_sql, args)

    def add_profile(self, profile: 'Profile'):
        sql = """
            insert into 
                profiles (priv_k, pub_k, profile_name, attrs, name, picture, updated_at) 
                        values(?,?,?,?,?,?,?)
            """
        args = [
            profile.private_key, profile.public_key,
            profile.profile_name, json.dumps(profile.attrs),
            profile.get_attr('name'), profile.get_attr('picture'),
            util_funcs.date_as_ticks(profile.update_at)
        ]

        self._db.execute_sql(sql, args)

    def update_profile(self,profile: 'Profile'):
        sql = """
                update profiles 
                    set profile_name=?, attrs=?, name=?, picture=?, updated_at=?
                    where pub_k=?
            """
        args = [
            profile.profile_name, json.dumps(profile.attrs),
            profile.get_attr('name'), profile.get_attr('picture'),
            util_funcs.date_as_ticks(profile.update_at),
            profile.public_key
        ]
        logging.debug('Store::update profile sql: %s args: %s' % (sql, args))
        self._db.execute_sql(sql, args)

    def update_contact_list(self, owner_pub_k, contacts):
        """
        when we get a contact list event that replaces any contact list that existed before
        so we'll delete all contacts an then add in the new contacts

        passing [] as contacts will result in all contacts for owner_pub_k being deleted

        FIXME: we need to add a batching method to db...

        :param contact:
        :return:
        """
        del_sql = 'delete from contacts where pub_k_owner=?'
        if self._db.execute_sql(del_sql, [owner_pub_k]):
            if contacts:
                insert_sql = """insert into contacts (pub_k_owner, pub_k_contact, 
                relay, petname, updated_at) values (?,?,?,?,?)"""

                """
                    concert contacts to [[]] for insertion
                """
                insert_data = []
                for c_contact in contacts:
                    insert_data.append([
                        owner_pub_k,
                        c_contact.contact_public_key,
                        c_contact.relay,
                        c_contact.petname,
                        c_contact.updated_at
                    ])
                # finally insert
                self._db.executemany_sql(insert_sql,insert_data)

