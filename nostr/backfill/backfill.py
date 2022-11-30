from __future__ import annotations

import time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.client.client import Client
    from nostr.settings.handler import Settings
    from nostr.ident.event_handlers import ProfileEventHandler
    from nostr.channels.event_handlers import ChannelEventHandler

import logging
from datetime import datetime, timedelta
from nostr.event.event import Event
from nostr.util import util_funcs
from nostr.channels.channel import Channel


class RangeBackfill:

    def __init__(self,
                 client: Client,
                 settings: Settings,
                 start_dt: datetime,
                 until_ndays: int,
                 day_chunk: int,
                 do_event,
                 profile_handler: ProfileEventHandler = None,
                 channel_handler: ChannelEventHandler = None):

        self._client = client
        self._settings = settings
        self._start_dt = start_dt
        self._until_days = until_ndays
        self._day_chunk = day_chunk
        self._do_event = do_event
        self._profile_handler = profile_handler
        self._channel_handler = channel_handler

    def _get_start_date(self):
        # get the start date we'll actually run from, either _start_dt as given or
        # further back if we already ran
        ret = self._start_dt

        previous_run_finished = self._settings.get(self._client.url + '.backfilltime')
        if previous_run_finished:
            ret = util_funcs.ticks_as_date(int(previous_run_finished))

        return ret

    def _import_profile_info(self, for_keys):
        if self._profile_handler:
            # some relays limit the n of keys so keep this reasonable
            for k_chunk in util_funcs.chunk(list(for_keys), 250):
                ps = self._profile_handler.get_profiles(k_chunk)
                self._profile_handler.load_contacts(ps)
                self._profile_handler.load_followers(ps)

    def _import_channel_info(self, evts):

        if self._channel_handler:
            last_posts = {}
            for_keys = set([])

            for c_evt in evts:
                k = Channel.get_msg_channel_id(c_evt)
                # important uses .channels.channel as this won't attempt ot fetch missing
                if k and k not in for_keys and self._channel_handler.channels.channel(k) is None:
                    for_keys.add(k)
                    last_posts[k] = c_evt

            # chunk same reason as profiles
            for k_chunk in util_funcs.chunk(list(for_keys), 250):
                channels = self._channel_handler.get_channels(k_chunk, create_missing=True)
                c_chn: Channel
                # now update the last post we the msg that triggered us to create the channel
                for c_chn in channels:
                    c_chn.do_post(last_posts[c_chn.event_id])

    def run(self):
        c_evt: Event
        # actual date we'll start from which may be further back if we already did some backfill
        act_start_date = self._get_start_date()
        until_date = self._start_dt - timedelta(days=self._until_days)
        if act_start_date <= until_date:
            print('%s no backfill required' % (self._client.url))
            return

        c_start = act_start_date

        while c_start > until_date:
            # unique pubks that published events
            event_p_keys = set()

            c_end = c_start - timedelta(days=self._day_chunk)
            if c_end < until_date:
                c_end = until_date
            # do stuff
            print('%s backfilling %s - %s' % (self._client.url,
                                              c_start, c_end))
            got_chunk = False
            while got_chunk is False:
                try:
                    evts = self._client.query(filters=[
                        {
                            'kinds': [
                                Event.KIND_TEXT_NOTE,
                                Event.KIND_REACTION,
                                Event.KIND_DELETE,
                                Event.KIND_CHANNEL_MESSAGE
                            ],
                            'since': util_funcs.date_as_ticks(c_end),
                            'until': util_funcs.date_as_ticks(c_start)
                        }
                    ])
                    # just incase make sure we have newest first, mostly we don't care but _import_channel_info
                    # wants sorted newest to oldest
                    Event.sort(evts, inplace=True)

                    self._do_event(self._client, None, evts)

                    # for each unique public_k import the profile/contact info (if we have profile handler)
                    self._import_profile_info({c_evt.pub_key for c_evt in evts})

                    # for each channel msg import the channel meta (if we have channel handler)
                    self._import_channel_info(evts)

                    got_chunk = True

                except Exception as e:
                    logging.debug('do_backfill: %s error fetching range %s - %s, %s' % (self._client.url,
                                                                                        c_start,
                                                                                        c_end,
                                                                                        e))
                    time.sleep(1)

                print('%s recieved %s events ' % (self._client.url,
                                                  len(evts)))

            c_start = c_end
            # update back fill time
            self._settings.put(self._client.url + '.backfilltime', util_funcs.date_as_ticks(c_end))

        print('backfill is complete - %s' % self._client.url)