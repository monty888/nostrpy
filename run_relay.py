"""
    run relay from the command line
    takes cmd line args or optionally config from TOML file at ~/.nostr/relay.toml
    (unless user gives another dir for file)

"""
import logging
import getopt
import sys
import os
import signal
from pathlib import Path
import toml
from toml import TomlDecodeError

from nostr.relay.relay import Relay
from nostr.relay.accepthandlers import LengthAcceptReqHandler
from nostr.relay.persist import SQLiteStore, MemoryStore, PostgresStore

# default values when nothing is specified either from cmd line or config file
HOST = 'localhost'
PORT = 8081
END_POINT = '/'
DEBUG_LEVEL = logging.DEBUG
DB_TYPE = 'sqlite'
# make this default home, wouldn't work on windows
WORK_DIR = '/home/%s/.nostrpy/' % Path.home().name
CONFIG_FILE = WORK_DIR + 'config.toml'
SQL_LITE_FILE = '%snostr-relay.db' % WORK_DIR
PG_USER = 'postgres'
PG_PASSWORD = 'password'
PG_DATBASE = 'nostr-relay'
MAX_SUB = 3
MAX_CONTENT_LENGTH = None

def usage():
    print("""
usage: python run_relay.py --host=localhost --port=8081

-h --help   -   show this message
-w --wipe   -   delete all data from db and exit
--config    -   config file if any
--host      -   host relay will listen websocket at, default %s
--port      -   port relay will listen websocket on, default %s
--endpoint  -   endpoint relay will listen websocket on, default %s
-s --store  -   storage type where relay will persist events etc. either sqllite, postgres or transient default %s
--dbfile    -   when --store is sqlite the db file for the database, default:
                %s
                when using dir .nostrpy dir it will be created if it doesn't exist already - other dirs wont and
                should be created manually. The dbfile will be created if it doesn't already exist.
--maxsub    -   maximum open subs allowed per client websocket, default %s
--maxlength -   maximum length for event content if any
  
    """ % (HOST, PORT, END_POINT, DB_TYPE, SQL_LITE_FILE, MAX_SUB))

def create_work_dir():
    if not os.path.isdir(WORK_DIR):
        logging.info('create_work_dir:: attempting to create %s' % WORK_DIR)
        os.makedirs(WORK_DIR)

def get_sql_store(filename):
    f = Path(filename)

    parent_dir = f.parts[len(f.parts)-2]

    # user must have given another dir, we better check it exists...
    if parent_dir != '.nostrpy':
        my_dir = Path(os.path.sep.join(f.parts[:-1]).replace(os.path.sep+os.path.sep, os.path.sep))
        if not my_dir.is_dir():
            print('sqllite dir not found %s' % my_dir)
            sys.exit(2)

    # if the file doesn't exist it'll be created and we'll create the db struct too
    # if it does we'll assume everything is ok...we could do more

    ret = SQLiteStore(filename)
    if not ret.exists():
        logging.info('get_sql_store::create new db %s' % filename)
        ret.create()
    else:
        logging.info('get_sql_store::open existing db %s' % filename)

    return ret


def get_postgres_store(db_name, user, password):
    ret = PostgresStore(db_name=db_name,
                        user=user,
                        password=password)

    if not ret.exists():
        ret.create()
    return ret



def load_toml(filename):
    ret = {}
    f = Path(filename)
    if f.is_file():
        try:
            ret = toml.load(filename)
        except TomlDecodeError as te:
            print('Error in config file %s - %s ' % (filename, te))
            sys.exit(2)

    else:
        logging.debug('load_toml:: no config file %s' % filename)
    return ret


def main():
    is_wipe = False
    create_work_dir()

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hs:w', ['help',
                                                          'host=',
                                                          'port=',
                                                          'endpoint=',
                                                          'config=',
                                                          'store=',
                                                          'dbfile=',
                                                          'maxsub=',
                                                          'maxlength=',
                                                          'wipe'])
    except getopt.GetoptError as e:
        print(e)
        usage()
        sys.exit(2)

    # get config file if any and debug, also we should get debug level here if any
    config_file = CONFIG_FILE
    for o,a in opts:
        if o == '--config':
            config_file = a

    # set logging level
    logging.getLogger().setLevel(logging.INFO)


    # default config
    use_max_length = MAX_CONTENT_LENGTH
    config = {
        'host': HOST,
        'port': PORT,
        'endpoint': END_POINT,
        'store': DB_TYPE,
        'dbfile': SQL_LITE_FILE,
        'maxsub': MAX_SUB,
        'maxlength': MAX_CONTENT_LENGTH,
        'pg_database': PG_DATBASE,
        'pg_user': PG_USER,
        'pg_password': PG_PASSWORD
    }
    config.update(load_toml(config_file))

    # do the rest of the passed in options, if defined will override defaults or from config file
    for o, a in opts:
        if o in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif o in ('-w','--wipe'):
            is_wipe = True
        elif o == '--host':
            config['host'] = a
        elif o == '--port':
            config['port'] = a
        elif o == '--endpoint':
            config['endpoint'] = a
            if config['endpoint'][0]!='/':
                config['endpoint'] = '/'+config['endpoint']
        elif o in ('-s', '--store'):
            config['store'] = a
        elif o == '--dbfile':
            config['dbfile'] = a
        elif o == '--maxsub':
            config['maxsub'] = a
        elif o == '--maxlength':
            config['maxlength'] = a

    # make sure items that need to be ints are
    for num_field in ('port', 'maxsub', 'maxlength'):
        try:
            if not config[num_field] is None:
                config[num_field] = int(config[num_field])
        except ValueError as e:
            print('--%s must be numeric' % num_field)
            sys.exit(2)

    # remove any items that don't apply, there not a problem but might confuse debug
    if config['store'] !='sqlite':
        del config['dbfile']
    if config['store'] !='postgres':
        del config['pg_database']
        del config['pg_user']
        del config['pg_password']

    # create storage object which is either to sqllite or posgres db
    if config['store'] == 'sqlite':
        my_store = get_sql_store(config['dbfile'])
    elif config['store'] == 'postgres':
        my_store = get_postgres_store(db_name=config['pg_database'],
                                      user=config['pg_user'],
                                      password=config['pg_password'])
    elif config['store'] == 'transient':
        my_store = MemoryStore()
    else:
        print('--store most be sqlite or postgres')
        sys.exit(2)

    if is_wipe:
        if config['store'] != 'transient':
            my_store.destroy()
        else:
            print('transient store, no action required!')
        sys.exit(0)

    # optional message accept handlers
    accept_handlers = []
    if config['maxlength']:
        accept_handlers.append(LengthAcceptReqHandler(max=config['maxlength']))

    for c_handler in accept_handlers:
        logging.info(c_handler)

    # now we have config run the relay
    config['pg_password'] = '***'
    logging.debug('config = %s' % config)
    my_relay = Relay(my_store, max_sub=config['maxsub'], accept_req_handler=accept_handlers)
    my_relay.start(config['host'], config['port'], config['endpoint'])

if __name__ == "__main__":

    def sigint_handler(signal, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    main()
