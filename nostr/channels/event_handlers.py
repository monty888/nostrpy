from __future__ import annotations
import time
from nostr.event.event import Event
from nostr.channels.persist import ChannelStoreInterface, Channel, ChannelList
from nostr.util import util_funcs
from nostr.client.client import Client
from gevent import Greenlet
import logging


class ChannelEventHandler:
    """
        similar to the profile event handler but for channels
    """

    @staticmethod
    def import_channel_info(channel_handler: ChannelEventHandler, events: [Event]):
        # just incase , make sure sorted newest first else last posts will be incorrect
        evts = Event.sort(events, inplace=False)

        last_posts = {}
        for_keys = set([])

        for c_evt in evts:
            k = Channel.get_msg_channel_id(c_evt)
            # important uses .channels.channel as this won't attempt ot fetch missing
            if k and k not in for_keys and channel_handler.channels.channel(k) is None:
                for_keys.add(k)
                last_posts[k] = c_evt

        # chunk same reason as profiles
        for k_chunk in util_funcs.chunk(list(for_keys), 250):
            channels = channel_handler.get_channels(k_chunk, create_missing=True)
            c_chn: Channel
            # now update the last post we the msg that triggered us to create the channel
            for c_chn in channels:
                c_chn.do_post(last_posts[c_chn.event_id])

    def __init__(self,
                 channel_store: ChannelStoreInterface,
                 on_channel_update=None,
                 max_insert_batch=500):

        self._store = channel_store
        self._channels = self._store.select()
        self._on_channel_update = on_channel_update
        self._max_insert_batch = max_insert_batch

    def do_event(self, sub_id, evt: Event, relay):
        if not hasattr(evt, '__iter__'):
            evt = [evt]

        def get_store_func(the_chunk, for_func):
            def the_func():
                for_func(the_chunk)
            return the_func

        channel_creates = self._get_filtered_creates(evt)
        for c_chunk in util_funcs.chunk(channel_creates, self._max_insert_batch):
            util_funcs.retry_db_func(get_store_func(c_chunk, self._do_creates))
            time.sleep(0.1)

        channel_posts = self._get_filtered_posts(evt)
        for c_chunk in util_funcs.chunk(channel_posts, self._max_insert_batch):
            util_funcs.retry_db_func(get_store_func(c_chunk, self._do_posts))
            time.sleep(0.1)

        if channel_posts:
            self.channels.sort()

    def _get_filtered_creates(self, evts: [Event]) -> [Event]:
        # split events
        c_evt: Event
        ret = [Channel.from_event(c_evt) for c_evt in evts if c_evt.kind == Event.KIND_CHANNEL_CREATE]

        # maybe change but for now cut any non named channels, also skip if we already have this channel id
        c_c: Channel
        ret = [c_c for c_c in ret
               if c_c.name and not self._channels.channel(c_c.event_id)]

        return ret

    def _get_filtered_posts(self, evts: [Event]) -> [Event]:
        # split events
        c_evt: Event
        ret = [c_evt for c_evt in evts if c_evt.kind == Event.KIND_CHANNEL_MESSAGE]

        # we only keep those for which we know the channel
        ret = [c_evt for c_evt in ret
               if self.channels.channel(Channel.get_msg_channel_id(c_evt))]

        return ret

    def _do_posts(self, posts: [Event]):
        c_evt: Event
        c: Channel
        for c_evt in posts:
            c = self.channels.channel(Channel.get_msg_channel_id(c_evt))
            # updates if c_evt is newer than whatever we already have
            c.do_post(c_evt)

    def _do_creates(self, channels: [Channel]):
        c_evt: Event
        c_c: Channel
        c_e: Channel

        self._store.put(channels)

        # update local cache
        updates = []
        for c_c in channels:
            o_e = self._channels.channel(c_c.event_id)
            if self._channels.put(c_c):
                updates.append([c_c, o_e])

        # fire update if any, probably change to send as batch too
        if self._on_channel_update:
            for i, c_update in enumerate(updates):
                try:
                    self._on_channel_update(c_update[0], c_update[1])
                except Exception as e:
                    logging.debug('ChannelEventHandler:_do_creates>_on_channel_update error: %s, channel: %s ' % (e,
                                                                                                                  c_c.event_id))

    @property
    def channels(self) -> ChannelList:
        return self._channels

    @property
    def store(self) -> ChannelStoreInterface:
        return self._store

    def set_on_update(self, on_update):
        self._on_update = on_update

    def get_id(self, channel_id) -> Channel:
        return self._channels.channel(channel_id)

    def get_channels(self, channel_ids: [str], create_missing=True) -> ChannelList:
        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]

        channels = []
        for k in channel_ids:
            c = self.channels.channel(k)
            if c:
                channels.append(c)
            elif create_missing:
                # TODO check k is valid?
                channels.append(Channel(event_id=k))

        return ChannelList(channels)

    def matches(self, m_str='', max_match=None):
        return self._channels.matches(m_str=m_str,
                                      max_match=max_match,
                                      search_about=False)


class NetworkedChannelEventHandler(ChannelEventHandler):

    def __init__(self,
                 channel_store: ChannelStoreInterface,
                 client: Client,
                 on_channel_update=None,
                 max_insert_batch=500):

        self._client = client
        super().__init__(channel_store=channel_store,
                         on_channel_update=on_channel_update,
                         max_insert_batch=max_insert_batch)

    def fetch_channel_creates(self, keys):
        if isinstance(keys, str):
            keys = keys.split(',')

        evts = self._client.query({
            'kinds': [Event.KIND_CHANNEL_CREATE],
            'ids': keys
        })
        ret = []
        c_evt: Event
        if evts:
            # return chanels we found
            ret = [Channel.from_event(c_evt) for c_evt in evts]
            Greenlet(util_funcs.get_background_task(self._do_creates, ret)).start_later(0)

        return ret

    def get_id(self, channel_id) -> Channel:
        ret = super().get_id(channel_id)
        if ret is None:
            fetched = self.fetch_channel_creates(channel_id)
            if fetched:
                ret = fetched[0]

        return ret

    def get_channels(self, channel_ids: [str], create_missing=True) -> ChannelList:
        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]
        ret = super().get_channels(channel_ids, create_missing=False)
        to_fetch = [k for k in channel_ids if ret.channel(k) is None]

        ret = ret.channels

        if to_fetch:
            to_fetch.sort()
            ret = ret + self.fetch_channel_creates(','.join(to_fetch))

        c: Channel
        if len(ret) != len(channel_ids) and create_missing:
            got = set([c.event_id for c in ret])
            for k in channel_ids:
                if k not in got:
                    empty_channel = Channel(event_id=k,
                                            # sub the same as we have no idea what the pub_k is
                                            create_pub_k='')
                    ret.append(empty_channel)
                    # so we won't continually be trying to fetch
                    # on seeing a meta event it'll get updated anyhow
                    self.channels.put(empty_channel)

        return ChannelList(ret)
