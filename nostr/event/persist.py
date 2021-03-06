import logging
import os
from datetime import datetime
from abc import ABC, abstractmethod
import json
from enum import Enum
from db.db import Database, SQLiteDatabase, PostgresDatabase
from sqlite3.dbapi2 import IntegrityError
from nostr.event.event import Event
from nostr.util import util_funcs
from nostr.exception import NostrCommandException
from data.data import DataSet

try:
    from psycopg2 import OperationalError
except:
    pass
from pathlib import Path


class DeleteMode(Enum):
    # action taken on recieveing a delete event

    # delete any events we can from db - note that once deleted there is no check that it's not reposted, which
    # anyone would be able to do... not just the creator.
    DEL_DELETE = 1
    # mark as deleted any events from db - to client this would look exactly same as DEL_DELETE
    DEL_FLAG = 2
    # nothing, ref events will still be returned to clients
    DEL_NO_ACTION = 3


class EventStoreInterface(ABC):

    @abstractmethod
    def add_event(self, evt: Event):
        """
        add given event to store should throw NostrCommandException if can't for some reason
        e.g. duplicate event, already newer contact/meta, or db insert err etc.

        :param evt: nostr.Event
        :return: None, as long as it returns it should have been success else it should throw
        """

    @abstractmethod
    def do_delete(self, evt: Event):
        """
        :param evt: the delete event
        :return: None, as long as it returns it should have been success else it should throw
        """

    @abstractmethod
    def get_filter(self, filter) -> [Event]:
        """
        :param filter: [{filter}...] nostr filter
        :return: all evts in store that passed the filter
        """


class RelayEventStoreInterface(EventStoreInterface):

    @abstractmethod
    def add_event(self, evt: Event):
        """
        add given event to store should throw NostrCommandException if can't for some reason
        e.g. duplicate event, already newer contact/meta, or db insert err etc.

        :param evt: nostr.Event
        :return: None, as long as it returns it should have been success else it should throw
        """

    @abstractmethod
    def do_delete(self, evt: Event):
        """
        :param evt: the delete event
        :return: None, as long as it returns it should have been success else it should throw
        """

    @abstractmethod
    def get_filter(self, filter) -> [Event]:
        """
        :param filter: [{filter}...] nostr filter
        :return: all evts in store that passed the filter
        """

    @abstractmethod
    def is_NIP09(self):
        """
        store with current params implementing NIP09
        :return: True/False
        """


class ClientEventStoreInterface(EventStoreInterface):
    # TODO:
    #  add method that returns the most recent create date for all relays we've seen

    @abstractmethod
    def add_event_relay(self, evt: Event, relay_url: str):
        """
        clients can recieve the same event from multiple souces so the store has an extra tbl that tracks that
        if you just call add_event no info on whre the event came from will be stored

        :param evt: nostr.Event
        :param relay_url:
        :return: None, as long as it returns it should have been success else it should throw
        """

    @abstractmethod
    def get_newest(self, for_relay, filter):
        """
        return ticks of the newest event we have for given relay for use in since filter
        filter is just a single nostr filter {}
        currently we're only the kind filter is used

        :param for_relay:
        :return:
        """

    @abstractmethod
    def get_filter(self, filter) -> [Event]:
        """
        :param filter: [{filter}...] nostr filter
        :return: all evts in store that passed the filter
        """

    @abstractmethod
    def event_relay(self, event_id: str) -> [str]:
        """
        :param event_id: nostr event_id
        :return: [str] relay_urls
        """

    @abstractmethod
    def direct_messages(self, pub_k: str) -> DataSet:
        """
        :param pub_k:
        :return:  DataSet containing event_id, pub_k, created_at of direct messages for this user
        order newest to oldest, one row per pub_k messaging the event_id, created_at is for the newest record we have
        """

    @abstractmethod
    def relay_list(self, pub_k: str = None) -> []:
        """
        :param pub_k: if given relays surgested by contacts for this pub_k will be listed first
        :return: [relay_urls]
        """


