import sys
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
from db.db import SQLiteDatabase

"""
    just a place to hand any util funcs that don't easily fit anywhere else
"""
class util_funcs:

    @staticmethod
    def ticks_as_date(ticks):
        return datetime.fromtimestamp(ticks)
    # reverse of above
    @staticmethod
    def date_as_ticks(dt: datetime):
        return int(dt.timestamp())

    @staticmethod
    def chunk(arr, chunk_size):
        if not hasattr(arr, '__iter__'):
            arr = [arr]

        if chunk_size is not None:
            ret = [arr[i:i + chunk_size] for i in range(0, len(arr), chunk_size)]
        else:
            ret = [arr]

        return ret

    @staticmethod
    def str_tails(the_str, taillen=4):
        # returns str start...end chars for taillen
        ret = '?...?'

        if the_str:
            if len(the_str) < (taillen*2)+3:
                ret = the_str
            else:
                ret = '%s...%s' % (the_str[:taillen], the_str[len(the_str)-taillen:])
        return ret

    @staticmethod
    def create_work_dir(top_dir, sub_dir=None):
        def fix_path_str(the_str):
            return the_str.replace(os.path.sep + os.path.sep, os.path.sep)

        f = Path(top_dir)
        the_top_dir = Path(fix_path_str(os.path.sep.join(f.parts)))

        if not the_top_dir.is_dir():
            parent_dir = Path(os.path.sep.join(f.parts[:-1]).replace(os.path.sep + os.path.sep, os.path.sep))

            # we'll only create the top dir so if the containing dir does't exist then error
            if not parent_dir.is_dir():
                print('no such directory %s to create nostrpy work directory %s in ' % (parent_dir, the_top_dir))
                sys.exit(os.EX_CANTCREAT)

            # make the directory
            logging.info('util_funcs::create_work_dir: attempting to create %s' % the_top_dir)
            try:
                os.makedirs(the_top_dir)
            except PermissionError as pe:
                print('error trying to create work director %s - %s' % (parent_dir, pe))
                sys.exit(os.EX_CANTCREAT)

        # is there a sub dir, check it exists and create if not
        if sub_dir is not None:
            the_sub_dir = Path(fix_path_str(os.path.sep.join(f.parts)+ os.path.sep + sub_dir))
            if not the_sub_dir.is_dir():
                try:
                    os.makedirs(the_sub_dir)
                except PermissionError as pe:
                    print('error trying to create work sub director %s - %s' % (the_sub_dir, pe))
                    sys.exit(os.EX_CANTCREAT)

    @staticmethod
    def create_sqlite_store(db_file):
        from nostr.event.persist import ClientSQLiteEventStore
        from nostr.ident.persist import SQLiteProfileStore

        my_events = ClientSQLiteEventStore(db_file)
        if not my_events.exists():
            my_events.create()
            my_profiles = SQLiteProfileStore(db_file)
            my_profiles.create()

        return SQLiteDatabase(db_file)

if __name__ == "__main__":
    print('monkies')