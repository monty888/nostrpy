from abc import ABC, abstractmethod
from db.db import SQLiteDatabase


class SettingStoreInterface(ABC):

    @abstractmethod
    def get(self, key, default=None,  recurse=False):
        """
        :param key:
        :param recurse:
        :param default:
        :return:
        """

    @abstractmethod
    def put(self, key, value):
        """
        :param key:
        :param value:
        :return:
        """

    @abstractmethod
    def delete(self, key):
        """
        :param key:
        :return:
        """

    @abstractmethod
    def list(self, keys=None, exact=True):
        """
        :param keys:
        :return:
        """


class SQLSettingsStore(SettingStoreInterface):

    def __init__(self, db):
        self._db = db

    def get(self, key, default=None, recurse=False):
        ret = default
        sql = 'select value from settings where name=%s' % self._db.placeholder
        args = [key]
        rs = self._db.select_sql(sql=sql,
                                 args=args)
        if rs:
            ret = rs[0]
        return ret

    def put(self, key, value):
        sql = 'insert or replace into settings values(%s, %s)' % (self._db.placeholder,
                                                                  self._db.placeholder)
        args = [key, value]
        return self._db.execute_sql(sql=sql,
                                    args=args)

    def delete(self, key):
        sql = 'delete from settings where name=%s' % self._db.placeholder
        args = [key]
        return self._db.execute_sql(sql=sql,
                                    args=args)

    def list(self, keys=None, exact=True):
        if not keys:
            sql = 'select name,value from settings'
            args = []
        else:
            if isinstance(keys, str):
                keys = [keys]

            if exact:
                sql = 'select name, value from settings where name in (%s)' % ','.join(([self._db.placeholder]*len(keys)))
                args = keys
            else:
                args = [v+'%' for v in keys]
                sql = 'select name, value from settings where name like %s ' % self._db.placeholder
                sql = sql + ''.join([('or name like '+self._db.placeholder)] * (len(keys)-1))

        return self._db.select_sql(sql=sql,
                                   args=args)


class SQLiteSettingsStore(SQLSettingsStore):

    def __init__(self, db_file):
        self._db_file = db_file
        super(SQLiteSettingsStore, self).__init__(SQLiteDatabase(db_file))

    def create(self):
        sql = """
        CREATE TABLE if not exists "settings" (
            "name"	TEXT UNIQUE,
            "value"	TEXT
        );
        """
        return self._db.execute_sql(sql)