class MemoryEventStore(EventStoreInterface):
    """
        Basic event store implemented in mem using {}
        could be improved to purge old evts or at set size/number if evts
        and to pickle events on stop and load for some sort of persistence when re-run

    """

    def __init__(self, delete_mode=DeleteMode.DEL_FLAG):
        self._delete_mode = delete_mode
        self._events = {}

    def add_event(self, evt: Event):
        self._events[evt.id] = {
            'is_deleted': False,
            'evt': evt
        }

    def do_delete(self, evt: Event):
        if self._delete_mode == DeleteMode.DEL_NO_ACTION:
            return
        to_delete = evt.e_tags
        if self._delete_mode == DeleteMode.DEL_FLAG:
            for c_id in to_delete:
                if c_id in self._events:
                    self._events[c_id]['is_deleted'] = True
        elif self._delete_mode == DeleteMode.DEL_DELETE:
            for c_id in to_delete:
                if c_id in self._events:
                    # we just leave the is deleted flag in place but get rid of the evt data
                    # as it's just in memory it wouldn't be easy to get at anyway so really we're just freeing the mem
                    del self._events[c_id]['evt']

    def test_event(self, evt:Event, filter):
        return evt.test(filter)

    def get_filter(self, filters):
        ret = set([])
        c_evt: Event
        limit = None
        # only been passed a single, put into list
        if isinstance(filters, dict):
            filters = [filters]

        # get limit if any
        for c_filter in filters:
            if 'limit' in c_filter:
                if limit is None or c_filter['limit'] > limit:
                    limit = c_filter['limit']

        # bit shit as we store unsorted we have to get all then sort and can only cut
        # to limit then
        for evt_id in self._events:
            r = self._events[evt_id]
            if not r['is_deleted']:
                c_evt = r['evt']
                for c_filter in filters:
                    if self.test_event(c_evt, c_filter):
                        ret.add(c_evt)

        def _updated_sort(evt: Event):
            return evt.created_at

        ret = list(ret)
        ret.sort(key=_updated_sort, reverse=True)
        if limit is not None:
            ret = ret[:limit]

        return ret


class RelayMemoryEventStore(MemoryEventStore, RelayEventStoreInterface):

    def add_event(self, evt: Event):
        if evt.id in self._events:
            raise NostrCommandException.event_already_exists(evt.id)
        super().add_event(evt)

    def is_NIP09(self):
        return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)


class ClientMemoryEventStore(MemoryEventStore, ClientEventStoreInterface):

    def __init__(self):
        super().__init__(DeleteMode.DEL_DELETE)

    def add_event(self, evt: Event):
        if hasattr(evt, '__iter__'):
            for c_evt in evt:
                super().add_event(c_evt)
        else:
            super().add_event(evt)

    def add_event_relay(self, evt: Event, relay_url: str):
        def do_add(evt: Event):
            if evt.id not in self._events:
                self.add_event(evt)
            e_store = self._events[evt.id]
            if not 'relays' in e_store:
                e_store['relays'] = set()

            self._events[evt.id]['relays'].add(relay_url)

        if hasattr(evt, '__iter__'):
            for c_evt in evt:
                do_add(c_evt)
        else:
            do_add(evt)

    def test_event(self, evt, filter):
        # adds basic text filter to client mem store
        ret = False
        if evt.test(filter):
            if 'content' in filter:
                ret = filter['content'].lower() in evt.content.lower()
            else:
                ret = True
        return ret

    def get_newest(self, for_relay, filter=None):
        if filter is None:
            filter = {}

        ret = 0
        evt: Event
        for i, k in enumerate(self._events):
            e_store = self._events[k]
            if for_relay in e_store['relays']:
                evt = e_store['evt']
                if evt.created_at_ticks > ret:
                    ret = evt.created_at_ticks

        return ret

    # TODO
    def event_relay(self, event_id: str) -> [str]:
        ret = []
        evt = self._events[event_id]
        if evt:
            # to match sql, should just be [str] as we say!!!
            ret = [{'relay_url': c_r} for c_r in list(evt['relays'])]

        return ret

    def direct_messages(self, pub_k: str) -> DataSet:
        all_dms = self.get_filter([
            {
                'authors': pub_k,
                'kinds': [Event.KIND_ENCRYPT]
            },
            {
                '#p': pub_k,
                'kinds': [Event.KIND_ENCRYPT]
            }
        ])

        got_pks = set()
        data = []
        c_evt: Event
        for c_evt in all_dms:
            if c_evt.pub_key not in got_pks:
                got_pks.add(c_evt.pub_key)
                data.append([
                    c_evt.id,
                    c_evt.pub_key,
                    c_evt.created_at
                ])

        ret = DataSet(heads=['event_id', 'pub_k', 'created_at'], data=data)
        return ret

    def relay_list(self, pub_k: str = None) -> []:
        pass


