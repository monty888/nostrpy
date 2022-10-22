from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.event.persist import ClientEventStoreInterface

import json
from abc import ABC, abstractmethod
from nostr.channels.channel import Channel, ChannelList
from nostr.util import util_funcs
from db.db import SQLiteDatabase, QueryFromFilter
from data.data import DataSet
from nostr.event.event import Event


class ChannelStoreInterface(ABC):

    @abstractmethod
    def put(self, c: Channel):
        """
        :param c:
        :return:
        """

    @abstractmethod
    def select(self, filter={}) -> ChannelList:
        """
        :param filter:
        :return:
        """

    @abstractmethod
    def channels_for_keys(self, keys: [str]):
        """
        :param keys:
        :return:
        """


    def import_from_events(self,
                           event_store: ClientEventStoreInterface,
                           evts: [Event] = None,
                           since=None):
        """
        :param evts:
        :param event_store:
        :param since:
        :return:
        """

        # if no events given then events since from events_store
        if evts is None:
            evt_filter = {
                'kinds': [Event.KIND_CHANNEL_CREATE]
            }
            if since is not None:
                evt_filter['since'] = since
                evts = event_store.get_filter(evt_filter)

        c: Channel
        for c_evt in evts:
            c = Channel.from_event(c_evt)
            # if they're not named we won't import at least not for now
            if c.name is not None:
                self.put(c)


class SQLiteSQLChannelStore(ChannelStoreInterface):

    def __init__(self, db_file):
        self._db_file = db_file
        self._db = SQLiteDatabase(self._db_file)

    def _prepare_put(self, c: Channel, batch=None):
        if batch is None:
            batch = []

        sql = """
            insert or replace into 
                channels (event_id, attrs, name, picture, about, create_pub_k, created_at, updated_at) 
                        values(?,?,?,?,?,?,?,?)
            on conflict(event_id)
            do update set 
                attrs = excluded.attrs,
                name = excluded.name,
                picture = excluded.picture,
                about = excluded.about,
                updated_at = excluded.updated_at
            where excluded.updated_at > updated_at
        """
        args = [
            c.event_id,
            json.dumps(c.attrs),
            c.name, c.picture, c.about, c.create_pub_k,
            c.created_at,
            c.updated_at
        ]

        batch.append({
            'sql': sql,
            'args': args
        })

        return batch

    def put(self, c: Channel):
        batch = []
        if not hasattr(c, '__iter__'):
            c = [c]

        for c_c in c:
            self._prepare_put(c_c, batch)

        return self._db.execute_batch(batch)

    def select(self, limit=None, until=None) -> DataSet:
        my_sql ="""
			select 
				c.event_id as c_id,
                c.create_pub_k as c_create_pub_k,
                c.attrs as c_attrs,
                c.created_at as c_created_at,
                c.updated_at as c_updated_at,
                last_post_pub_k,
                last_post_text,
                last_post_time
			from channels c
			left outer join 
			(select 
                c_id,
                c_create_pub_k,
                c_attrs,
                c_created_at,
                c_updated_at,
                last_post_pub_k,
                last_post_text,
                last_post_time
                from (
                select 
                c.event_id as c_id,
                c.create_pub_k as c_create_pub_k,
                c.attrs as c_attrs,
                c.created_at as c_created_at,
                c.updated_at as c_updated_at,
                e.content as last_post_text,
                e.pubkey as last_post_pub_k,
                e.created_at as last_post_time,
                row_number() over (PARTITION by et.value order by e.created_at desc) as rn
                from channels c
                inner join event_tags et on et.type='e' and et.value=c.event_id
                inner join events e on et.id = e.id
                where e.kind=42
                ) as channels
                where channels.rn=1) as with_posts on c.event_id = c_id
        """
        args = []

        if until:
            my_sql = my_sql + 'and last_post_time < %s' % self._db.placeholder
            args.append(until)

        my_sql = my_sql + ' order by last_post_time desc'

        if limit:
            my_sql = my_sql + ' limit %s' % self._db.placeholder
            args.append(limit)

        channels = self._db.select_sql(sql=my_sql, args=args)

        ret = []
        new_c: Channel
        for c_c in channels:
            new_c = Channel(event_id=c_c['c_id'],
                            create_pub_k=c_c['c_create_pub_k'],
                            attrs=c_c['c_attrs'],
                            created_at=c_c['c_created_at'],
                            updated_at=c_c['c_updated_at'])

            if c_c['last_post_pub_k']:
                new_c.last_post = Event(
                    kind=Event.KIND_CHANNEL_MESSAGE,
                    content=c_c['last_post_text'],
                    pub_key=c_c['last_post_pub_k'],
                    created_at=c_c['last_post_time']
                )

            ret.append(new_c)
        return ChannelList(ret)


    def channels_for_keys(self, keys: [str]):
        my_q = QueryFromFilter("""
            select distinct et.value 
            from events e
            inner join event_tags et on et.id = e.id
            inner join channels c on et.value = c.event_id
        """,
                               filter=[
                                   {
                                       'kind': 42
                                   },
                                   'and',
                                   {
                                       'pubkey': keys
                                   }
                               ],
                               placeholder='?').get_query()
        return self._db.select_sql(sql=my_q['sql'],
                                   args=my_q['args']).data_arr('value')

    def create(self):
        self._db.execute_batch([
            {
                'sql': """
                    create table channels(
                        event_id text,
                        attrs text,
                        name text,
                        picture text,
                        about text,
                        create_pub_k text,
                        created_at int,
                        updated_at int,
                        UNIQUE(event_id) ON CONFLICT IGNORE
                    )
            """
            }
        ])

    def destroy(self):
        self._db.execute_batch([
            {
                'sql': 'drop table channels'
            }
        ])