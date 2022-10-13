from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.event.event import Event
    from nostr.event.persist import ClientEventStoreInterface

import json
from abc import ABC, abstractmethod
from nostr.channels.channel import Channel, ChannelList
from nostr.util import util_funcs
from db.db import SQLiteDatabase, QueryFromFilter


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

    def select(self, filter={}):
        my_q = QueryFromFilter('select * from channels',
                               filter=filter,
                               placeholder=self._db.placeholder).get_query()

        channels = self._db.select_sql(sql=my_q['sql'],
                                       args=my_q['args'])
        ret = []
        for c_c in channels:
            ret.append(Channel(event_id=c_c['event_id'],
                               create_pub_k=c_c['create_pub_k'],
                               attrs=c_c['attrs'],
                               created_at=c_c['created_at'],
                               updated_at=c_c['updated_at']))
        return ChannelList(ret)

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