class SQLEventStore(EventStoreInterface):

    @staticmethod
    def _make_filter_sql(filters, placeholder='?', custom=None):
        """
        creates the sql to select events from a db given nostr filter
        :param filter:
        :return:
        """

        def for_single_filter(filter):
            def do_tags(tag_type):
                nonlocal args
                t_filter = filter['#' + tag_type]
                if isinstance(t_filter, str):
                    t_filter = [t_filter]
                e_sql = """
                %s id in 
                    (
                        select id from event_tags where type = '%s' and value in(%s)
                    )
                                """ % (join,
                                       tag_type,
                                       ','.join([placeholder] * len(t_filter)))
                sql_arr.append(e_sql)
                args = args + t_filter

            # deleted isnull to filter deleted if in flag delete mode
            sql_arr = ['select * from events where deleted isnull']
            # join not really required anymore because its always and
            join = 'and'
            args = []
            if 'since' in filter:
                sql_arr.append(' %s created_at>=%s' % (join, placeholder))
                args.append(filter['since'])
            if 'until' in filter:
                sql_arr.append(' %s created_at<=%s' % (join, placeholder))
                args.append(filter['until'])
            if 'kinds' in filter:
                kind_arr = filter['kinds']
                if not hasattr(kind_arr, '__iter__') or isinstance(kind_arr, str):
                    kind_arr = [kind_arr]
                arg_str = ','.join([placeholder] * len(kind_arr))
                sql_arr.append(' %s kind in(%s)' % (join, arg_str))
                args = args + kind_arr
            if 'authors' in filter:
                auth_arr = filter['authors']
                if not hasattr(auth_arr, '__iter__') or isinstance(auth_arr, str):
                    auth_arr = [auth_arr]

                arg_str = 'or '.join(['pubkey like ' + placeholder] * len(auth_arr))
                sql_arr.append(' %s (%s)' % (join, arg_str))
                for c_arg in auth_arr:
                    args.append(c_arg + '%')

            if 'ids' in filter:
                ids_arr = filter['ids']
                if not hasattr(ids_arr, '__iter__') or isinstance(ids_arr, str):
                    ids_arr = [ids_arr]

                arg_str = ' or '.join(['event_id like ' + placeholder] * len(ids_arr))
                sql_arr.append(' %s (%s)' % (join, arg_str))
                for c_arg in ids_arr:
                    args.append(c_arg + '%')

            # generic tags start with #, also included here are p and e tags as they're done in same way
            for c_name in filter:
                # its an event tag
                if c_name[0] == '#':
                    do_tags(c_name[1:])
                    join = 'and'

            if custom is not None:
                # where custom queries are of the form select id from
                # only for non standard query additions, currently content by the client
                # if something standard ever replaces should be moved into the make construction here
                # assuming it can be done in a non db specifc way...
                custom_queries = custom(filter, join)
                for c_cust_q in custom_queries:
                    print(c_cust_q)
                    sql_arr.append(c_cust_q['sql'])
                    args.append(c_cust_q['args'])

            return {
                'sql': ''.join(sql_arr),
                'args': args
            }

        # only been passed a single, put into list
        if isinstance(filters, dict):
            filters = [filters]

        sql = ''
        args = []
        # added support for filter limit and result now sorted by given create_at date
        # only the largest limit is taken where there is a limit on more than one filter
        limit = None
        for c_filter in filters:
            q = for_single_filter(c_filter)
            if sql:
                sql += ' union '
            sql = sql + q['sql']
            args = args + q['args']
            if 'limit' in c_filter:
                if limit is None or c_filter['limit'] > limit:
                    limit = c_filter['limit']

        sql += ' order by created_at desc'
        if limit is not None:
            sql += ' limit %s' % limit

        return {
            'sql': sql,
            'args': args
        }

    @staticmethod
    def _events_data_to_event_arr(data) -> [Event]:
        """
        :param data: from db query should have event fields head at min
        :return: [Events]
        """
        ret = []
        for c_r in data:
            ret.append(Event(
                id=c_r['event_id'],
                pub_key=c_r['pubkey'],
                kind=c_r['kind'],
                content=c_r['content'],
                tags=c_r['tags'],
                created_at=util_funcs.ticks_as_date(c_r['created_at']),
                sig=c_r['sig']
            ))
        return ret

    def __init__(self, db: Database, delete_mode=DeleteMode.DEL_FLAG):
        self._delete_mode = delete_mode
        self._db = db

    def _prepare_most_recent_types(self, evt:Event, batch:[]):
        # META and CONTACT_LIST event type supercede any previous events of same type, so if this event is newer
        # then we'll delete all pre-existing
        if evt.kind in (Event.KIND_META, Event.KIND_CONTACT_LIST):
            # if self._db.select_sql(sql='select id from events '
            #                            'where created_at>=%s and kind=%s '
            #                            'and pubkey=%s'.replace('%s', self._db.placeholder),
            #                        args=[evt.created_at_ticks, evt.kind, evt.pub_key]):
            #     raise NostrCommandException('Newer event for kind %s already exists' % evt.kind)
            #
            # else:
            # delete existing, note these are done as actual deletes not perhaps
            # they should also honor the delete mode, so if flagging just mark as deleted?
            batch.append(
                {
                    'sql': 'delete from event_tags where id in '
                           '(select id from events where kind=%s and pubkey=%s)' %
                           (self._db.placeholder, self._db.placeholder),
                    'args': [evt.kind, evt.pub_key]
                }
            )
            batch.append(
                {
                    'sql': 'delete from events where id in '
                           '(select id from events '
                           'where kind=%s and pubkey=%s)'.replace('%s', self._db.placeholder),
                    'args': [evt.kind, evt.pub_key]
                }
            )

    def _prepare_add_event_batch(self, evt: Event, batch=None):
        if batch is None:
            batch = []
        is_add = False
        if not self._db.select_sql(sql='select id from events where event_id=%s' % self._db.placeholder,
                                   args=[evt.id]):
            is_add = True
            self._prepare_most_recent_types(evt, batch)

            batch.append({
                'sql': 'insert into events(event_id, pubkey, created_at, kind, tags, content,sig) '
                       'values(%s,%s,%s,%s,%s,%s,%s)'.replace('%s', self._db.placeholder),
                'args': [
                    evt.id, evt.pub_key, evt.created_at_ticks,
                    evt.kind, json.dumps(evt.tags), evt.content, evt.sig
                ]
            })

            # currently we only put in the tags table the bits needed to suport query [2:] could go in an extra field
            # but as we already have the full info in events tbl probably don't need
            for c_tag in evt.tags:
                if len(c_tag) >= 2:
                    tag_type = c_tag[0]
                    tag_value = c_tag[1]
                    batch.append({
                        # 'sql': 'insert into event_tags SELECT last_insert_rowid(),?,?',
                        'sql': """
                                                    insert into event_tags values (
                                                    (select id from events where event_id=%s),
                                                    %s,
                                                    %s)
                                                """.replace('%s', self._db.placeholder),
                        'args': [evt.id, tag_type, tag_value]
                })
        return batch, is_add

    def add_event(self, evt: Event):
        if hasattr(evt, '__iter__'):
            batch = []
            for c_evt in evt:
                self._prepare_add_event_batch(c_evt, batch)

            is_add = self._db.execute_batch(batch)

        else:
            batch, is_add = self._prepare_add_event_batch(evt)
            if is_add:
                is_add = self._db.execute_batch(batch)

        return is_add

    def get_filter(self, filter, custom=None) -> [Event]:
        """
        from database returns events that match filter/s
        doesn't do #e and #p filters yet (maybe never)
        also author and ids are currently exact only, doesn't support prefix
        :param filter: {} or [{},...] or filters
        :return:
        """
        filter_query = SQLEventStore._make_filter_sql(filter,
                                                      placeholder=self._db.placeholder,
                                                      custom=custom)

        # print(filter_query['sql'], filter_query['args'])

        data = self._db.select_sql(sql=filter_query['sql'],
                                   args=filter_query['args'])

        return self._events_data_to_event_arr(data)

    def _prepare_delete_batch(self, evt: Event):
        batch = []
        if self._delete_mode == DeleteMode.DEL_NO_ACTION:
            return batch
        to_delete = evt.e_tags

        # only flag as deleted
        if self._delete_mode == DeleteMode.DEL_FLAG:
            batch.append({
                'sql': 'update events set deleted=true where event_id in (%s) and kind<>?' %
                       ','.join(['?'] * len(to_delete)),
                'args': to_delete + [Event.KIND_DELETE]

            })
        # actually delete
        elif self._delete_mode == DeleteMode.DEL_DELETE:
            batch = [
                {
                    'sql': 'delete from event_tags where id in (select id from events '
                           'where event_id in (%s) and kind<>?)' % ','.join(
                        ['?'] * len(to_delete)),
                    'args': to_delete + [Event.KIND_DELETE]
                },
                {
                    'sql': 'delete from events where event_id in (%s) and kind<>?' % ','.join(['?'] * len(to_delete)),
                    'args': to_delete + [Event.KIND_DELETE]
                }
            ]

        return batch

    def do_delete(self, evt: Event):
        ret = None
        batch = self._prepare_delete_batch(evt)
        if batch:
            ret = self._db.execute_batch(batch)
        return ret


