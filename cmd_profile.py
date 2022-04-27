"""
    create/link profile_name, private key to
"""

import logging
import sys
from pathlib import Path
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile
from nostr.ident.persist import SQLProfileStore
from nostr.util import util_funcs

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
PROFILE_STORE = SQLProfileStore(DB)

def usage():
    print("""
usage:

    python cmd_profile.py -n <profile_name>, creates a new profile - key pair is auto generated.
    fails if profile_name already exits

    python cmd_profile.py -n <profile_name>, <private_key> create new profile with supplied private key
    fails if either profile_name or private_key already exits

    python cmd_profile.py -l <private_key> <profile_name>, link to existing profile - seen via META event
    
    python cmd_profile.py -i <file_name>
    profile_name/private_key that already exist will be skipped
    
 
    """)
    sys.exit(2)


def create_new(args):
    if len(args) < 1:
        usage()

    profile_name = args[0]
    priv_key = None
    if len(args)>1:
        priv_key = args[1]
        if not util_funcs.is_nostr_key(priv_key):
            print('%s - doesn\'t look like a nostr private key - should be 64 char hex' % priv_key)
            sys.exit(2)

        priv_key = bytes(bytearray.fromhex(priv_key))

    print('creating new profile %s' % profile_name)

    # NOTE, this will error if either the profile_name or if given, private_key already exists
    new_p = PROFILE_STORE.new_profile(profile_name,
                                      priv_key=priv_key)

    print('created new profile %s ' % new_p.display_name())


def load_file(args):
    if len(args) != 1:
        print('requires filename for csv profile file to import from')
        sys.exit(2)

    file_name = args[0]
    # TODO: add support to get names to import
    PROFILE_STORE.import_file(file_name)

    print('load file %s' % file_name)

def save_file(args):
    if len(args) != 1:
        print('requires filename for csv profile file to output to')
        sys.exit(2)
    file_name = args[0]
    PROFILE_STORE.export_file(file_name)

def link_profile(args):
    if len(args) != 2:
        print("""
--link require 2 params <profile_name> <private_key>  
            
            
        """)
        sys.exit(2)

    profile_name = args[0]
    priv_key = args[1]
    if not util_funcs.is_nostr_key(priv_key):
        print('%s - doesn\'t look like a nostr private key - should be 64 char hex' % priv_key)
        sys.exit(2)

    p = Profile(priv_key,
                profile_name=profile_name)

    profiles = PROFILE_STORE.select()
    if profiles.lookup_profilename(profile_name):
        print('profile with name %s already exists' % profile_name)
        sys.exit(2)

    update_p = profiles.lookup_pub_key(p.public_key)
    if not update_p:
        print('no profile with matching public key - %s exists to link to' % p.public_key)
        sys.exit(2)
    if update_p.profile_name:
        print('%s already has profile name, changing from %s to %s ' % (priv_key,
                                                                        profile_name,
                                                                        update_p.profile_name))

    update_p.profile_name = profile_name
    update_p.private_key = priv_key
    PROFILE_STORE.update_profile_local(update_p)

def profile_edit():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hnlix', ['help',
                                                           'new',
                                                           'link',
                                                           'import',
                                                           'export'])

        # an option is required
        if len(opts) == 0:
            usage()

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            elif o in ('-n', '--new'):
                create_new(args)
            elif o in ('-i','--import'):
                load_file(args)
            elif o in ('-x','--export'):
                save_file(args)
            elif o in ('-l','--link'):
                link_profile(args)

    except getopt.GetoptError as e:
        print(e)
        usage()



if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    profile_edit()
