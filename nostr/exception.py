
class NostrCommandException(Exception):

    @classmethod
    def event_already_exists(cls, id):
        return NostrCommandException('event already exists %s' % id)

    # define elsewhere so easier to import...
    pass