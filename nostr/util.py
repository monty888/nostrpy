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

if __name__ == "__main__":

    print(util_funcs.date_as_ticks(datetime.now()))
    print(util_funcs.ticks_as_date(1645067085))
    print(util_funcs.ticks_as_date(1645049579))