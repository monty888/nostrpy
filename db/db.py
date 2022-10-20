"""
    Simple database access class
    probably we'll subclass where you just need to supply the getcon and __init__ methods
    this would allow easy swap of db

"""
import sqlite3
from threading import BoundedSemaphore
import time
from sqlite3 import Error
try:
    import psycopg2
except:
    pass
from data.data import DataSet
import logging
from abc import abstractmethod, ABC


class Database:

    @abstractmethod
    def execute_sql(self, sql, args=None):
        """
            execute some SQL, currently we'll just fall over on
            errors
        """

    @abstractmethod
    def executemany_sql(self, sql, args=None):
        """
            execute some SQL, returns True/False on success if catch_err is False
            then errors will raise an exception
        """

    @abstractmethod
    def execute_batch(self, batch):
        """
        :param batch: array of {
            'sql' : str,
            'args' : [] optional
        }
        :return: True on success
        """

    @abstractmethod
    def select_sql(self, sql, args=None) -> DataSet:
        """
        excutes query against database con
        :param sql: query str
        :param args: query args
        :return: results as DataSet
        """

    @property
    def placeholder(self):
        pass


class SQLiteDatabase(Database, ABC):

    def __init__(self, f_name):
        self._f_name = f_name
        # as SQLite locks the entire db at some point during any update we try and manage writes
        # so we block ourself and make it less likely to get db locked error...
        # of course if another instance is being used or another python the db could still end up locked and we'd fail
        # :(. We only put the locks around writes, reads will leave to fail for the caller to deal with...
        self._lock = BoundedSemaphore()

    def _get_con(self):
        return sqlite3.connect(self._f_name)

    @property
    def file(self):
        return self._f_name

    def execute_sql(self, sql, args=None, catch_err=False):
        """
            execute some SQL, currently we'll just fall over on
            errors
        """
        success = False
        if args is None:
            args = []

        # e only local
        was_err = None

        with self._lock:
            try:
                c = self._get_con()
                logging.debug('Database::execute_batch SQL: %s\n ARGS: %s' % (sql,
                                                                              args))
                # replace to ? as used by sql_lite
                sql = sql.replace(':?', self.placeholder)
                # if [[]] then we're doing a multi insert, not sure this is a perfect test...
                if args and isinstance(args[0], list):
                    c.executemany(sql, args)
                else:
                    c.execute(sql,args)
                c.commit()
                success = True
            except Error as e:
                logging.debug('Database::execute_sql error %s' % e)
                was_err = e
            finally:
                if c:
                    c.close()

        if not catch_err and was_err:
            raise was_err

        return success

    def executemany_sql(self, sql, args=None, catch_err=False):
        """
            execute some SQL, returns True/False on success if catch_err is False
            then errors will raise an exception
        """
        ret = False
        if args is None:
            args = []

        # e only local
        was_err = None
        with self._lock:
            try:
                c = self._get_con()
                c.executemany(sql,args)
                c.commit()
                ret = True
            except Error as e:
                logging.debug('Database::executemany_sql error %s' % e)
                was_err = e
            finally:
                if c:
                    c.close()

        if not catch_err and was_err:
            raise was_err

        return ret

    def execute_batch(self, batch, catch_err=False):
        """
        :param batch: array of {
            'sql' : str,
            'args' : [] optional
        }
        :return: True on success
        """
        ret = False
        was_err = None
        c = None
        with self._lock:
            try:
                c = self._get_con()
                curs = c.cursor()
                curs.execute('begin')
                for c_cmd in batch:
                    args = []
                    sql = c_cmd['sql']
                    if 'args' in c_cmd:
                        args = c_cmd['args']
                    logging.debug('Database::execute_batch SQL: %s\n ARGS: %s' % (sql,
                                                                                  args))
                    # as execute_sql to do multiple row insert if [[]]
                    if args and isinstance(args[0], list):
                        curs.executemany(sql, args)
                    else:
                        curs.execute(sql, args)


                c.commit()
                logging.debug('Database::execute_batch commit done')
                ret = True
            except Error as e:
                was_err = e
                logging.debug('Database::execute_batch error - not committed %s' % e)

            finally:
                if c:
                    c.close()

        if not catch_err and was_err:
            raise was_err

        return ret

    def select_sql(self, sql, args=None) -> DataSet:
        """
        excutes query against database con
        :param sql: query str
        :param args: query args
        :return: results as DataSet
        """
        logging.debug('Database::select_sql - SQL: %s \n ARGS: %s' % (sql,args))

        if args is None:
            args = []

        # replace to ? as used by sql_lite
        sql = sql.replace(':?', self.placeholder)

        # create con
        con = self._get_con()

        # get result set of query
        rs = con.execute(sql, args)

        # extract the heads
        heads = []
        for c_h in rs.description:
            # col name in 0 the rest are always None and contain no useful info for us
            heads.append(c_h[0])

        # now extract the data
        data = []
        for c_r in rs:
            # we change to [] as there are some places where being a turple will be a problem
            data.append(list(c_r))

        # clean up, not sure require to close rs if closing con
        # but what the hell
        rs.close()
        con.close()
        # now return as a dataset
        return DataSet(heads, data)

    def _insert_tbl(self, t_name, data: DataSet):
        # nothing to insert
        if not data:
            return
        sql = 'insert into %s ' % t_name
        pcount = ['?'] * len(data.Heads)
        fields = '(%s) values (%s)' % (','.join(data.Heads),
                                       ','.join(pcount))

        self.execute_sql(sql+fields,data.Data)

    @property
    def placeholder(self):
        return '?'


