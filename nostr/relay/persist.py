import logging
import os
from db.db import Database
from data.data import DataSet
from nostr.event import Event
from nostr.util import util_funcs
from nostr.exception import NostrCommandException


class RelayStore:
    """
        persistence for the relay implementation, the relay only really needs to store events and
        structure (for example seperate table for tags) as best we can for querying.
        Note that it's unlikely that an sqlite base persistence layer will be ok if the relay is
        really being hit
    """

    @classmethod
    def make_filter_sql(cls, filters):
        """
        creates the sql to select events from a db given nostr filter
        NOTE tags are currently not dealt with so if needed this will have to be done in
        2nd pass on whats returned use the TODO: event filter on each
        :param filter:
        :return:
        """
        def for_single_filter(filter):
            def do_tags(tag_type):
                nonlocal args
                t_filter = filter['#'+tag_type]
                if isinstance(t_filter, str):
                    t_filter = [t_filter]
                e_sql = """
                %s id in 
                    (
                        select id from event_tags where type = '%s' and value in(%s)
                    )
                                """ % (join,
                                       tag_type,
                                       ','.join(['?'] * len(t_filter)))
                sql_arr.append(e_sql)
                args = args + t_filter

            # deleted isnull to filter deleted if in flag delete mode
            sql_arr = ['select * from events where deleted isnull']
            # join not really required anymore because its always and
            join = 'and'
            args = []
            if 'since' in filter:
                sql_arr.append(' %s created_at>=?' % join)
                args.append(filter['since'])
            if 'until' in filter:
                sql_arr.append(' %s created_at<=?' % join)
                args.append(filter['until'])
            if 'kinds' in filter:
                kind_arr = filter['kinds']
                if not hasattr(kind_arr,'__iter__')or isinstance(kind_arr,str):
                    kind_arr = [kind_arr]
                arg_str = ','.join(['?']*len(kind_arr))
                sql_arr.append(' %s kind in(%s)' % (join, arg_str))
                args = args + kind_arr
            if 'authors' in filter:
                auth_arr = filter['authors']
                if not hasattr(auth_arr,'__iter__') or isinstance(auth_arr,str):
                    auth_arr = [auth_arr]

                arg_str = 'or '.join(['pubkey like ?'] * len(auth_arr))
                sql_arr.append(' %s (%s)' % (join, arg_str))
                for c_arg in auth_arr:
                    args.append(c_arg + '%')

            if 'ids' in filter:
                ids_arr = filter['ids']
                if not hasattr(ids_arr,'__iter__') or isinstance(ids_arr,str):
                    ids_arr = [ids_arr]

                arg_str = ' or '.join(['event_id like ?']*len(ids_arr))
                sql_arr.append(' %s (%s)' % (join, arg_str))
                for c_arg in ids_arr:
                    args.append(c_arg+'%')

            # add other tags e.g. shared that appears on encrypted tags?
            if '#e' in filter:
                do_tags('e')
            if '#p' in filter:
                do_tags('p')

            return {
                'sql' : ''.join(sql_arr),
                'args' : args
            }

        # only been passed a single, put into list
        if isinstance(filters, dict):
            filters = [filters]

        sql = ''
        args = []
        for c_filter in filters:
            q = for_single_filter(c_filter)
            if sql:
                sql += ' union '
            sql = sql + q['sql']
            args = args + q['args']

        return {
            'sql': sql,
            'args': args
        }

    def __init__(self, db_file):
        self._db_file = db_file
        self._db = Database(db_file)
        logging.debug('RelayStore::__init__ db_file=%s', self._db_file)

    def create(self, tables=['events']):

        if 'events' in tables:
            evt_tmpl = DataSet(heads=[
                'id', 'event_id', 'pubkey', 'created_at', 'kind', 'tags', 'content', 'sig','deleted'
            ], data=[])
            evt_tmpl.create_sqlite_table(self._db_file, 'events', {
                'id': {
                    'type': 'INTEGER PRIMARY KEY '
                },
                'event_id': {
                    # not a type but all the underlying does is concat str so will do
                    'type': 'UNIQUE'
                },
                'created_at': {
                    'type': 'int'
                },
                'kind': {
                    'type': 'int'
                },
                # will only ever be set if flagged deletes
                'deleted' : {
                    'type' : 'int'
                }
            })

            tag_tmp = DataSet(heads=['id','type','value'])
            tag_tmp.create_sqlite_table(self._db_file, 'event_tags', {
                'id': {
                    'type' : 'int'
                }
            })

    def destroy(self, tables=['events']):
        """
            removes tbls as created in create - currently no key constraints so any table can be droped
        """
        if 'events' in tables:
            batch = [
                {
                    'sql': 'drop table event_tags'
                },
                {
                    'sql' : 'drop table events'
                }
            ]
            self._db.execute_batch(batch)
        # also remove the file, this make it easy for us to
        # know db needs creating without looking for tbls or something
        os.remove(self._db_file)

    def add_event(self, evt: Event, catch_err=False):
        """
        store event to db, maybe allow [] of events that will be done in batch?
        :param evt: Event obj
        :param catch_err: set to True if don't want to raise exception on err
        :return: True/False, you'll only get False when catch_err is True
        """
        batch = []
        # META and CONTACT_LIST event type supercede any previous events of same type, so if this event is newer
        # then we'll delete all pre-existing
        if evt.kind in (Event.KIND_META, Event.KIND_CONTACT_LIST):
            if self._db.select_sql(sql='select id from events where created_at>=? and kind=? and pubkey=?',
                                   args=[evt.created_at_ticks, evt.kind, evt.pub_key]):
                raise NostrCommandException('Newer event for kind %s already exists' % evt.kind)

            else:
                # delete existing
                batch.append(
                    {
                        'sql': 'delete from event_tags where id in '
                               '(select id from events where kind=? and pubkey=?)',
                        'args': [evt.kind, evt.pub_key]
                    }
                )
                batch.append(
                    {
                        'sql': 'delete from events where id in '
                                '(select id from events where kind=? and pubkey=?)',
                        'args': [evt.kind, evt.pub_key]
                    }
                )

        batch.append({
            'sql': 'insert into events(event_id, pubkey, created_at, kind, tags, content,sig) values(?,?,?,?,?,?,?)',
            'args': [
                evt.id, evt.pub_key, evt.created_at_ticks,
                evt.kind, str(evt.tags), evt.content, evt.sig
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
                    'sql' : """
                        insert into event_tags values (
                        (select id from events where event_id=?),
                        ?,
                        ?)
                    """,
                    'args': [evt.id,tag_type, tag_value]
                })

        return self._db.execute_batch(batch, catch_err=catch_err)

    def get_filter(self, filter):
        """
        from database returns events that match filter/s
        doesn't do #e and #p filters yet (maybe never)
        also author and ids are currently exact only, doesn't support prefix
        :param filter: {} or [{},...] or filters
        :return:
        """
        filter_query = RelayStore.make_filter_sql(filter)
        data = self._db.select_sql(sql=filter_query['sql'],
                                   args=filter_query['args'])
        ret = []
        for c_r in data:
            # we could actually do extra filter here
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

    def delete_events(self, ids, flag=False):
        if not ids:
            return True
        if isinstance(ids, str):
            ids = [ids]
        if isinstance(ids[0], Event):
            ids = [evt.id for evt in ids]

        # only flag as deleted
        if flag:
            ret = self._db.execute_sql(sql='update events set deleted=true where event_id in (%s) and kind<>?' %
                                           ','.join(['?'] * len(ids)),
                                       args=ids + [Event.KIND_DELETE])
        # actually delete
        else:
            batch = [
                {
                    'sql': 'delete from event_tags where id in (select id from events '
                           'where event_id in (%s) and kind<>?)' % ','.join(
                        ['?'] * len(ids)),
                    'args': ids + [Event.KIND_DELETE]
                },
                {
                    'sql' : 'delete from events where event_id in (%s) and kind<>?' % ','.join(['?']*len(ids)),
                    'args': ids + [Event.KIND_DELETE]
                }
            ]
            ret = self._db.execute_batch(batch)

        return ret