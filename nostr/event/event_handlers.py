from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nostr.ident.profile import Profile
    from nostr.client.client import Client
    from nostr.settings.handler import Settings

import copy
import json
import time
from datetime import datetime, timedelta
from collections import OrderedDict
from functools import lru_cache
from nostr.event.event import Event, EventTags
from nostr.util import util_funcs
from nostr.event.persist import ClientEventStoreInterface
from nostr.spam_handlers.spam_handlers import SpamHandlerInterface


class EventHandler:
    """
        persists event we have seen to storage, profiles created/updated for meta_data type
        TODO: either add back in persist profile here or move to own handler
    """
    @staticmethod
    def reaction_lookup(content: str):
        lookup = {
            '': 'like',
            'like': 'like',
            '+': 'like',
            '-': 'dislike',
            '👍': 'agree',
            'wtf': 'wtf'
        }
        ret = 'other'
        content = content.lower()
        if content in lookup:
            ret = lookup[content]
        # couldn't get this to lookup from dict
        elif content == u'❤️':
            ret = 'like'

        return ret

    def __init__(self,
                 store: ClientEventStoreInterface,
                 max_insert_batch=500,
                 spam_handler: SpamHandlerInterface = None):
        self._store = store
        self._max_insert_batch = max_insert_batch
        self._spam_handler = spam_handler

    def get_events_by_ids(self, ids):
        if isinstance(ids, str):
            ids = [ids]

        ids.sort()

        return copy.deepcopy(self._get_events_by_ids(json.dumps(ids)))

    @lru_cache(maxsize=100)
    def _get_events_by_ids(self, ids):
        """
        just goes to the store at the moment but as event with id are immutable we may have extra level of cache here
        in the future
        :param ids:
        :return:
        """
        ids = json.loads(ids)
        return self._store.get_filter({
            'ids': ids
        })

    def do_event(self, sub_id, evt: Event, relay):
        def get_store_func(the_chunk):
            def the_func():
                self._store.add_event_relay(the_chunk, relay)
            return the_func

        for c_evt_chunk in util_funcs.chunk(evt, self._max_insert_batch):
            # de-spam chunk
            c_evt_chunk = [c_evt for c_evt in c_evt_chunk if not self.is_spam(c_evt)]

            util_funcs.retry_db_func(get_store_func(c_evt_chunk))
            time.sleep(0.1)

    def is_spam(self, evt: Event):
        return self._spam_handler and self._spam_handler.is_spam(evt)

    def get_events(self, filter,
                   use_profile: Profile = None,
                   embed_reactions=True,
                   add_reactions_flag=True,
                   embed_replies=False) -> [Event]:
        c_evt: Event
        events = self._store.get_filter(filter)

        if add_reactions_flag and use_profile:
            events = self._add_reacted_to(use_profile, events)

        # for reaction events to be useful you'll probably want to embed the event that is being reacted to
        if embed_reactions:
            self.add_reaction_events(use_profile, events)
        if embed_replies:
            # channels
            use_offset = 1
            if Event.KIND_ENCRYPT in filter[0]['kinds']:
                use_offset = 0

            self._add_reply_events(events, offset=use_offset)

        return events

    def _map_reaction_events(self, evts: []):
        """
        for events returns all the events that have been reacted to if we can find them
        :param evts:
        :return:
        """
        r_evts = []
        r_to_ids = []
        r_to_id_map = {}
        # reaction evts only
        for c_evt in evts:
            e_tags = EventTags(c_evt['tags']).e_tags
            # if it doesn't have e_tags then there is something wrong with the reaction so we ignore
            if c_evt['kind'] == Event.KIND_REACTION and e_tags:
                r_evts.append(c_evt)
                r_to_id = e_tags[len(e_tags)-1]
                r_to_ids.append(e_tags[len(e_tags)-1])
                r_to_id_map[c_evt['id']] = r_to_id

        return r_evts, r_to_id_map

    def _merge_reaction_events(self, r_evts: [], r_to_evts: [], reaction_map: {}, use_profile: Profile):
        # make a lookup of r_to_evts, we may not have all the events reacted to by r_evts
        c_evt: Event
        r_lookup = dict((c_evt['id'], c_evt) for c_evt in r_evts)
        r_to_lookup = dict((c_evt['id'], c_evt) for c_evt in r_to_evts)

        # add r_event_data as r_event, we do over r_evts but this is the same data as
        # evts so we're actually changing there
        for r_id in reaction_map.keys():
            r_to_id = reaction_map[r_id]
            r_evt = r_lookup[r_id]

            if r_to_id in r_to_lookup:
                r_evt['react_event'] = r_to_lookup[r_to_id]
            else:
                pub_k = '?no_pub_k?'
                p_tags = EventTags(r_evt['tags']).p_tags
                if p_tags:
                    pub_k = p_tags[0]

                r_evt['react_event'] = Event(id=r_id,
                                             content='unable to find reacted to event',
                                             pub_key=pub_k).event_data()

            # add interpretation
            interpretation = EventHandler.reaction_lookup(r_evt['content'])
            r_evt['interpretation'] = interpretation
            if interpretation == 'like' and use_profile and use_profile.public_key == r_evt['pubkey']:
                r_evt['react_event']['react_like'] = True

    def add_reaction_events(self, use_profile: Profile, evts: []):
        """
            adds react_event to any kind7 reaction events
        """
        # get reacted to events if any
        r_evts, r_to_id_map = self._map_reaction_events(evts)
        # nothing more to do
        if not r_evts:
            return

        # fetch reacted to events
        r_to_evts = self.get_events_by_ids(list(r_to_id_map.values()))

        # now embed in the reacted to events
        self._merge_reaction_events(r_evts, r_to_evts, r_to_id_map, use_profile)

        return evts

    def _add_reacted_to(self, p: Profile, evts: []):
        """
            for given events returns a lookup of [event_id] {
                'type' : true     p reacted to e this type - undefined if not true
            }
            NOTE if evts is actually reaction events then the actual events being reacted to must be embedded
            for the reactions to show
        """

        def _use_event(the_evt):
            ret = the_evt
            if the_evt['kind'] == Event.KIND_REACTION and 'react_event' in the_evt:
                ret = the_evt['react_event']
            return ret

        r_evts = self._store.get_filter({
            'kinds': [Event.KIND_REACTION],
            'authors': [p.public_key],
            '#e': [_use_event(c_evt)['id'] for c_evt in evts]
        })

        # make a look up of reaction mappings
        r_lookup = {}
        for c_evt in r_evts:
            e_tags = EventTags(c_evt['tags']).e_tags
            if e_tags:
                interpretation = EventHandler.reaction_lookup(c_evt['content'])
                r_to_id = e_tags[0]
                if r_to_id not in r_lookup:
                    r_lookup[r_to_id] = {}

                # we only care if we have the type or not e.g. for like on/off
                # for other expect the caller should know what its looking for
                r_lookup[r_to_id]['react_' + interpretation] = True
                r_lookup[r_to_id]['react_' + interpretation + '_id'] = c_evt['id']

        # finally merged in the reactions
        for c_evt in evts:
            use_id = _use_event(c_evt)['id']
            if use_id in r_lookup:
                if use_id == c_evt['id']:
                    c_evt.update(r_lookup[use_id])
                else:
                    c_evt['react_event'].update(r_lookup[use_id])

        return evts

    def _add_reply_events(self, evts:[], offset=1, max_reply=1):
        """
        add reply_events [] change to single
        :param evts:
        :return:
        """
        # evts that have been replied too
        reply_events = [evt for evt in evts if len(EventTags(evt['tags']).e_tags) > offset]

        # create lookup of events we have
        evts_lookup = {evt['id']: evt for evt in evts}

        # embed reply events if we already have them and not missing ids for store q
        missing_ids = []
        missing_map = {}
        for c_evt in reply_events:
            c_evt['reply_events'] = []

            # TODO: remove max_reply, would it ever make sense to reply ti more than one event?!
            for r_evt_id in EventTags(c_evt['tags']).e_tags[offset:offset+max_reply]:
                if r_evt_id in evts_lookup:
                    c_evt['reply_events'].append(evts_lookup[r_evt_id])
                else:
                    if r_evt_id not in missing_map:
                        # do we really want to support multi to 1 ?
                        missing_map[r_evt_id] = []
                        missing_ids.append(r_evt_id)
                    missing_map[r_evt_id].append(c_evt)
                    c_evt['reply_events'] = []

        # ok see if we can find any of those missing events.. thats is replies to events that
        # are not in evts (not unexpected)
        if missing_ids:
            m_evts = self.get_events_by_ids(missing_ids)

            # lookup by id of events we found
            m_evts_lookup = {evt['id']: evt for evt in m_evts}
            for m_id in missing_ids:
                # found
                if m_id in m_evts_lookup:
                    for c_evt in missing_map[m_id]:
                        c_evt['reply_events'].append(m_evts_lookup[m_id])
                # not in our store
                else:
                    for c_evt in missing_map[m_id]:
                        c_evt['reply_events'].append({
                            'id': m_id,
                            'sig': None,
                            'pubkey': '?',
                            'kind': Event.KIND_TEXT_NOTE,
                            'content': 'unable to find reply to event id: %s' % m_id,
                            'tags': [],
                            'created_at': 0
                        })

        return evts

    @property
    def store(self):
        return self._store