class SQLiteEventStore(SQLEventStore):
    """
        SQLite implementation of RelayStoreInterface

    """
    CREATE_SQL_BATCH = [
        {
            'sql':
                """
                create table events( 
                    id INTEGER PRIMARY KEY,  
                    event_id UNIQUE,  
                    pubkey text,  
                    created_at int,  
                    kind int,  
                    tags text,  
                    content text,  
                    sig text,  
                    deleted int)
                """
        },
        {
            'sql':
                """
                create table event_tags(
                    id int,  
                    type text,  
                    value text)
                """
        }
    ]

    def __init__(self, db_file, delete_mode=DeleteMode.DEL_FLAG, full_text=False):
        super().__init__(SQLiteDatabase(db_file),
                         delete_mode=delete_mode)
        logging.debug('SQLiteStore::__init__ db_file=%s, delete mode=%s' % (db_file,
                                                                            self._delete_mode))

    def create(self):
        return self._db.execute_batch(SQLiteEventStore.CREATE_SQL_BATCH)

    def exists(self):
        return Path(self._db.file).is_file()

    def destroy(self):
        os.remove(self._db.file)


class PostgresEventStore(SQLEventStore):
    """
    Postgres implementation of RelayStoreInterface
    """

    def __init__(self, db_name, user, password, delete_mode=DeleteMode.DEL_FLAG):
        super().__init__(PostgresDatabase(db_name=db_name,
                                          user=user,
                                          password=password),
                         delete_mode=delete_mode)
        self._db_name = db_name
        self._user = user
        self._password = password
        logging.debug('PostgresStore::__init__ db=%s, user=%s, delete mode=%s' % (db_name,
                                                                                  user,
                                                                                  self._delete_mode))

    def exists(self):
        ret = True
        try:
            self._db.select_sql('select 1')
        except OperationalError as oe:
            if 'does not exist' in str(oe):
                ret = False
        return ret

    def create(self):
        """
        needs to be done above the level the store is created at, assumed that the same user has permissions to create
        we can;'t just us postgres_db.execute_sql because it creates a tx and CREATE DATABASE won't work inside a tx
        """
        postgres_db = PostgresDatabase(db_name='postgres',
                                       user=self._user,
                                       password=self._password)
        c = postgres_db._get_con()
        c.autocommit = True
        cur = c.cursor()
        cur.execute(
            """
                CREATE DATABASE "%s"
                    WITH 
                    OWNER = postgres
                    ENCODING = 'UTF8'
                    LC_COLLATE = 'en_GB.UTF-8'
                    LC_CTYPE = 'en_GB.UTF-8'
                    TABLESPACE = pg_default
                    CONNECTION LIMIT = -1;
            """ % self._db_name
        )

        self._db.execute_batch([
            {
                'sql': """
                    create table events( 
                        id SERIAL PRIMARY KEY,  
                        event_id text UNIQUE,  
                        pubkey varchar(128),  
                        created_at int,  
                        kind int,  
                        tags text,  
                        content text,  
                        sig varchar(128),  
                        deleted int)
                """
            },
            {
                'sql': """
                    create table event_tags(
                        id int,  
                        type varchar(32),  
                        value text)
                """
            }
        ])

    def destroy(self):
        # as create
        postgres_db = PostgresDatabase(db_name='postgres',
                                       user=self._user,
                                       password=self._password)
        c = postgres_db._get_con()
        c.autocommit = True
        cur = c.cursor()
        cur.execute(
            """
            SELECT  
            pg_terminate_backend (pg_stat_activity.pid)
            FROM
                pg_stat_activity
            WHERE
            pg_stat_activity.datname = '%s';
            """ % self._db_name
        )
        cur.execute('DROP DATABASE IF EXISTS "%s"' % self._db_name)


