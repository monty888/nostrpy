from datetime import datetime, timedelta
"""
    just a place to hand any util funcs that don't easily fit anywhere else
"""


class util_funcs:

    @classmethod
    def ticks_as_date(cls, ticks):
        return datetime.fromtimestamp(ticks)
    # reverse of above
    @classmethod
    def date_as_ticks(cls, dt: datetime):
        return int(dt.timestamp())

    @classmethod
    def str_tails(cls, the_str, taillen=4):
        # returns str start...end chars for taillen
        ret = '?...?'
        if the_str:
            ret = '%s...%s' % (the_str[:taillen], the_str[len(the_str)-taillen:])
        return ret

    def sql_lite_destroy(self, db_file, export_profiles=None):
        """
            completely removes the sql_lite db that we're currently using for our nostr client
            if supplied export_profiles is filename to export profiles that we use - This are the ones that
            we have priv keys for
        """
        pass
    def sql_lite_create(self, db_file, import_profiles=None):
        """
            creates empty db for use by our nostr client
            import profiles is filename of previously exported profiles to impotr on create
        """
        pass


if __name__ == "__main__":
    print('monkies')