class PostgresDatabase(Database, ABC):
    """
        Same for Postgres using psycopg2
        unfortunetly  psycopg2 and sqlite3 cons so for now have just re-implemented the same methods


    """
    def __init__(self, db_name, user, password):
        self._name = db_name
        self._user = user
        self._password = password

    def _get_con(self):
        return psycopg2.connect("dbname=%s user=%s password=%s" % (self._name,
                                                                   self._user,
                                                                   self._password))

    def execute_sql(self, sql, args=None):
        with self._get_con() as c:
            with c.cursor() as cur:
                logging.debug('Database::execute_batch SQL: %s\n ARGS: %s' % (sql,
                                                                              args))
                cur.execute(sql, args)
                c.commit()

    def executemany_sql(self, sql, args=None):
        raise Exception('not implemented!')

    def execute_batch(self, batch):
        with self._get_con() as c:
            with c.cursor() as cur:
                for c_cmd in batch:
                    args = []
                    sql = c_cmd['sql']
                    if 'args' in c_cmd:
                        args = c_cmd['args']
                    logging.debug('Database::execute_batch SQL: %s\n ARGS: %s' % (sql,
                                                                                  args))
                    cur.execute(sql, args)

                c.commit()

    def select_sql(self, sql, args=None) -> DataSet:
        with self._get_con() as c:
            with c.cursor() as cur:
                cur.execute(sql, args)
                # get heads
                heads = [h.name for h in cur.description]

                # and data
                rows = cur.fetchall()
                data = []
                for c_r in rows:
                    data.append(list(c_r))

        return DataSet(heads, data)

    @property
    def placeholder(self):
        return '%s'


class QueryFromFilter:
    OR_JOIN = 'OR'
    AND_JOIN = 'AND'

    def __init__(self, select_sql:str, filter={}, placeholder='?', alias={}, def_join='OR'):
        self._sql_base = select_sql
        self._filter = filter
        if isinstance(self._filter,dict):
            self._filter = [self._filter]
        self._placeholder = placeholder
        self._alias = alias
        self._join = ' where '
        if ' where ' in select_sql:
            self._join = ' or '

        self._def_join = def_join


    def _construct(self):

        sql_arr = [self._sql_base]
        args = []

        def _add_filter(c_filter):
            opened = False
            for k in c_filter:
                if not opened:
                    sql_arr.append(self._join)
                    sql_arr.append(' (')
                    opened = True
                _add_for_field(c_filter, k)

            if opened:
                sql_arr.append(') ')
                self._join = self._def_join

        def _add_for_field(c_filter, f_name):
            nonlocal args

            values = c_filter[f_name]
            db_field = f_name
            if f_name in self._alias:
                db_field = self._alias[db_field]

            if not hasattr(values, '__iter__') or isinstance(values, str):
                values = [values]

            sql_arr.append(
                ' %s in (%s) ' % (db_field,
                                     ','.join([self._placeholder] * len(values)))
            )

            args = args + values

        for f in self._filter:
            if isinstance(f, dict):
                _add_filter(f)
            if isinstance(f, str):
                self._join = ' %s ' % f

        return {
            'sql': ''.join(sql_arr),
            'args': args,
            'join': self._join
        }

    def get_query(self):
        return self._construct()