class NetworkedEventHandler(EventHandler):

    def __init__(self,
                 store: ClientEventStoreInterface,
                 client: Client,
                 max_insert_batch=500,
                 spam_handler: SpamHandlerInterface = None,
                 settings: Settings = None,
                 on_fetch=None):
        self._client = client
        self._query_cache = OrderedDict()
        self._max_query_cache = 100
        self._settings = settings
        self._on_fetch = on_fetch
        self._timeout = 5

        super().__init__(store=store,
                         max_insert_batch=max_insert_batch,
                         spam_handler=spam_handler)

    def fetch_events(self, filter):
        """
        :param filter: nostr filter
        :return: [Event] events fecthed from relays

        we have a cache of str(filter) of queries that we have done before and if we find in here then our
        local db should be uptodate there just isnt enough events that pass the filter to hit the limit.
        cache is queued in ordered dict and when we hit the max the oldest q is removed... Thats ok as there
        shouldn't be a problem refetching from relays except the time cost.
        It'd be better if we had the qs kept by last access in future.
        Note we don't just put a lru cache on the method as that'll cause problems with events that may have been
        deleted.
        TODO: there's probably more to look into here and we'll need to go through carefully how we deal with deletes
         esp if we end up connecting to relay that doesn't honour them...

        """
        query_key = json.dumps(filter)

        # we've already run this query which means our local db should be up to date
        if query_key in self._query_cache:
            return []

        ret = {}
        complete = False

        def _do_event(the_client: Client, sub_id: str, evts):
            nonlocal ret
            relay = the_client.url
            ret[relay] = [c_evt.event_data() for c_evt in evts]
            c_evt: Event
            self.do_event(sub_id, evts, relay)
            if self._on_fetch:
                self._on_fetch(evts)

        def _complete():
            nonlocal complete
            complete = True

        self._client.query(filter, _do_event,
                           timeout=self._timeout,
                           emulate_single=False,
                           on_complete=_complete)

        while complete is False or len(ret)==0:
            time.sleep(0.1)

        # add key to cache so we qon't requery
        self._query_cache[query_key] = True
        if len(self._query_cache) >= self._max_query_cache:
            self._query_cache.popitem(last=False)

        return Event.merge(*ret.values())

    @lru_cache(maxsize=100)
    def _get_events_by_ids(self, ids):
        evts = super()._get_events_by_ids(ids)
        ids = json.loads(ids)
        if len(evts) != len(ids):
            got_ids = {c_evt['id'] for c_evt in evts}
            still_needed = [c_id for c_id in ids if c_id not in got_ids]

            # might not actually be any required, duplicates in ids
            if still_needed:
                fetched = self.fetch_events({
                    'ids': still_needed
                })

                evts = Event.merge(evts, fetched)
                Event.sort(evts, inplace=True)

        return evts

    def _fetch_required(self, events, filter, limit) -> bool:
        """
        should we go to the network to fetch more events?! hopefully we can reduce fetch to relays as much as possible
        :param events:
        :param filter:
        :return:
        """

        # if filters always as for ids, #e then we can put a max time that we need to be able to look back
        # most likely looking at event/event thread
        def _can_restrict_events():
            ret = True
            for c_f in filter:
                # sad
                if not '#e' in c_f and not 'ids' in c_f:
                    ret = False
                    break
            return ret

        def _get_min_until():
            c_evt: Event
            event_lookup = dict([(c_evt['id'], c_evt) for c_evt in events])
            r_evts = []
            ret = None
            try:
                for c_f in filter:
                    if 'ids' in c_f:
                        for c_id in c_f['ids']:
                            r_evts.append(event_lookup[c_id])
                    if '#e' in c_f:
                        for c_id in c_f['#e']:
                            r_evts.append(event_lookup[c_id])

                Event.sort(r_evts, inplace=True)
                # allow 2 hours out for clocks, maybe they'll
                ret = r_evts[0]['created_at'] - 60*60*2
            except KeyError as ke:
                pass

            return ret

        ret = False
        if limit and len(events) < limit:
            ret = True

            # set by event search, there are some queries we could pass on but for now we restrict to only local search
            if 'no-fetch' in filter[0]:
                ret = False

            # if filter is for names ids, we have all those ids and we have all those events
            # then as long as there create_at plus so wobble is in our backfill time
            # events that refer to them can be older than this date so we should have already fetched them if they
            # exist
            elif self._settings and _can_restrict_events():
                min_date = _get_min_until()
                backfill_until = util_funcs.date_as_ticks(datetime.now() -
                                                          timedelta(days=int(self._settings.get('backfill.until'))))

                if min_date and min_date > backfill_until:
                    ret = False

        return ret

    def get_events(self, filter,
                   use_profile: Profile = None,
                   embed_reactions=True,
                   add_reactions_flag=True,
                   embed_replies=False) -> [Event]:
        c_evt: Event
        events = self._store.get_filter(filter)

        # normalise filter
        if isinstance(filter, dict):
            filter = [filter]

        # if there is a limit and we returned less than that then we'll have to go to the network
        # there maybe some optimisations we can do here to decide that we don't need to go to the network
        # even in case of <limit
        limit = None
        if 'limit' in filter[0]:
            limit = filter[0]['limit']

        if self._fetch_required(events, filter, limit):
            # stringify so it can be used as a cache key
            evts_from_network = self.fetch_events(filter)
            events = Event.merge(events, evts_from_network)[:limit]
            Event.sort(events, inplace=True)

        if embed_reactions:
            self.add_reaction_events(use_profile, events)
        # for reaction events the reacted to embed must have been embeded
        if add_reactions_flag and use_profile:
            events = self._add_reacted_to(use_profile, events)

        if embed_replies:
            # channels
            use_offset = 1
            if Event.KIND_ENCRYPT in filter[0]['kinds']:
                use_offset = 0

            self._add_reply_events(events, offset=use_offset)

        return events

