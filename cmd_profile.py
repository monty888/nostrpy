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

# TODO: also postgres
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
DB = SQLiteDatabase('%s/nostr-client.db' % WORK_DIR)
PROFILE_STORE = SQLProfileStore(DB)

def usage():
    print("""
usage:

    python cmd_profile.py -n <profile_name>, creates a new profile key pair is auto generated.
    
    python cmd_profile.py -n <private_key> <profile_name>, create new profile with supplied priv_key

    python cmd_profile.py -l <private_key> <profile_name>, link to existing profile - seen via META event
    
    python cmd_profile.py -f <file_name>
    
    write this bluurg when we actually know what all the cmds do!!!!
 
    """)
    sys.exit(2)


def create_new(args):
    if len(args) != 1:
        usage()

    profile_name = args[0]

    print('creating new profile %s' % profile_name)
    new_p = PROFILE_STORE.new_profile(profile_name)

    print('created new profile %s ' % new_p.display_name())


def load_file(args):
    if len(args) != 1:
        print('requires filename for csv profile file')
        sys.exit(2)

    file_name = args[0]
    # TODO: add support to get names to import
    PROFILE_STORE.import_from_file(file_name)

    print('load file %s' % file_name)

def link_profile(args):
    if len(args) != 2:
        print("""
            profile link require 2 params  
            
            
        """)
        sys.exit(2)


def profile_edit():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hnlf', ['help',
                                                          'new',
                                                          'link',
                                                          'file'])

        # no args or options
        if len(args) == 0 and len(opts) == 0:
            usage()

        # attempt interpret action
        for o, a in opts:
            if o in ('-h', '--help'):
                usage()
            elif o in ('-n', '--new'):
                create_new(args)
            elif o in ('-f','--file'):
                load_file(args)
            elif o in ('-l','--link'):
                link_profile(args)

    except getopt.GetoptError as e:
        print(e)
        usage()



if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    profile_edit()
