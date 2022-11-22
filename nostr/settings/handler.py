from abc import ABC
from .persist import SettingStoreInterface
from threading import BoundedSemaphore


class Settings(SettingStoreInterface, ABC):
    """
        caches locally for reads everything else is just as the given settings store
    """
    def __init__(self, settings_store: SettingStoreInterface):
        self._store = settings_store
        self._lock = BoundedSemaphore()
        self._lookup = None
        self._load()

    def _load(self):
        with self._lock:
            self._lookup = {}
            for r in self._store.list():
                self._lookup[r['name']] = r['value']

    def get(self, key, default=None, recurse=False):
        ret = default
        if key in self._lookup:
            ret = self._lookup[key]
        elif recurse:
            pass
        return ret

    def put(self, key, value):
        self._store.put(key, value)
        self._load()

    def delete(self, key):
        self._store.delete(key)
        self._load()

    def list(self, keys=None, exact=True):
        return self._store.list(keys=keys,
                                exact=exact)