class RelaySQLEventStore(SQLEventStore, RelayEventStoreInterface):

    def is_NIP09(self):
        return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)


class RelaySQLiteEventStore(SQLiteEventStore, RelayEventStoreInterface):

    def is_NIP09(self):
        return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)


class RelayPostgresEventStore(PostgresEventStore, RelayEventStoreInterface):

    def is_NIP09(self):
        return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)


class ClientSQLEventStore(SQLEventStore, ClientEventStoreInterface):


    def get_newest(self, for_relay, filter=None):
        """
        returns the newest event we've seen so we can use that as a since in any queries we created and not ask for everthing
        as event creators set the create_at time will probably need to re-visit this.
        have added created_at as a filter now so just one event miles in the future won't stop of fetching gaps
        probably the relay should have a max time in the future that'll it allow events to be set before rejecting,
        also our EventPersister sshould probably reject events too far in the future...

        :param for_relay:
        :param filter:
        :return:
        """

        if filter is None:
            filter = {}

        sql_arr = [
            'select created_at from events e'
            ' inner join event_relay er on e.id = er.id'
            ' where er.relay_url = %s and e.created_at<=%s' % (self._db.placeholder,
                                                               self._db.placeholder)
        ]
        args = [for_relay, util_funcs.date_as_ticks(datetime.now())]

        if 'kinds' in filter:
            kinds = filter['kinds']
            if not hasattr(kinds, '__iter__') or isinstance(kinds, str):
                kinds = [kinds]
            sql_arr.append(' and e.kind in (%s)' % ','.join([self._db.placeholder]*len(kinds)))
            args = args + kinds

        sql_arr.append(' order by created_at desc limit 1')
        my_sql = ''.join(sql_arr)
        ret = 0
        my_recent_evt = self._db.select_sql(my_sql, args)
        if my_recent_evt:
            ret = my_recent_evt[0]['created_at']
        else:
            logging.debug('Store::get_newest - no created_at found, db empty?')
        return ret

    def add_event_relay(self, evt: Event, relay_url: str):
        if hasattr(evt, '__iter__'):
            batch = []
            for c_evt in evt:
                self._prepare_add_event_batch(c_evt, batch)
                batch.append({
                    'sql': 'insert into event_relay values ((select id from events where event_id=?), ?)',
                    'args': [c_evt.id, relay_url]
                })

        else:
            batch, is_add = super()._prepare_add_event_batch(evt)
            batch.append({
                'sql': 'insert into event_relay values ((select id from events where event_id=?), ?)',
                'args': [evt.id, relay_url]
            })

        return self._db.execute_batch(batch)

    def event_relay(self, event_id: str) -> [str]:
        sql = """
        select relay_url from event_relay er
            inner join events e on e.id = er.id 
            where e.event_id=%s
            order by relay_url
        """ % self._db.placeholder

        return self._db.select_sql(sql=sql,
                                   args=[event_id]).as_arr()

    def direct_messages(self, pub_k: str) -> DataSet:
        sql = """
select event_id,pub_k,max(created_at) as created_at from(
    select e.event_id, e_t.value as pub_k,e.created_at as created_at from events e 
    inner join event_tags e_t on e_t.id = e.id
    where 
        e.pubkey=%s and e.kind=4
        and e_t.type='p' and e_t.value!=%s
    union
    select e.event_id, e.pubkey as pub_k,e.created_at as created_at from events e 
    inner join event_tags e_t on e_t.id = e.id
    where 
        e.kind=4 and e_t.type='p' and e_t.value=%s and e.pubkey!=%s
)
GROUP by pub_k
order by created_at desc
        
        """ % (self._db.placeholder,
               self._db.placeholder,
               self._db.placeholder,
               self._db.placeholder)

        return self._db.select_sql(sql,
                                   args=[pub_k]*4)

    def relay_list(self, pub_k: str = None) -> []:
        # https://stackoverflow.com/questions/18807276/how-to-make-my-postgresql-database-use-a-case-insensitive-collation
        # this might work in postgres if we create the collation
        # just used lower!

        # all order by how many unique pub_k recommended
        all_sql = """
select lower(trim(trim(trim(content),X'09'),'/')) as relay
from events where kind=2 
group by relay
order by count(pubkey) desc, relay  
        """

        # same but using recomendations of followers of pub_k
        relative_pub_k_sql = """
select lower(trim(trim(trim(content),X'09'),'/')) as relay
from events where kind=2 and 
pubkey in (
	select pub_k_contact from contacts where pub_k_owner=%s
)
group by relay
order by count(pubkey) desc, relay
        """ % self._db.placeholder

        ret = []
        for_pub_k = None

        if pub_k:
            data = self._db.select_sql(sql=relative_pub_k_sql,
                                        args=[pub_k])
            for_pub_k = [row['relay'] for row in data]

        data = self._db.select_sql(sql=all_sql)
        for_all = [row['relay'] for row in data]

        if for_pub_k:
            ret = for_pub_k
            test_set = set(for_pub_k)
            for url in for_all:
                if url not in test_set:
                    ret.append(url)
        else:
            ret = for_all

        return ret

