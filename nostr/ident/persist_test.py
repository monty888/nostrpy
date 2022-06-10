"""
    tests for the nostr.relay
"""
import unittest
import logging
import signal
import sys
from nostr.ident.persist import TransientProfileStore,ProfileType
from nostr.ident.profile import Profile
from nostr.encrypt import Keys


class ProfileStoreTestCase(unittest.TestCase):
    """
        only transient currently
    """
    def setUp(self) -> None:
        self._store = TransientProfileStore()

        # some profiles without priv keys
        for i in range(0, 5):
            k = Keys.get_new_key_pair()
            p = Profile(
                pub_k=k['pub_k'],
                attrs={
                    'name': 'test remote profile %s' % i
                }
            )
            self._store.add(p)

        # some profiles with priv keys (local)
        for i in range(0, 5):
            k = Keys.get_new_key_pair()

            p = Profile(
                pub_k=k['pub_k'],
                priv_k=k['priv_k'],
                attrs={
                    'name': 'test local profile %s' % i
                }
            )
            self._store.add(p)


    def tearDown(self) -> None:
        pass

    def test_select(self):
        assert len(self._store.select()) == 10


    def test_select_local(self):
        assert len(self._store.select(profile_type=ProfileType.LOCAL)) == 5


if __name__ == '__main__':
    # logging.getLogger().setLevel(logging.DEBUG)
    unittest.main()