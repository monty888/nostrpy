from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass

import time
from nostr.event.event import Event
from nostr.util import util_funcs
from nostr.event.persist import ClientEventStoreInterface
from nostr.spam_handlers.spam_handlers import SpamHandlerInterface


class PersistEventHandler:
    """
        persists event we have seen to storage, profiles created/updated for meta_data type
        TODO: either add back in persist profile here or move to own handler
    """

    def __init__(self,
                 store: ClientEventStoreInterface,
                 max_insert_batch=500,
                 spam_handler: SpamHandlerInterface=None):
        self._store = store
        self._max_insert_batch = max_insert_batch
        self._spam_handler = spam_handler
        # to check if new or update profile
        # self._profiles = DataSet.from_sqlite(db_file,'select pub_k from profiles')

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