class ClientSQLiteEventStore(SQLiteEventStore, ClientSQLEventStore,  ClientEventStoreInterface):

    """
        experimental for full text search only doing in sqllite at the monent and only for the client
        as its not required for the relay to support anything other than nostr filtered based queries
        it won't be standard anyway so postgres (and in mem) will need to be done in own style
        where we don't fulltext is false we'll just provide something via like query
    """
    FTS_CONTENT_TABLE_CREATE_SQL = {
        'sql': """
            CREATE VIRTUAL TABLE event_content
            USING FTS5(id,content);
        """
    }

    # client stores info about which relays we saw events from
    RELAY_TABLE_SQL = {
        'sql': """
            create table event_relay(
                id int,  
                relay_url text,
                UNIQUE(id, relay_url) ON CONFLICT IGNORE
                )
        """
    }

    def __init__(self, db_file, full_text=True):
        self._db_file = db_file
        self._full_text = full_text

        logging.debug('Experimental client sqllite fulltext search: %s' % self._full_text)
        super().__init__(db_file)

    def create(self):
        create_batch = ClientSQLiteEventStore.CREATE_SQL_BATCH + [ClientSQLiteEventStore.RELAY_TABLE_SQL]
        if self._full_text:
            create_batch.append(ClientSQLiteEventStore.FTS_CONTENT_TABLE_CREATE_SQL)

        self._db.execute_batch(create_batch)

    def _prepare_add_event_batch(self, evt: Event, batch=None):
        if batch is None:
            batch = []

        evt_batch, is_add = super()._prepare_add_event_batch(evt, batch)
        if is_add and self._full_text and evt.kind == Event.KIND_TEXT_NOTE:
            evt_batch.append({
                'sql': """
                                                    insert into event_content values (
                                                    (select id from events where event_id=%s),
                                                    %s)
                                                """.replace('%s', self._db.placeholder),
                'args': [evt.id, evt.content]
            })

        return evt_batch, is_add

    # def add_event(self, evt: Event):
    #     evt_batch, is_add = self._prepare_add_event_batch(evt)
    #     if is_add:
    #         self._db.execute_batch(evt_batch)

    def get_filter(self, filter) -> [Event]:
        def my_custom(filter, join):
            ret = []
            if 'content' in filter:
                if self._full_text:
                    sql = """
                        %s id in (
                            select id from event_content ec
                            where ec.content match %s  
                        )
                    """ % (join, self._db.placeholder)

                    ret.append(
                        {
                            'sql': sql,
                            'args': filter['content']
                        }
                    )
                else:
                    # standard like style this should work in postgres (postgres probably has its own full text search)
                    sql = """
                            %s id in (
                                select id from events where content like %s  
                            )
                        """ % (join, self._db.placeholder)

                    ret.append(
                        {
                            'sql': sql,
                            'args': '%' + filter['content'] + '%'
                        }
                    )


            return ret

        return super().get_filter(filter, my_custom)
