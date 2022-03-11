"""
    EventHandlers for Client subscribe method, there should be a do_event(evt, relay) which should be passed as the
    handler arg when calling the subscribe method. Eventually support mutiple handlers per sub and add.remove handlers
    plus maybe chain of handlers

"""
import base64
import logging
import json
from nostr.persist import Store
from nostr.encrypt import SharedEncrypt
from nostr.util import util_funcs


class PrintEventHandler:
    """
        Basic handler that just prints to screen any events it sees.
        Can be turned off by calling view_off

        TODO: add kinds filter, default NOTE and ENCRYPT only
    """

    def __init__(self, view_on=True):
        self._view_on = view_on

    def view_on(self):
        self._view_on = True

    def view_off(self):
        self._view_on = False

    def do_event(self, evt, relay):
        if self._view_on:
            pubkey = evt['pubkey']
            pubkey = '%s...%s' % (pubkey[:4],
                                  pubkey[len(pubkey)-4:])

            print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                                   pubkey,
                                   evt['content']))


class DecryptPrintEventHandler(PrintEventHandler):
    """
        prints out decrypted messages we created or sent to us
        NOTE: this is not the style that is compatiable with clust, that uses a public inbox
        and encrypts the event as a package... want to add this too
    """

    def __init__(self, priv_k, view_on=True):
        self._priv_k = priv_k
        self._my_encrypt = SharedEncrypt(priv_k)
        super(DecryptPrintEventHandler, self).__init__(view_on)

    def _do_dycrypt(self, crypt_text, pub_key):
        msg_split = crypt_text.split('?iv')
        text = base64.b64decode(msg_split[0])
        iv = base64.b64decode(msg_split[1])

        return (self._my_encrypt.decrypt_message(encrypted_data=text,
                                                 iv=iv,
                                                 # note the ext is ignored anyway
                                                 pub_key_hex='02' + pub_key))

    def do_event(self, evt, relay):
        if self._view_on is False:
            return
        do_decrypt = False
        to_key = evt['tags'][0][1]
        print(to_key, self._my_encrypt.public_key_hex)
        if evt['kind'] == Event.KIND_ENCRYPT:
            # messages we created
            if evt['pubkey'] == self._my_encrypt.public_key_hex[2:]:
                pub_key = to_key
                do_decrypt = True

            # messages sent to us
            elif to_key == self._my_encrypt.public_key_hex[2:]:
                pub_key = evt['pubkey']
                do_decrypt = True

        content = evt['content']
        if do_decrypt:
            content = self._do_dycrypt(evt['content'], pub_key)

        print('%s: %s - %s' % (util_funcs.ticks_as_date(evt['created_at']),
                               evt['pubkey'],
                               content))


class FileEventHandler:

    def __init__(self, file_name, delete_exist=True):
        self._file_name = file_name
        if delete_exist:
            with open(self._file_name, 'w'):
                pass

    def do_event(self, evt, relay):
        # appends to
        with open(self._file_name, "a") as f:
            evt['pubkey'] = evt['pubkey']
            f.writelines(json.dumps(evt) + '\n')
        logging.debug('FileEventHandler::do_event event appended to file %s' % self._file_name)


class EventTimeHandler:

    def __init__(self, callback=None):
        self._callback = callback

    def do_event(self, evt, relay):
        self._callback(evt['created_at'])


class PersistEventHandler:
    """
        persists event we have seen to storage, profiles created/updated for meta_data type
        TODO: either add back in persist profile here or move to own handler
    """

    def __init__(self, db_file):
        self._store = Store(db_file)
        # to check if new or update profile
        # self._profiles = DataSet.from_sqlite(db_file,'select pub_k from profiles')

    def do_event(self, evt, relay):

        # store the actual event
        try:
            self._store.add_event(evt, relay)
        except:
            # most likely because we already have, we could though add a table that
            # linking evets with every relay we saw them from
            pass

        # pubkey = evt['pubkey']
        #
        # # if meta then add/update profile as required
        # if evt['kind'] == Event.KIND_META:
        #     c_profile = self._profiles.value_in('pub_k',pubkey)
        #     if c_profile:
        #         my_store.update_profile(c_profile)
        #     else:
        #         c_profile = Profile(pub_k=pubkey,attrs=evt['content'],update_at=evt['created_at'])
        #         my_store.add_profile(c_profile)
        #
        #     # for now we just reload the whole lot from db rather then just updating what we have
        #     profiles = ProfileList.create_others_profiles_from_db(db_file)