from __future__ import annotations

import time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.settings.handler import Settings
    from nostr.ident.event_handlers import ProfileEventHandler
    from nostr.ident.profile import ContactList
    from nostr.channels.event_handlers import ChannelEventHandler


import logging
from copy import deepcopy
from datetime import datetime, timedelta
from nostr.event.event import Event
from nostr.util import util_funcs
from nostr.channels.channel import Channel
from nostr.ident.profile import Profile, Contact
from nostr.client.client import Client


class RangeBackfill:

    def __init__(self,
                 client: Client,
                 settings: Settings,
                 start_dt: datetime,
                 until_ndays: int,
                 day_chunk: int,
                 do_event,
                 profile_handler: ProfileEventHandler = None):

        # NOTE currently this expects a single client not clientpool - it'd probably still work but not quite as
        # expected with client pool (we call from EOSE where we have single client obj
        # at the moment so this isn't a problem)
        self._client = client
        self._settings = settings
        self._start_dt = start_dt
        self._until_days = until_ndays
        self._day_chunk = day_chunk
        self._timeout = 30
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
        c_evt: Event
        # actual date we'll start from which may be further back if we already did some backfill
        act_start_date = self._get_start_date()
        until_date = self._start_dt - timedelta(days=self._until_days)
        if act_start_date <= until_date:
            print('%s no backfill required' % (self._client.url))
            return

        c_start = act_start_date

        while c_start > until_date:

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
                    ], timeout=self._timeout)
                    # just incase make sure we have newest first, mostly we don't care but _import_channel_info
                    # wants sorted newest to oldest
                    Event.sort(evts, inplace=True)

                    self._do_event(self._client, None, evts)

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


