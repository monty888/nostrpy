APP.nostr.data.state = function(){
    /* some basic state, done via cookies currently but expect we'll at some point move to session/local storage
        some would probably be better on the server and also possible indexdb

    */
    function set_cookie(cName, cValue, expDays) {
            let date = new Date();
            date.setTime(date.getTime() + (expDays * 24 * 60 * 60 * 1000));
            const expires = "expires=" + date.toUTCString();
            document.cookie = cName + "=" + cValue + "; " + expires + "; path=/";
    }

    function get_cookie(cName, def) {
          const name = cName + "=";
          const cDecoded = decodeURIComponent(document.cookie); //to be careful
          const cArr = cDecoded .split('; ');
          let ret;

          cArr.forEach(function(val){
            if (val.indexOf(name) === 0) ret = val.substring(name.length);
          })
          if(ret===undefined){
            ret = def===undefined ? null : def;
          }
          return ret;
    }

    return {
        'put': function(name, value, args){
            args = args || {};
            set_cookie(name, value);
        },
        'get': function(name, args){
            args = args || {};
            let def = args.def;
            return get_cookie(name, def);
        }
    }
}();

APP.nostr.data.event = function(){
    let _listener = {};

    return {
        'add_listener' : function(for_type, listener){
            if(_listener[for_type]===undefined){
                _listener[for_type] = [];
            }
            _listener[for_type].push(listener);
        },
        'remove_listener' : function(for_type, listener){
            if(_listener[for_type]!==undefined){
                let lists = _listener[for_type];
                for(let i=0;i<lists.length;i++){
                    if(lists[i]===listener){
                        lists.splice(i,1);
                        break;
                    }
                }

            }
        },
        'fire_event' : function(of_type, data){
            if(_listener[of_type]!==undefined){
                _listener[of_type].forEach(function(c_list){
                    try{
                        c_list(of_type,data);
                    }catch(e){
                        console.log(e)
                    }
                });
            }

        }
    }
}();

APP.nostr.data.user = function(){
    const CLIENT = 'nostrpy-web';

    return {
        'get_profile' : function(){
            let ret = APP.nostr.data.state.get('profile', {
                'def' : {}
            });
            if(typeof(ret)==='string'){
                try{
                    ret = JSON.parse(ret)
                }catch(e){
                    ret = {};
                }
            }
            return ret;
        },
        'set_profile' : function(p){
            APP.nostr.data.state.put('profile', JSON.stringify(p));
            APP.nostr.data.event.fire_event('profile_set', p);

//            APP.remote.set_profile({
//                'key' : key,
//                'success' : function(data){
//                    _current_profile = data;
//                    if(typeof(callback)==='function'){
//                        return data;
//                    }
//                    APP.nostr.data.event.fire_event('profile_set', data);
//                }
//            });
        },
        // to replace get/set
        'profile': function(p){
            let ret = p;
            if(p!==undefined){
                APP.nostr.data.state.put('profile', JSON.stringify(p));
                APP.nostr.data.event.fire_event('profile_set', p);
            }else{
                ret = APP.nostr.data.state.get('profile', {
                    'def' : {}
                });
                if(typeof(ret)==='string'){
                    try{
                        ret = JSON.parse(ret)
                    }catch(e){
                        ret = {};
                    }
                }
            }
            return ret;
        },
        'get_client' : function(){
            return CLIENT;
        },
        'is_add_client_tag' : function(){
            return APP.nostr.data.state.get('add_client_tag', {
                'def': true
            });
        },
        'set_add_client_tag' : function(val){
            APP.nostr.data.state.put('add_client_tag', val);
        },
        'enable_media' : function(val){
            let ret = val;
            if(val!==undefined){
                APP.nostr.data.state.set('enable_media', val);
            }else{
                ret = APP.nostr.data.state.get('enable_media', {
                    'def' : true
                });
            }
            return ret
        }
    };
}();

