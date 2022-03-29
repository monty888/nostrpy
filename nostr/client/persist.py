"""
    The client store just keeps a local copy of nostr events that we have seen before and is almost the relay store.
    it adds relay_url so that we can see which relay
    and the delete just deletes events from event tbl - actually no delete at mo....

    The same db we'll use elsewhere for keeping data about profiles, contacts and any extra data specific to a
    client implementation. In many cases this data is just derived from the events table for example profiles tbl
    is created from meta event types, so you can delete all profiles and the reacreate from events tbl
    or you could event not persist the events but subscribe to a relay and create just the profiles data from
    what you get back from the relay/

"""

from abc import ABC, abstractmethod
import logging
from datetime import datetime
import json
from pathlib import Path
import os
from data.data import DataSet
from db.db import SQLiteDatabase, Database
from nostr.util import util_funcs
from nostr.event import Event
from nostr.relay.persist import SQLStore as RelayStore


class ClientStoreInterface(ABC):

    @abstractmethod
    def add_event(self, evt: Event, relay_url: str):
        """
        add given event to store should throw NostrCommandException if can't for some reason
        e.g. duplicate event, already newer contact/meta, or db insert err etc.

        :param evt: nostr.Event
        :param relay_url:
        :return: None, as long as it returns it should have been success else it should throw
        """

    # @abstractmethod
    # def do_delete(self, evt: Event):
    #     """
    #     :param evt: the delete event
    #     :return: None, as long as it returns it should have been success else it should throw
    #     """

    @abstractmethod
    def get_filter(self, filter):
        """
        :param filter: [{filter}...] nostr filter
        :return: all evts in store that passed the filter
        """


class SQLStore(ClientStoreInterface, ABC):
    """
    sql version of ClientStoreInterface, we won't bother with mem only version for the client
    as with the relay we'll do 2 versions just to add the correct create and destroy sql
    hopefully we can keep the rest of our SQL standard enough that the underlying db doesn't matter
    """

    # tbl structure should be same so copy this method from relays version of sqlstore
    @classmethod
    def make_filter_sql(cls, filters, placeholder='?'):
        return RelayStore.make_filter_sql(filter, placeholder)

    def __init__(self, db: Database):
        self._db = db
        # copy this method from relay
        self._do_filter = RelayStore.get_filter

    def get_oldest(self):
        """
            gets the oldest event in the database, this can then be used when subscribing as the since var
            so we don't have to fetch everything. Maybe just use as guide and lookback a little further as may not have
            seen some events on some relays e.g if lost connection so could be some gaps.
            Change this so that it can be oldest of events matching filter
            A Client might want to give the user option to scan back anyway to check for any gaps
        """
        ret = 0
        created_by = self._db.select_sql('select created_at from events order by created_at desc limit 1')
        if created_by:
            ret = created_by[0]['created_at']
        else:
            logging.debug('Store::get_oldest - no created_at found, db empty?')

        return ret

    def add_event(self, evt: Event, relay_url='?'):

        batch = [
            {
                'sql': 'insert into events(event_id, pubkey, created_at, kind, tags, content,sig) values(?,?,?,?,?,?,?)',
                'args': [
                    evt.id, evt.pub_key, evt.created_at_ticks,
                    evt.kind, json.dumps(evt.tags), evt.content, evt.sig
                ]
            },
            # TODO  rem last_insert_rowid() make like we did for relay event_tags
            {
                'sql': 'insert into event_relay values((select id from events where event_id=%s), %s)'.replace('%s',self._db.placeholder),
                'args': [evt.id, relay_url]
            }
        ]

        # tags = json.loads(evt['tags'].replace('\'', '\"'))
        tags = evt.tags
        if tags and not isinstance(tags[0], list):
            tags = [tags]
        for c_tag in tags:

            if len(c_tag) >= 2:
                tag_type = c_tag[0]
                tag_value = c_tag[1]
                batch.append({
                    # 'sql': 'insert into event_tags SELECT last_insert_rowid(),?,?',
                    'sql' : """
                        insert into event_tags values (
                        (select id from events where event_id=%s),
                        %s,
                        %s)
                    """.replace('%s', self._db.placeholder),
                    'args': [evt.id, tag_type, tag_value]
                })

        try:
            self._db.execute_batch(batch)
        # probably because already inserted, take a look see if we already have for this relay
        except Exception as e:
            data = DataSet.from_db(self._db,
                                   sql='SELECT  e.id, er.relay_url from events e'
                                       ' inner join event_relay er on e.id = er.id'
                                       ' where e.event_id = ?',
                                   args=[evt.id])
            have_relay = data.value_in('relay_url', relay_url)
            # we recieved event we have seen before but from another relay, just insert into event_relay tbl
            if data and not have_relay:
                self._db.execute_sql('insert into event_relay values (?, ?)',
                                     args=[data[0]['id'], relay_url])

    def get_filter(self, filter):
        return self._do_filter(filter)

    # TODO - to go
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

    # TODO: also to go, move to contacts
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


class SQLLiteStore(SQLStore):

    def __init__(self, db_file):
        self._db_file = db_file
        super().__init__(SQLiteDatabase(db_file))
        logging.debug('SQLiteStore::__init__ db_file=%s' % db_file)

    def create(self):
        self._db.execute_batch([
            {
                'sql': """
                                    create table events( 
                                        id INTEGER PRIMARY KEY,  
                                        event_id UNIQUE,  
                                        pubkey text,  
                                        created_at int,  
                                        kind int,  
                                        tags text,  
                                        content text,  
                                        sig text)
                                """
            },
            {
                'sql': """
                                    create table event_tags(
                                    id int,  
                                    type text,  
                                    value text)
                                """
            },
            {
                'sql': """
                                    create table event_relay(
                                        id int,  
                                        relay_url text)
                                """
            }
        ])

    def exists(self):
        return Path(self._db.file).is_file()

    def destroy(self):
        os.remove(self._db_file)

