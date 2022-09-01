"""
    create/link profile_name, private key to
"""

import logging
import sys
from pathlib import Path
import getopt
from db.db import SQLiteDatabase
from nostr.ident.profile import Profile
from nostr.ident.persist import SQLProfileStore, ProfileStoreInterface, ProfileType
from nostr.encrypt import Keys

# TODO: also postgres
WORK_DIR = '%s/.nostrpy/' % Path.home()
DB_FILE = 'nostr-client.db'

def usage():
    print("""
usage:

    python cmd_profile.py -n <profile_name> creates a new profile - key pair is auto generated.
    fails if profile_name already exits

    python cmd_profile.py -n <profile_name> <private_key> - create new profile with supplied private key
    fails if either profile_name or private_key already exits

    python cmd_profile.py -l <profile_name> <private_key> - link to existing profile - seen via META event
    
    python cmd_profile.py -i <file_name>
    profile_name/private_key that already exist will be skipped
    
    python cmd_profile.py -x <file_name>
    write profiles to csv file
    
    python cmd_profile.py -v 
    prints out profiles that have private keys in the current db
 
    """)
    sys.exit(2)


def create_new(args, profile_store:ProfileStoreInterface):
    if len(args) < 1:
        usage()

    profile_name = args[0]
    priv_key = None
    if len(args)>1:
        priv_key = args[1]
        if not Keys.is_key(priv_key):
            print('%s - doesn\'t look like a nostr private key - should be 64 char hex' % priv_key)
            sys.exit(2)

        # priv_key = bytes(bytearray.fromhex(priv_key))

    print('creating new profile %s' % profile_name)

    # NOTE, this will error if either the profile_name or if given, private_key already exists
    new_p = profile_store.new_profile(profile_name,
                                      priv_key=priv_key)

    print('created new profile %s ' % new_p.display_name())


def load_file(args, profile_store:ProfileStoreInterface):
    if len(args) != 1:
        print('requires filename for csv profile file to import from')
        sys.exit(2)

    file_name = args[0]
    # TODO: add support to get names to import
    print('load file %s' % file_name)
    result = profile_store.import_file(file_name)
    print('--Added--')
    c_p: Profile
    for c_p in result['added']:
        print(c_p.display_name())

    # already existing are updated, this only changes the link to profile name, attrs will stay as they are
    # this will work most of the time but doesn't cover e.g. the profile name exists and is used for another key
    profiles = profile_store.select_profiles()
    if result['existed']:
        print('--Existed updated--')
        for c_p in result['existed']:
            is_change = 'no change'
            if not profiles.lookup_profilename(c_p.profile_name):
                is_change = 'updated'
                profile_store.put_profile(c_p, is_local=True)

            print('%s, %s' % (c_p.display_name(), is_change))


def save_file(args, profile_store:ProfileStoreInterface):
    if len(args) != 1:
        print('requires filename for csv profile file to output to')
        sys.exit(2)
    file_name = args[0]
    profile_store.export_file(file_name)

def link_profile(args, profile_store:ProfileStoreInterface):
    if len(args) != 2:
        print("""
--link require 2 params <profile_name> <private_key>  
            
            
        """)
        sys.exit(2)

    profile_name = args[0]
    priv_key = args[1]

    if not Keys.is_key(priv_key):
        print('%s - doesn\'t look like a nostr private key - should be 64 char hex' % priv_key)
        sys.exit(2)

    p = Profile(priv_key,
                profile_name=profile_name)

    profiles = profile_store.select_profiles()
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
    profile_store.put_profile(update_p, is_local=True)
    print('link done %s', profile_name)


def view_profiles(profile_store:ProfileStoreInterface):
    profiles = profile_store.select_profiles(profile_type=ProfileType.LOCAL)
    c_p: Profile

    for c_p in profiles:
        name = c_p.name
        if name is None:
            name = '-'
        print('%s %s [%s]' % (c_p.public_key, name[:15].ljust(15), c_p.profile_name[:20].ljust(20)))

def profile_edit():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hnlixv', ['help',
                                                            'new',
                                                            'link',
                                                            'import',
                                                            'export',
                                                            'view',
                                                            'dbfile='])

        # default db
        db_file = WORK_DIR + DB_FILE

        # an option is required
        if len(opts) == 0:
            usage()

        for o, a in opts:
            if o == '--dbfile':
                db_file = WORK_DIR + a

        # only doing sqlite dbs currently, no point mem stores, postgres in future
        print('working on sqlite db_file: %s' % db_file)
        profile_store = SQLProfileStore(SQLiteDatabase(db_file))

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            elif o in ('-n', '--new'):
                create_new(args, profile_store)
                sys.exit(0)
            elif o in ('-i', '--import'):
                load_file(args, profile_store)
                sys.exit(0)
            elif o in ('-x', '--export'):
                save_file(args, profile_store)
                sys.exit(0)
            elif o in ('-l', '--link'):
                link_profile(args, profile_store)
                sys.exit(0)
            elif o in ('-v', '--view'):
                view_profiles(profile_store)
                sys.exit(0)
        usage()

    except getopt.GetoptError as e:
        print(e)
        usage()

def test_store():
    pass


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    profile_edit()
