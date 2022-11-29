from __future__ import annotations

import time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.client.client import Client
    from nostr.settings.handler import Settings
    from nostr.ident.event_handlers import ProfileEventHandler

import logging
from datetime import datetime, timedelta
from nostr.event.event import Event
from nostr.util import util_funcs


class RangeBackfill:

    def __init__(self,
                 client: Client,
                 settings: Settings,
                 start_dt: datetime,
                 until_ndays: int,
                 day_chunk: int,
                 do_event,
                 profile_handler: ProfileEventHandler = None):

        self._client = client
        self._settings = settings
        self._start_dt = start_dt
        self._until_days = until_ndays
        self._day_chunk = day_chunk
        self._do_event = do_event
        self._profile_handler = profile_handler

    def _get_start_date(self):
        # get the start date we'll actually run from, either _start_dt as given or
        # further back if we already ran
        ret = self._start_dt

        previous_run_finished = self._settings.get(self._client.url + '.backfilltime')
        if previous_run_finished:
            ret = util_funcs.ticks_as_date(int(previous_run_finished))

        return ret

    def run(self):
        # actual date we'll start from which may be further back if we already did some backfill
        act_start_date = self._get_start_date()
        until_date = self._start_dt - timedelta(days=self._until_days)
        if act_start_date <= until_date:
            print('%s no backfill required' % (self._client.url))
            return

        c_start = act_start_date

        while c_start > until_date:
            ukeys = set()
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
                    self._do_event(self._client, None, evts)
                    # now we'l  try get profile and contact info for events we got
                    c_evt: Event
                    ukeys = {c_evt.pub_key for c_evt in evts}.union(ukeys)
                    if self._profile_handler:
                        # some relays limit the n of keys so keep this reasonable
                        for k_chunk in util_funcs.chunk(list(ukeys), 250):
                            ps = self._profile_handler.get_profiles(k_chunk)
                            self._profile_handler.load_contacts(ps)
                            self._profile_handler.load_followers(ps)

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