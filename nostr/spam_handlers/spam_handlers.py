from abc import ABC, abstractmethod
from nostr.event.event import Event


class SpamHandlerInterface(ABC):

    @abstractmethod
    def is_spam(self, evt:Event):
        """
        :param evt:
        :return:
        """


class ContentBasedDespam(SpamHandlerInterface):
    """
        good enough for the time being but really need to take into context local profiles
        we can use followers, comunicated with as a way to rate
        also probably return a category e.g./ score

        spam,           100
        potential_spam  >50
        ok              <25     ??

        this we can the put onto events table, spam we probably we won't import or do anything with
        but potential spam might be imported but then deleted by a process after 24hours or something

    """
    def __init__(self):
        pass

    def is_spam(self, evt: Event):
        ret = False
        content = evt.content
        if evt.kind == Event.KIND_TEXT_NOTE:
            if content == '' or evt.content.startswith('{'):
                ret = True
            else:
                parts = content.split(' ')
                if len(parts) <= 1:
                    if len(parts[0]) > 20 and not parts[0].startswith('http'):
                        ret = True
        return ret
