# import logging
# import os
# from abc import ABC, abstractmethod
# import json
# from enum import Enum
# from db.db import Database, SQLiteDatabase, PostgresDatabase
# from nostr.event.event import Event
# from nostr.util import util_funcs
# from nostr.exception import NostrCommandException
# try:
#     from psycopg2 import OperationalError
# except:
#     pass
# from pathlib import Path
#
#
# class RelayStoreInterface(ABC):
#
#     @abstractmethod
#     def add_event(self, evt: Event):
#         """
#         add given event to store should throw NostrCommandException if can't for some reason
#         e.g. duplicate event, already newer contact/meta, or db insert err etc.
#
#         :param evt: nostr.Event
#         :return: None, as long as it returns it should have been success else it should throw
#         """
#
#     @abstractmethod
#     def do_delete(self, evt: Event):
#         """
#         :param evt: the delete event
#         :return: None, as long as it returns it should have been success else it should throw
#         """
#
#     @abstractmethod
#     def get_filter(self, filter):
#         """
#         :param filter: [{filter}...] nostr filter
#         :return: all evts in store that passed the filter
#         """
#
#     @abstractmethod
#     def is_NIP09(self):
#         """
#         store with current params implementing NIP09
#         :return: True/False
#         """
#
# class DeleteMode(Enum):
#     # what will the relay do on receiving delete event
#
#     # delete any events we can from db - note that once deleted there is no check that it's not reposted, which
#     # anyone would be able to do... not just the creator.
#     # TODO: write accept handler that will block reinserts of previously deleted events
#     DEL_DELETE = 1
#     # mark as deleted any events from db - to client this would look exactly same as DEL_DELETE
#     DEL_FLAG = 2
#     # nothing, ref events will still be returned to clients
#     DEL_NO_ACTION = 3
#
#
# class MemoryStore(RelayStoreInterface):
#     """
#         Basic event store implemented in mem using {}
#         could be improved to purge old evts or at set size/number if evts
#         and to pickle events on stop and load for some sort of persistence when re-run
#
#     """
#     def __init__(self, delete_mode=DeleteMode.DEL_FLAG):
#         self._delete_mode = delete_mode
#         self._evts = {}
#
#     def add_event(self, evt: Event):
#         if evt.id in self._evts:
#             raise NostrCommandException.event_already_exists(evt.id)
#         self._evts[evt.id] = {
#             'is_deleted': False,
#             'evt': evt
#         }
#
#     def do_delete(self, evt: Event):
#         if self._delete_mode == DeleteMode.DEL_NO_ACTION:
#             return
#         to_delete = evt.e_tags
#         if self._delete_mode == DeleteMode.DEL_FLAG:
#             for c_id in to_delete:
#                 if c_id in self._evts:
#                     self._evts[c_id]['is_deleted'] = True
#         elif self._delete_mode == DeleteMode.DEL_DELETE:
#             for c_id in to_delete:
#                 if c_id in self._evts:
#                     # we just leave the is deleted flag in place but get rid of the evt data
#                     # as it's just in memory it wouldn't be easy to get at anyway so really we're just freeing the mem
#                     del self._evts[c_id]['evt']
#
#     def get_filter(self, filter):
#         ret = []
#         c_evt: Event
#         for evt_id in self._evts:
#             r = self._evts[evt_id]
#             if not r['is_deleted']:
#                 c_evt = r['evt']
#                 if c_evt.test(filter):
#                     ret.append(c_evt)
#         return ret
#
#     def is_NIP09(self):
#         return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)
#
#
# class SQLStore(RelayStoreInterface):
#
#     @classmethod
#     def make_filter_sql(cls, filters, placeholder='?'):
#         """
#         creates the sql to select events from a db given nostr filter
#         :param filter:
#         :return:
#         """
#         def for_single_filter(filter):
#             def do_tags(tag_type):
#                 nonlocal args
#                 t_filter = filter['#'+tag_type]
#                 if isinstance(t_filter, str):
#                     t_filter = [t_filter]
#                 e_sql = """
#                 %s id in
#                     (
#                         select id from event_tags where type = '%s' and value in(%s)
#                     )
#                                 """ % (join,
#                                        tag_type,
#                                        ','.join([placeholder] * len(t_filter)))
#                 sql_arr.append(e_sql)
#                 args = args + t_filter
#
#             # deleted isnull to filter deleted if in flag delete mode
#             sql_arr = ['select * from events where deleted isnull']
#             # join not really required anymore because its always and
#             join = 'and'
#             args = []
#             if 'since' in filter:
#                 sql_arr.append(' %s created_at>=%s' % (join, placeholder))
#                 args.append(filter['since'])
#             if 'until' in filter:
#                 sql_arr.append(' %s created_at<=%s' % (join, placeholder))
#                 args.append(filter['until'])
#             if 'kinds' in filter:
#                 kind_arr = filter['kinds']
#                 if not hasattr(kind_arr,'__iter__')or isinstance(kind_arr,str):
#                     kind_arr = [kind_arr]
#                 arg_str = ','.join([placeholder]*len(kind_arr))
#                 sql_arr.append(' %s kind in(%s)' % (join, arg_str))
#                 args = args + kind_arr
#             if 'authors' in filter:
#                 auth_arr = filter['authors']
#                 if not hasattr(auth_arr,'__iter__') or isinstance(auth_arr,str):
#                     auth_arr = [auth_arr]
#
#                 arg_str = 'or '.join(['pubkey like ' + placeholder] * len(auth_arr))
#                 sql_arr.append(' %s (%s)' % (join, arg_str))
#                 for c_arg in auth_arr:
#                     args.append(c_arg + '%')
#
#             if 'ids' in filter:
#                 ids_arr = filter['ids']
#                 if not hasattr(ids_arr,'__iter__') or isinstance(ids_arr,str):
#                     ids_arr = [ids_arr]
#
#                 arg_str = ' or '.join(['event_id like ' + placeholder]*len(ids_arr))
#                 sql_arr.append(' %s (%s)' % (join, arg_str))
#                 for c_arg in ids_arr:
#                     args.append(c_arg+'%')
#
#             # generic tags start with #, also included here are p and e tags as they're done in same way
#             for c_name in filter:
#                 # its an event tag
#                 if c_name[0] == '#':
#                     do_tags(c_name[1:])
#                     join = 'and'
#
#             return {
#                 'sql': ''.join(sql_arr),
#                 'args': args
#             }
#
#         # only been passed a single, put into list
#         if isinstance(filters, dict):
#             filters = [filters]
#
#         sql = ''
#         args = []
#         # added support for filter limit and result now sorted by given create_at date
#         # only the largest limit is taken where there is a limit on more than one filter
#         limit = None
#         for c_filter in filters:
#             q = for_single_filter(c_filter)
#             if sql:
#                 sql += ' union '
#             sql = sql + q['sql']
#             args = args + q['args']
#             if 'limit' in c_filter:
#                 if limit is None or c_filter['limit'] > limit:
#                     limit = c_filter['limit']
#
#         sql += ' order by created_at desc'
#         if limit is not None:
#             sql += ' limit %s' % limit
#
#         return {
#             'sql': sql,
#             'args': args
#         }
#
#     def __init__(self, db: Database, delete_mode=DeleteMode.DEL_FLAG):
#         self._delete_mode = delete_mode
#         self._db = db
#
#     def add_event(self, evt: Event):
#         """
#         store event to db, maybe allow [] of events that will be done in batch?
#         :param evt: Event obj
#         :return: True/False, you'll only get False when catch_err is True
#         """
#         batch = []
#         # META and CONTACT_LIST event type supercede any previous events of same type, so if this event is newer
#         # then we'll delete all pre-existing
#         if evt.kind in (Event.KIND_META, Event.KIND_CONTACT_LIST):
#             if self._db.select_sql(sql='select id from events '
#                                        'where created_at>=%s and kind=%s '
#                                        'and pubkey=%s'.replace('%s', self._db.placeholder),
#                                    args=[evt.created_at_ticks, evt.kind, evt.pub_key]):
#                 raise NostrCommandException('Newer event for kind %s already exists' % evt.kind)
#
#             else:
#                 # delete existing
#                 batch.append(
#                     {
#                         'sql': 'delete from event_tags where id in '
#                                '(select id from events where kind=%s and pubkey=%s)' %
#                                (self._db.placeholder, self._db.placeholder),
#                         'args': [evt.kind, evt.pub_key]
#                     }
#                 )
#                 batch.append(
#                     {
#                         'sql': 'delete from events where id in '
#                                '(select id from events '
#                                'where kind=%s and pubkey=%s)'.replace('%s', self._db.placeholder),
#                         'args': [evt.kind, evt.pub_key]
#                     }
#                 )
#
#         batch.append({
#             'sql': 'insert into events(event_id, pubkey, created_at, kind, tags, content,sig) '
#                    'values(%s,%s,%s,%s,%s,%s,%s)'.replace('%s', self._db.placeholder),
#             'args': [
#                 evt.id, evt.pub_key, evt.created_at_ticks,
#                 evt.kind, json.dumps(evt.tags), evt.content, evt.sig
#             ]
#         })
#
#         # currently we only put in the tags table the bits needed to suport query [2:] could go in an extra field
#         # but as we already have the full info in events tbl probably don't need
#         for c_tag in evt.tags:
#             if len(c_tag) >= 2:
#                 tag_type = c_tag[0]
#                 tag_value = c_tag[1]
#                 batch.append({
#                     # 'sql': 'insert into event_tags SELECT last_insert_rowid(),?,?',
#                     'sql' : """
#                         insert into event_tags values (
#                         (select id from events where event_id=%s),
#                         %s,
#                         %s)
#                     """.replace('%s', self._db.placeholder),
#                     'args': [evt.id, tag_type, tag_value]
#                 })
#
#         self._db.execute_batch(batch)
#
#
#     def get_filter(self, filter):
#         """
#         from database returns events that match filter/s
#         doesn't do #e and #p filters yet (maybe never)
#         also author and ids are currently exact only, doesn't support prefix
#         :param filter: {} or [{},...] or filters
#         :return:
#         """
#         filter_query = SQLStore.make_filter_sql(filter,
#                                                 placeholder=self._db.placeholder)
#
#         # print(filter_query['sql'], filter_query['args'])
#
#         data = self._db.select_sql(sql=filter_query['sql'],
#                                    args=filter_query['args'])
#         ret = []
#         for c_r in data:
#             # we could actually do extra filter here
#             ret.append(Event(
#                 id=c_r['event_id'],
#                 pub_key=c_r['pubkey'],
#                 kind=c_r['kind'],
#                 content=c_r['content'],
#                 tags=c_r['tags'],
#                 created_at=util_funcs.ticks_as_date(c_r['created_at']),
#                 sig=c_r['sig']
#             ))
#         return ret
#
#     def do_delete(self, evt: Event):
#         if self._delete_mode == DeleteMode.DEL_NO_ACTION:
#             return
#         to_delete = evt.e_tags
#
#         # only flag as deleted
#         if self._delete_mode == DeleteMode.DEL_FLAG:
#             ret = self._db.execute_sql(sql='update events set deleted=true where event_id in (%s) and kind<>?' %
#                                            ','.join(['?'] * len(to_delete)),
#                                        args=to_delete + [Event.KIND_DELETE])
#         # actually delete
#         elif self._delete_mode == DeleteMode.DEL_DELETE:
#             batch = [
#                 {
#                     'sql': 'delete from event_tags where id in (select id from events '
#                            'where event_id in (%s) and kind<>?)' % ','.join(
#                         ['?'] * len(to_delete)),
#                     'args': to_delete + [Event.KIND_DELETE]
#                 },
#                 {
#                     'sql' : 'delete from events where event_id in (%s) and kind<>?' % ','.join(['?']*len(to_delete)),
#                     'args': to_delete + [Event.KIND_DELETE]
#                 }
#             ]
#             ret = self._db.execute_batch(batch)
#
#         return ret
#
#     def is_NIP09(self):
#         return self._delete_mode in (DeleteMode.DEL_FLAG, DeleteMode.DEL_DELETE)
#
# class SQLiteStore(SQLStore):
#     """
#         SQLite implementation of RelayStoreInterface
#
#     """
#     def __init__(self, db_file, delete_mode=DeleteMode.DEL_FLAG):
#         super().__init__(SQLiteDatabase(db_file),
#                          delete_mode=delete_mode)
#         logging.debug('SQLiteStore::__init__ db_file=%s, delete mode=%s' % (db_file,
#                                                                             self._delete_mode))
#
#     def create(self):
#         events_tbl_sql = """
#             create table events(
#                 id INTEGER PRIMARY KEY,
#                 event_id UNIQUE,
#                 pubkey text,
#                 created_at int,
#                 kind int,
#                 tags text,
#                 content text,
#                 sig text,
#                 deleted int)
#         """
#         events_tag_tbl_sql = """
#             create table event_tags(
#                 id int,
#                 type text,
#                 value text)
#         """
#         self._db.execute_batch([
#             {
#                 'sql': events_tbl_sql
#             },
#             {
#                 'sql': events_tag_tbl_sql
#             }
#         ])
#
#     def exists(self):
#         return Path(self._db.file).is_file()
#
#     def destroy(self):
#         os.remove(self._db.file)
#
#
# class PostgresStore(SQLStore):
#     """
#     Postgres implementation of RelayStoreInterface
#     """
#     def __init__(self, db_name, user, password, delete_mode=DeleteMode.DEL_FLAG):
#         super().__init__(PostgresDatabase(db_name=db_name,
#                                           user=user,
#                                           password=password),
#                          delete_mode=delete_mode)
#         self._db_name = db_name
#         self._user = user
#         self._password = password
#         logging.debug('PostgresStore::__init__ db=%s, user=%s, delete mode=%s' % (db_name,
#                                                                                   user,
#                                                                                   self._delete_mode))
#
#     def exists(self):
#         ret = True
#         try:
#             self._db.select_sql('select 1')
#         except OperationalError as oe:
#             if 'does not exist' in str(oe):
#                 ret = False
#         return ret
#
#     def create(self):
#         """
#         needs to be done above the level the store is created at, assumed that the same user has permissions to create
#         we can;'t just us postgres_db.execute_sql because it creates a tx and CREATE DATABASE won't work inside a tx
#         """
#         postgres_db = PostgresDatabase(db_name='postgres',
#                                        user=self._user,
#                                        password=self._password)
#         c = postgres_db._get_con()
#         c.autocommit = True
#         cur = c.cursor()
#         cur.execute(
#             """
#                 CREATE DATABASE "%s"
#                     WITH
#                     OWNER = postgres
#                     ENCODING = 'UTF8'
#                     LC_COLLATE = 'en_GB.UTF-8'
#                     LC_CTYPE = 'en_GB.UTF-8'
#                     TABLESPACE = pg_default
#                     CONNECTION LIMIT = -1;
#             """ % self._db_name
#         )
#
#
#         self._db.execute_batch([
#             {
#                 'sql': """
#                     create table events(
#                         id SERIAL PRIMARY KEY,
#                         event_id text UNIQUE,
#                         pubkey varchar(128),
#                         created_at int,
#                         kind int,
#                         tags text,
#                         content text,
#                         sig varchar(128),
#                         deleted int)
#                 """
#             },
#             {
#                 'sql': """
#                     create table event_tags(
#                         id int,
#                         type varchar(32),
#                         value text)
#                 """
#             }
#         ])
#
#     def destroy(self):
#         # as create
#         postgres_db = PostgresDatabase(db_name='postgres',
#                                        user=self._user,
#                                        password=self._password)
#         c = postgres_db._get_con()
#         c.autocommit = True
#         cur = c.cursor()
#         cur.execute(
#             """
#             SELECT
#             pg_terminate_backend (pg_stat_activity.pid)
#             FROM
#                 pg_stat_activity
#             WHERE
#             pg_stat_activity.datname = '%s';
#             """ % self._db_name
#         )
#         cur.execute('DROP DATABASE IF EXISTS "%s"' % self._db_name)