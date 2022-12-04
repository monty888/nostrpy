from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass

import logging
from threading import BoundedSemaphore
from datetime import datetime
import json
from json import JSONDecodeError
from nostr.util import util_funcs
from nostr.event.event import Event


class Channel:

    @staticmethod
    def from_event(evt: Event):
        """
        TODO: add option to verify sig/eror if invalid?
        creates an event object from json - at the moment this must be a full event, has id and has been signed,
        may add option for presigned event in future
        :param evt_json: json to create the event, as you'd recieve from subscription
        :return:
        """
        return Channel(event_id=evt.id,
                       create_pub_k=evt.pub_key,
                       attrs=evt.content,
                       created_at=util_funcs.date_as_ticks(evt.created_at))

    @staticmethod
    def get_msg_channel_id(evt: Event):
        """
        for given channel message event returns the channel id that that msg is in
        :param evt:
        :return:
        """
        ret = None
        if evt.kind == Event.KIND_CHANNEL_MESSAGE:
            e_tags = evt.e_tags
            if e_tags:
                ret = e_tags[0]
        return ret

    def __init__(self, event_id: str, create_pub_k: str, attrs=None,
                 created_at: int = None, updated_at: int = None,
                 last_post: Event = None):
        self._event_id = event_id
        self._create_pub_k = create_pub_k
        self._attrs = {}
        if attrs is not None:
            if isinstance(attrs, dict):
                self._attrs = attrs
            # if is str rep e.g. directly from event turn it to {}
            elif isinstance(attrs, str):
                try:
                    self._attrs = json.loads(attrs)
                except JSONDecodeError as e:
                    print(attrs)
                    logging.debug(e)

        self._created_at = created_at
        if self._created_at is None:
            self._created_at = util_funcs.date_as_ticks(datetime.now())

        self._updated_at = self._created_at
        if updated_at is not None:
            self._updated_at = updated_at

        self._last_post = last_post

    def as_dict(self):
        last_post = None
        if self._last_post:
            last_post = self._last_post.event_data()

        return {
            'id': self.event_id,
            'create_pub_k': self.create_pub_k,
            'name': self.name,
            'about': self.about,
            'picture': self.picture,
            'last_post': last_post
        }

    @property
    def name(self):
        ret = self.get_attr('name')
        if ret is None:
            ret = '?unknown?'
        return ret

    @property
    def picture(self):
        return self.get_attr('picture')

    @property
    def about(self):
        return self.get_attr('about')

    @property
    def event_id(self):
        return self._event_id

    @property
    def create_pub_k(self):
        return self._create_pub_k

    @property
    def created_at(self):
        return self._created_at

    @property
    def updated_at(self):
        return self._updated_at

    @property
    def attrs(self):
        return self._attrs

    @attrs.setter
    def attrs(self, attrs) -> dict:
        self._attrs = attrs

    def get_attr(self, name):
        # returns vale for named atr, None if it isn't defined
        ret = None
        if name in self._attrs:
            ret = self._attrs[name]
        return ret

    def set_attr(self, name, value):
        self._attrs[name] = value

    @property
    def last_post(self) -> Event:
        return self._last_post

    @last_post.setter
    def last_post(self, evt: Event):
        self._last_post = evt

    def do_post(self, evt: Event):
        # as last_post except it'll only update _last_post if the given evt is actually newer
        if self._last_post is None or evt.created_at_ticks > self.last_post.created_at_ticks:
            self._last_post = evt

    def __str__(self):
        return '%s[%s]' % (self.name[0:15].ljust(18), self.event_id)

    def __lt__(self, other):
        ret = False
        if self.name and other.name:
            ret = self.name.lower() < other.name.lower()
        elif self.name and other.name is None:
            ret = True
        return ret


class ChannelList:

    def __init__(self, channels: [Channel]):
        self._channels = channels
        self._lookup = {}
        c_c: Channel
        for c_c in self._channels:
            self._lookup[c_c.event_id] = c_c

        self._lock = BoundedSemaphore()

    def matches(self, m_str, max_match=None, search_about=False):
        self.sort()
        if m_str.replace(' ', '') == '':
            ret = self._channels
            if max_match:
                ret = ret[:max_match]
            return ret

        # simple text text lookup against name/pubkey
        ret = []
        # we're going to ignore case
        m_str = m_str.lower()
        c_c: Channel

        for c_c in self._channels:
            # pubkey should be lowercase but name we convert
            if m_str in c_c.event_id or \
                    c_c.name and m_str in c_c.name.lower() \
                    or search_about and c_c.about is not None and m_str in c_c.about:
                ret.append(c_c)

            # found enough matches
            if max_match and len(ret) >= max_match:
                break
        return ret

    def put(self, c:Channel):
        ret = False
        if c.event_id not in self._lookup:
            self._channels.append(c)
            self._lookup[c.event_id] = c
            ret = True
        else:
            o_c = self._lookup[c.event_id]
            if c.updated_at > o_c.updated_at:
                self._channels = [c_c for c_c in self._channels if c_c.event_id != c.event_id]
                self._lookup[c.event_id] = c
                ret = True
        return ret

    def channel(self, channel_id):
        ret = None
        if channel_id in self._lookup:
            ret = self._lookup[channel_id]
        return ret

    @property
    def channels(self):
        return self._channels

    def sort(self):
        def keyFunc(c: Channel):
            ret = 0
            if c.last_post:
                ret = c.last_post.created_at_ticks
            return ret

        with self._lock:
            self._channels.sort(key=keyFunc,
                                reverse=True)

    def __len__(self):
        return len(self._channels)

    def __getitem__(self, item):
        return self._channels[item]
