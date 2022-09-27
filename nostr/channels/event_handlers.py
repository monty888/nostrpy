import time
from nostr.event.event import Event
from nostr.channels.persist import ChannelStoreInterface, Channel, ChannelList
from nostr.util import util_funcs
import logging


class ChannelEventHandler:
    """
        similar to the profile event handler but for channels
    """

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

        # split events
        c_evt: Event
        channel_creates = [Channel.from_event(c_evt) for c_evt in evt if c_evt.kind == Event.KIND_CHANNEL_CREATE]
        # maybe change but for now cut any non named channels
        channel_creates = [c_c for c_c in channel_creates if c_c.name is not None]

        def get_store_func(the_chunk):
            def the_func():
                self._do_creates(the_chunk)
            return the_func

        for c_chunk in util_funcs.chunk(channel_creates, self._max_insert_batch):
            util_funcs.retry_db_func(get_store_func(c_chunk))
            time.sleep(0.1)

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
                    self._on_profile_update(c_update[0], c_update[1])
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

    def channel(self, channel_id) -> Channel:
        return self._channels.channel(channel_id)

    def matches(self, m_str='', max_match=None):
        return self._channels.matches(m_str=m_str,
                                      max_match=max_match,
                                      search_about=False)

