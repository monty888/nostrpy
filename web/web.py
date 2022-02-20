import bottle
from bottle import request, Bottle, static_file,route
import logging
import json
from nostr.ident import ProfileList
from data.data import DataSet
from io import BytesIO
import base64

class StaticServer():
    """
        simple server that just deals with the static data html,js, css...
    """
    def __init__(self, file_root):
        self._app = Bottle()
        self._file_root = file_root+'/'


        """
            basically or statics are the same just ext and name of sub dir and the route text that changes
            so each call this to get the method that'll be called by their route that defines sub_dir and ext for that 
            files type
        """
        def get_for_ftype(sub_dir, ext=None):
            # where not defined so e.g. sub_dir == /css and file ext == .css
            if ext is None:
                ext = sub_dir

            def for_type(name):
                my_root = self._file_root + '%s/' % sub_dir
                logging.debug('StaticServer:: root: %s sub_dir: %s name: %s ext: %s' % (self._file_root,
                                                                                        sub_dir,
                                                                                        name,
                                                                                        ext))

                # if ext not already included then we'll add it
                if not ('.%s' % ext) in name:
                    name = name + '.%s' % ext
                print(name, my_root)
                return static_file(filename=name, root=my_root)
            return for_type

        # html
        html_method = get_for_ftype('html')
        @self._app.route('/html/<name>')
        def html(name):
            return html_method(name)

        # js
        js_method = get_for_ftype('script','js')
        @self._app.route('/script/<name>')
        def js(name):
            return js_method(name)

        # css
        css_method = get_for_ftype('css','css')
        @self._app.route('/css/<name>')
        def css(name):
            return css_method(name)

        @self._app.route('/fonts/<name>')
        def font(name):
            accept = set(['woff2','woff','ttf','svg'])
            splits = name.split('.')
            font_dir = self._file_root + 'fonts/'
            if len(splits)>1 and splits[1] in accept:
                logging.debug('StaticServer::%s %s %s' % (splits[1],
                                                          font_dir,
                                                          name))

                ret = static_file(filename=name, root=font_dir)

            else:
                # TODO this should readlly be doing a ?501? Auth exception
                raise Exception('arrrgh font type not accepted')
            return ret


    def start(self, host='localhost', port=8080):
        bottle.run(self._app, host=host, port=port)

class NostrWeb(StaticServer):

    def __init__(self, file_root, db_file):
        self._db_file = db_file

        # initial load of profiles, after that shoudl track events
        # obvs at some point keeping all profiles in mem might not work so well
        self._other_profiles = ProfileList.create_others_profiles_from_db(db_file).as_arr()

        super(NostrWeb, self).__init__(file_root)

        self._add_routes()

    def _add_routes(self):
        self._app.route('/profiles',callback=self._profiles_list)
        self._app.route('/contact_list',callback=self._contact_list)


        # obvs improve this and probably move to StaticServer
        def my_internal(e):
            return str(e).replace(',','<br>')

        self._app.error_handler = {
            500 : my_internal
        }

    def _profiles_list(self):
        ret = {
            'profiles' : self._other_profiles
        }
        return ret

    def _contact_list(self):
        pub_k = request.query.pub_k
        if not pub_k:
            raise Exception('pub_k is required')

        contacts = DataSet.from_sqlite(self._db_file,sql='select * from contacts where pub_k_owner=?',
                                       args=[pub_k])
        return {
            'contacts' : contacts.as_arr(dict_rows=True)
        }



def nostr_web():
    nostr_db_file = '/home/shaun/PycharmProjects/nostrpy/nostr/storage/nostr.db'
    my_server = NostrWeb(file_root='/home/shaun/PycharmProjects/nostrpy/web/static/',
                         db_file=nostr_db_file)
    my_server.start()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    nostr_web()