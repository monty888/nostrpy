"""
    nothing specific to races just methods to execute and query db
"""
import sqlite3
from sqlite3 import Error
from data.data import DataSet
import logging


class Database:

    def __init__(self, f_name):
        self._f_name = f_name

    def _get_con(self):
        return sqlite3.connect(self._f_name)

    def execute_sql(self, str, args=None, catch_err=False):
        """
            execute some SQL, currently we'll just fall over on
            errors
        """
        success = False
        if args is None:
            args = []

        # e only local
        was_err = None

        try:
            c = self._get_con()

            # if [[]] then we're doing a multi insert, not sure this is a perfect test...
            if args and isinstance(args[0], list):
                c.executemany(str, args)
            else:
                c.execute(str,args)
            c.commit()
            success = True
        except Error as e:
            logging.log(logging.WARN, e)
            was_err = e
        finally:
            if c:
                c.close()

        if not catch_err and was_err:
            raise was_err

        return success

    def executemany_sql(self, str, args=None, catch_err=False):
        """
            execute some SQL, currently we'll just fall over on
            errors
        """
        if args is None:
            args = []

        # e only local
        was_err = None

        try:
            c = self._get_con()
            c.executemany(str,args)
            c.commit()
        except Error as e:
            logging.log(logging.WARN, e)
            was_err = e
        finally:
            if c:
                c.close()

        if not catch_err and was_err:
            raise was_err

    def select_sql(self, sql, args=None)->DataSet:
        return DataSet.from_sqlite(self._f_name, sql, args)

    def _insert_tbl(self, t_name, data: DataSet):
        # nothing to insert
        if not data:
            return
        sql = 'insert into %s ' % t_name
        pcount = ['?'] * len(data.Heads)
        fields = '(%s) values (%s)' % (','.join(data.Heads),
                                       ','.join(pcount))


        self.execute_sql(sql+fields,data.Data)