/*
    profiles data is global,
    the load will only be attempted once no matter how many times init is called
    so probably better to only do in one place and use on_load for other places
    in future clear the init flag on load fail so init can be rerun...
    obvs int the long run keeping lookup of all profiles in mem isn't going to scale...
*/
APP.nostr.data.profiles = function(){
    // as loaded
    let _profiles_arr,
    // key'd pubk for access
    _profiles_lookup,
    // called when completed
    _on_load = [],
    // set true when initial load is done
    _is_loaded = false,
    // has loaded started
    _load_started = false;

    function _get_load_contact_info(p){
        return function(callback){
            // make sure we're looking at same profile obj
            let my_p = _profiles_lookup[p.pub_k];
            // already loaded, caller can continue
            if(my_p.contacts!==undefined){
                callback();
            }
            // load required
            APP.remote.load_profile({
                'pub_k': p.pub_k,
                'include_followers': true,
                'include_contacts': true,
                'success' : function(data){
                    // update org profile with contacts and folloers
                    my_p.contacts = data['contacts'];
                    my_p.followers = data['followed_by'];
                    try{
                        callback();
                    }catch(e){
                        console.log(e);
                    }
                }
            });
        }
    }

    function _loaded(data){
        _profiles_arr = data['profiles'];
        _profiles_lookup = {};
        _profiles_arr.forEach(function(p){
            p.load_contact_info = _get_load_contact_info(p);
            _profiles_lookup[p['pub_k']] = p;
            // do some clean up
            if(p.attrs.about===null){
                p.attrs.about='';
            }
            if(p.attrs.name===null){
                p.attrs.name='';
            }
            if(p.attrs.picture!==undefined){
                if((p.attrs.picture===null) || (p.attrs.picture.toLowerCase().indexOf('http')!==0)){
                    delete p.attrs.picture;
                }
            }

        });


        _is_loaded = true;
        _on_load.forEach(function(c_on_load){
            try{
                c_on_load();
            }catch(e){
                console.log(e);
            }
        });

        APP.nostr.data.event.fire_event('profiles-loaded',{});
    }

    function init(args){
        args = args || {};
        args.success = _loaded;

        if(_load_started===true){
            if(typeof(args.on_load)==='function'){
                if(_is_loaded){
                    args.on_load();
                }else{
                    _on_load.push(args.on_load);
                }
            }
            return;
        }

        _load_started = true;
        if(typeof(args.on_load)==='function'){
            _on_load.push(args.on_load);
        };

        APP.remote.load_profiles(args);
    };

    return {
        'init' : init,
        'is_loaded': function(){
            return _is_loaded;
        },
        'lookup': function(pub_k){
            return _profiles_lookup[pub_k];
        },
        'count' : function(){
            return _profiles_arr.length;
        },
        'all' : function(){
            return _profiles_arr;
        }

    };
}();

/*
    same thing but this is only for local profiles,
    ie the ones that we can use to mkae posts, edit their meta etc.
    done without the load code from above...probably need to add it...but work out what the fuck thats
    doing first because I thought the network code was stopping mutiple requests to the same resource...
*/
APP.nostr.data.local_profiles = function(){
        // as loaded
    let _profiles_arr,
        // set true when initial load is done
    _is_loaded = false,
        // has loaded started
    _load_started = false;

    function init(args){
        let o_success = args.success;
        _load_started = true;
        args.success = function(data){
            _is_loaded = true;
            _profiles_arr = data['profiles'];
            if(typeof(o_success)==='function'){
                o_success(_profiles_arr)
            }
        }
        args.cache = false;

        if(_is_loaded){
            o_success(_profiles_arr);
        }else{
            APP.remote.local_profiles(args);
        }
    };

    APP.nostr.data.event.add_listener('local_profile_update',function(of_type, data){
        _is_loaded = false;
    });


    return {
        'init' : init,
        'profiles' : function(){
            return _profiles_arr;
        }
    }

}();