class ProfileBackfiller:

    def __init__(self, client: Client,
                 do_event,
                 profile_handler: ProfileEventHandler,
                 settings: Settings,
                 start_dt: datetime,
                 user_until: int = None,
                 follow_until: int = 0,
                 follow_follow_until: int = 0,
                 day_chunk: int = 10,
                 ):

        self._client = client
        self._settings = settings
        self._day_chunk = day_chunk
        self._start_dt = start_dt
        self._timeout = 30

        def _get_max(a,b):
            ret = a
            if not a is None:
                if b is None or b > a:
                    ret = b
            return ret

        # number of days to import back for each of the user, their follows and follows of their follows
        # if you don't want set to 0, set to None will get all we can from relays
        self._user_until = user_until
        self._follow_until = follow_until
        self._follow_follow_until = follow_follow_until

        # make sure user >= follow >= follow_follow
        self._follow_until = _get_max(self._follow_until, self._follow_follow_until)
        self._user_until = _get_max(self._user_until, self._follow_until)


        # user wher until value is None, after this date we'll just do a max pull with no since date
        self._oldest_max = datetime(2022, 1, 1)

        # base query for the events we're pulling in, when we get these we'll then go get
        # meta, channel creates, contacts etc. as required
        # TODO: nip4s, do seperately
        self._base_query = [{
            'kinds': [
                Event.KIND_TEXT_NOTE,
                Event.KIND_REACTION,
                Event.KIND_DELETE,
                Event.KIND_CHANNEL_MESSAGE
            ]
        }]

        self._profile_handler = profile_handler
        self._do_event = do_event

    def _get_state_key(self, the_client: Client, pub_k: str):
        return '%s.%s.profile-backfill' % (the_client.url,
                                           pub_k)

    def _get_start_date(self, c: Client, pub_k: str):
        # get the start date we'll actually run from, either _start_dt as given or
        # further back if we already ran
        if hasattr(self._start_dt, '__call__'):
            ret = self._start_dt()
        else:
            ret = self._start_dt

        state_k = self._get_state_key(c, pub_k)
        previous_run_finished = self._settings.get(state_k)
        if previous_run_finished:
            ret = util_funcs.ticks_as_date(int(previous_run_finished))

        return ret

    def _do_backfill(self, client: Client, authors, newest: int, oldest: int):
        if isinstance(authors, str):
            authors = [authors]

        c_evt: Event

        c_start = newest
        # set True when we make are final pull
        is_complete = False

        while is_complete is False:
            c_end = c_start - timedelta(days=self._day_chunk)
            # normally we should supply this
            if oldest:
                if c_end < oldest:
                    c_end = oldest
                    is_complete = True
            else:
                if c_end < self._oldest_max:
                    c_end = None
                    is_complete = True


            # do stuff
            print('%s backfilling %s - %s' % (client.url,
                                              c_start, c_end))

            # we never give up on a chunk, we probably should fail out at somepoint...
            got_chunk = False
            while got_chunk is False:
                try:
                    c_query = deepcopy(self._base_query)
                    c_query[0]['until'] = util_funcs.date_as_ticks(c_start)
                    if c_end:
                        c_query[0]['since'] = util_funcs.date_as_ticks(c_end)

                    c_query[0]['authors'] = authors

                    evts = client.query(filters=c_query, timeout=self._timeout)
                    self._do_event(client, None, evts)

                    got_chunk = True
                    logging.debug('%s recieved %s events ' % (client.url,
                                                              len(evts)))

                except Exception as e:
                    logging.debug('do_backfill: %s error fetching range %s - %s, %s' % (client.url,
                                                                                        c_start,
                                                                                        c_end,
                                                                                        e))
                    time.sleep(1)



            c_start = c_end
            # update back fill time
            for k in authors:
                state_k = self._get_state_key(client, k)
                if c_end is None:
                    filled_to = 1
                else:
                    filled_to = util_funcs.date_as_ticks(c_end)

                self._settings.put(state_k, filled_to)

        logging.info('ProfileBackfiller::event backfill is complete - %s' % client.url)

    def _do_backfill_chunked(self, client: Client, authors, newest: int, oldest: int):
        """
        just _do_backfill called but with the authors chunked so we don't get error from relays
        :param client:
        :param authors:
        :param newest:
        :param oldest:
        :return:
        """
        for c_authors in util_funcs.chunk(authors, 250):
            self._do_backfill(client=client,
                              authors=c_authors,
                              newest=newest,
                              oldest=oldest)

    def _backfill_profile(self, p: Profile):
        # no profile backfill
        if self._user_until == 0:
            logging.info('ProfileBackfiller::_backfill_profile _user_until is 0, no backfill requested')
            return

        for c_client in self._client:
            # we'll backfill from here onwards
            newest = self._get_start_date(c_client, p.public_key)
            # as far back as we want to fill
            oldest = None
            if self._user_until:
                oldest = datetime.now() - timedelta(days=self._user_until)

            logging.info('ProfileBackfiller::_backfill_profile starting profile backfill for %s from client %s'
                         % (p.display_name(), c_client.url))

            self._do_backfill(client=c_client,
                              newest=newest,
                              oldest=oldest,
                              authors=p.public_key)

            self._backfill_dms(client=c_client,
                               for_user=p)

    def _backfill_dms(self, client: Client, for_user: Profile):
        # we never give up on a chunk, we probably should fail out at somepoint...
        got_chunk = False
        while got_chunk is False:
            try:
                evts = client.query(
                    [
                        {
                            'kinds': [Event.KIND_ENCRYPT],
                            'authors': [for_user.public_key],
                        }
                    ],
                    [
                        {
                            'kinds': [Event.KIND_ENCRYPT],
                            '#p': [for_user.public_key]
                        }
                    ]
                )
                self._do_event(client, None, evts)
                key = '%s.%s.dms' % (client.url,
                                     for_user.public_key)
                self._settings.put(key, 'true')

                got_chunk = True

            except Exception as e:
                logging.debug('ProfileBackfiller::_backfill_dms: %s error fetching dms for %s - %s' % (client.url,
                                                                                                       for_user.public_key,
                                                                                                       e))
                time.sleep(1)

            logging.info('%s got dms for %s events ' % (client.url,
                                                        len(evts)))

    def _get_authors(self, p: Profile,
                     follow_follows=False):
        """
        returns pub_ks ok profiles p follows or if follow_follows is True then the of those they follow
        excluding keys of the profiles p follows
        :param p:
        :param follow_follows:
        :return:
        """
        self._profile_handler.load_contacts(p)
        c_c: Contact
        c_p: Profile
        follow_keys = set([c_c.contact_public_key for c_c in p.contacts])
        if follow_follows:
            # force profiles to exist
            self._profile_handler.get_profiles(follow_keys)
            ret = set([])
            for c_k in follow_keys:
                c_p = self._profile_handler.get_pub_k(c_k)
                if c_p:
                    self._profile_handler.load_contacts(c_p)
                    for c_c in c_p.contacts:
                        c_pub_k = c_c.contact_public_key
                        if c_pub_k not in follow_keys and c_pub_k not in ret:
                            ret.add(c_pub_k)
            ret = list(ret)

        else:
            ret = list(follow_keys)

        return ret

    def _backfill_followers(self, p: Profile, follow_follow=False):
        until = self._follow_until
        if follow_follow:
            until = self._follow_follow_until

        # no follower backfill
        if until == 0:
            logging.info('ProfileBackfiller::_backfill_followers until is 0, no backfill requested')
            return

        c_newest = None
        authors = self._get_authors(p, follow_follow)
        # as far back as we want to fill
        oldest = None
        if until:
            oldest = datetime.now() - timedelta(days=until)

        authors_to_fetch = []
        for c_client in self._client:
            for c_pk in authors:
                # we already have older data
                if c_newest and c_newest < oldest:
                    continue

                p_newest = self._get_start_date(c_client, c_pk)
                if c_newest is None or c_newest == p_newest:
                    c_newest = p_newest
                    authors_to_fetch.append(c_pk)
                else:
                    self._do_backfill_chunked(c_client,
                                              authors=authors,
                                              newest=c_newest,
                                              oldest=oldest)
                    authors_to_fetch = []
                    c_newest = p_newest

            # any still to do, will be all if their all on same start date
            if authors:
                self._do_backfill_chunked(c_client,
                                          authors=authors_to_fetch,
                                          newest=c_newest,
                                          oldest=oldest)

    def _backfill_user(self, p: Profile):
        # do our ourself
        self._backfill_profile(p)
        # our follows
        self._backfill_followers(p, follow_follow=False)
        # folows of our follows
        self._backfill_followers(p, follow_follow=True)

    def profile_update(self, n_profile: Profile, o_profile: Profile):
        # just linked to a profile, we'll start a backfill for this profile
        if n_profile.private_key is not None and o_profile.private_key is None:
            self._backfill_user(n_profile)

    def contact_update(p: Profile, n_c: ContactList, o_c: ContactList):
        pass
