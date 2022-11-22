APP.nostr.data.state = function(){
    // todo

    return {
        put(name, value, args){
            args = args || {};
            sessionStorage.setItem(name, value);
        },
        get(name, args){
            args = args || {};
            let def = args.def===undefined ? null : args.def,
            ret = sessionStorage.getItem(name);
            // not stored for session
            if(ret===null){
                // did we get in the /state/js that the server sent us
                if(APP.nostr.data.server_state[name]!==undefined){
                    ret = APP.nostr.data.server_state[name];
                // else default val or null
                }else{
                    ret = def;
                }
            }
            return ret;
        }
    }
}();

APP.nostr.data.relay_status = function(){
    let _state;

    function init(){
        _state = JSON.parse(APP.nostr.data.server_state.relay_status);
        // watch for changes, to start watching for changes you need to make a get request...
        APP.nostr.data.event.add_listener('relay_status', function(type, data){
            _state = data;
        });
    };

    return {
        get(){
            // intial state from server, rendered into state/js file
            if(_state===undefined){
                init();
            };
            return _state;
        }
    }
}();

APP.nostr.data.filter = function(){

    function create(filter){
        let _my_filter = [],
            // filters currently immuntable so we'll work this out when we create too
            _as_str;

        // make so we have arr of filters
        if(typeof(filter.forEach)==='function'){
            filter.forEach(function(c_filter){
                _my_filter.push(_.extend({},c_filter));
            });

        }else{
            _my_filter.push(_.extend({},filter));
        }

        // str version
        _as_str = JSON.stringify(_my_filter);

        // changes for quicker testing and consistancy
        _my_filter.forEach(function(c_filter){
            ['kinds','#p','authors','#e','ids'].forEach(function(c_f){
                if(c_filter[c_f]!==undefined){
                    c_filter[c_f] = new Set(c_filter[c_f]);
                }
            });

        });

        function as_str(){
            return _as_str;
        }

        // as [{},{}...] parse _as_str as our internal rep uses sets which we don't want to return
        function as_object(){
            return JSON.parse(_as_str)
        }

        function test(evt){
            let c_filter,
                is_match,
                c_f;

            function check_tags(the_set, tname){
                let c_tag,
                    ret = false;
                for(let i=0;i<evt.tags.length;i++){
                    c_tag = evt.tags[i];
                    if(c_tag.length>=1 && c_tag[0]===tname){
                        if(the_set.has(c_tag[1])){
                            ret = true;
                            break;
                        }
                    }
                }
                return ret;
            }

            for(let i=0;i<_my_filter.length;i++){
                c_filter = _my_filter[i];
                is_match = true;
                // check kind
                if(c_filter.kinds!==undefined){
                    is_match = is_match && c_filter.kinds.has(evt.kind);
                }
                // check author who created event
                if(c_filter.authors!==undefined){
                    is_match = is_match && c_filter.authors.has(evt.pubkey);
                }
                // event_ids
                if(c_filter.ids!==undefined){
                    is_match = is_match && c_filter.ids.has(evt.id);
                }
                if(c_filter['#p']!==undefined){
                    is_match = is_match && check_tags(c_filter['#p'], 'p');
                }

                if(c_filter['#e']!==undefined){
                    is_match = is_match && check_tags(c_filter['#e'], 'e');
                }

                if(is_match){
                    break;
                }
            }
            return is_match;
        }

        return {
            'as_str': as_str,
            'as_object': as_object,
            'test': test
        }
    }

    return {
        'create' : create
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

    let _user;

    // makes sure our user obj has the most upto
    APP.nostr.data.event.add_listener('event',function(of_type, data){
        if(data.kind===3 && _user.pub_k!==undefined){
            if(data.pubkey===_user.pub_k){
                let n_contacts = [];
                data.tags.forEach(function(c_tag){
                    if(c_tag.length>=1){
                        if(c_tag[0]=='p'){
                            n_contacts.push(c_tag[1]);
                        }
                    }
                });
                _user.contacts = n_contacts;
                set_session_profile(_user);
                APP.nostr.data.event.fire_event('contacts_updated', _user);
            }
        }
    });

    function set_session_profile(data){
        _user = data;
        APP.nostr.data.state.put('profile', JSON.stringify(_user));
    }

    // for simple get/sets
    function _property(name, val, def){
        let ret = val;

        if(val!==undefined && val!==null){
            APP.nostr.data.state.put(name, val);
        }else{
            ret = APP.nostr.data.state.get(name, {
                'def' : def
            });
        }
        return ret
    }

    return {
        'profile': function(user){
            function set_profile(pub_k){
                function loaded(p){
                    set_session_profile(p);
                    APP.nostr.data.event.fire_event('profile_set', _user);
                }

                if(pub_k===undefined){
                    loaded({});
                }else{
                    APP.remote.load_profile({
                        'pub_k' : pub_k,
                        'include_contacts' : 'keys',
                        'success' : loaded
                    });
                }
            }

            if(_user===undefined){
                let my_user = JSON.parse(APP.nostr.data.state.get('profile', {
                    'def' : '{}'
                }));
                _user = my_user;
            }
            // setting a new user
            if(user!==undefined && user.pub_k!==_user.pub_k){
                set_profile(user.pub_k)
            }

            // caller doesn't have the same obj
            return _.extend({},_user);
        },
        get(name,def){
            return _property(name,null,def);
        },
        put(name,value){
            return _property(name,value);
        },
        'get_client' : function(){
            return CLIENT;
        },
        'is_add_client_tag' : function(){
            return APP.nostr.data.state.get('add_client_tag', {
                'def': false
            });
        },
        'set_add_client_tag' : function(val){
            APP.nostr.data.state.put('add_client_tag', val);
        },
        'enable_media' : function(val){
            return _property('enable_media', val, true);
        },
        'enable_web_preview': function(val){
            let wp = _property('enable_web_preview', val, true);
            // media also needs to be enabled
            return wp && APP.nostr.data.user.enable_media();
        },
        // prob only for debugging, should be on
        // session store of profiles we've seen
        // NOTE until we get the client to put on seeing meta events
        // session cache will be an issue so disabled for now
        'profile_cache' : function(val){
            return _property('profile_cache', val, true);
        },
        'follow_toggle': function(){
            let my_timer,
                follows = {},
                unfollows = {};

            return function(pub_k, callback, delay){
                delay = delay===undefined ? 200 : delay;
                clearTimeout(my_timer);
                if(follows[pub_k]!==undefined){
                    delete follows[pub_k]
                }else if(unfollows[pub_k]!==undefined){
                    delete unfollows[pub_k];
                }else{
                    if(_user.contacts.includes(pub_k)){
                        unfollows[pub_k] = true;
                    }else{
                        follows[pub_k] = true;
                    }
                }

                my_timer = setTimeout(function(){
                    let k,
                        to_follow= [],
                        to_unfollow = [];

                    for(k in follows){
                        to_follow.push(k);
                    }

                    for(k in unfollows){
                        to_unfollow.push(k);
                    }

                    if(to_follow.length>0 || to_unfollow.length>0){
                        // change to post?!
                        APP.remote.update_follows({
                            'pub_k': _user.pub_k,
                            'to_follow' : to_follow,
                            'to_unfollow' : to_unfollow,
                            'cache' : false,
                            'success' : function(data){
                                if(typeof(callback)==='function'){
                                    callback(data);
                                }
                            }
                        });
                    }
                    unfollows = {};
                    follows = {};
                },delay);

            }
        }()
    };
}();


/*
    Profiles should be accessed through here, don't use network methods directly...
*/
APP.nostr.data.profiles = function(){
    const _data = APP.nostr.data;
    let _lookup = {},
        _in_progress_count = 0,
        _wait_load = [],
        _session_cache = APP.nostr.data.user.profile_cache();

    function _get_picture(p){
        let ret;
        if(p.attrs.picture===undefined || p.attrs.picture===''){
            ret = APP.nostr.gui.robo_images.get_url({
                'text' : p.pub_k
            });
        }else{
            ret = p.attrs.picture;
        }
        return ret;
    }

    function _do_store(data){
        data.profiles.forEach(function(p){
            _clean_profile(p);
            // loads via search might override profiles we already have
            // probably this is not a problem, but we might have fetched contacts
            // just incase don't restore this
            if(_lookup[p.pub_k]===undefined || _lookup[p.pub_k].state!=='loaded'){
                _lookup[p['pub_k']] = {
                    'state': 'loaded',
                    'profile': p
                };

                if(_session_cache){
                    APP.nostr.data.state.put('profile-'+p.pub_k, JSON.stringify(p));
                }

            }
        });
    }

    function _clean_profile(p){
        if(p.attrs===undefined){
            p.attrs = {};
        };
        p.load_contact_info = _get_load_contact_info(p);
        p.picture = _get_picture(p);
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
    }

   /*
        lazy load method to get contacts onto profile objs
    */
    function _get_load_contact_info(p){
        return function(callback){
            // make sure we're looking at same profile obj
            let my_p = _lookup[p.pub_k].profile;
            // already loaded, caller can continue
            if(my_p.contacts!==undefined){
                callback();
            }
            // load required
            APP.remote.load_profile({
                'pub_k': p.pub_k,
                'include_followers': 'keys',
                'include_contacts': 'keys',
                'success' : function(data){
                    let load_required = [];
                    // update org profile with contacts and followers
                    my_p.contacts = data['contacts'];
                    my_p.followers = data['followed_by'];
                    // probably we don't have all the profiles for followers/contacts so anotehr load required :(
                    ['contacts','followers'].forEach(function(c_f){
                        my_p[c_f].forEach(function(c_key){
                            if(_lookup[c_key]===undefined){
                                load_required.push(c_key);
                            }
                        });
                    });

                    if(load_required.length===0){
                        callback();
                    }else{
                        // looks a bit weird but as the lookup is actually global I think this is ok...
                        APP.nostr.data.profiles_n.create({
                            'pub_ks': load_required,
                            'on_load': callback
                        });
                    }
                }
            });
        }
    }

    function fetch(args){
        args = args || {};
        // should never reach here without pub_ks
        let _pub_ks = args.pub_ks!==undefined ? args.pub_ks : [],
            _on_load = args.on_load,
            _load_args;

        function do_load(load_arr){
            _in_progress_count+=1;
            if(typeof(_on_load)==='function'){
                _wait_load.push(_on_load);
            }

            _load_args = {
                'pub_k' : load_arr.join(','),
                'success' : function(data){
                    _in_progress_count-=1;
                    _do_store(data);

                    // mark unloaded as not found
                    load_arr.forEach(function(pub_k){
                        if(_lookup[pub_k]!==undefined && _lookup[pub_k].state!=='loaded'){
                            _lookup[pub_k] = {
                                'state': 'not found'
                            };
                        }
                    });
                    if(_in_progress_count===0){
                        _wait_load.forEach(function(c_callback){
                            try{
                                c_callback();
                            }catch(e){
                            }
                        });
                        _wait_load = [];
                    }

                }
            };
            APP.remote.load_profiles(_load_args);
        }

        function init(){
            let // already started loading by different caller
                load_start_count = 0,
                // those we need to load for ourself
                load_arr = [],
                p_slot;

            _pub_ks.forEach(function(pub_k){
                p_slot = _lookup[pub_k];
                // we're the first to ask for this
                if(p_slot===undefined){

                    // cached in session storage, will need to check how much can be stored here and limit
                    // as required, currently cache all profiles is 400k<
                    if(_session_cache){
                        p = APP.nostr.data.state.get('profile-'+pub_k);
                        if(p!==null){
                            p_slot = _lookup[pub_k] = {
                                'state': 'loaded',
                                'profile': JSON.parse(p)
                            };
                        }
                    }

                    // going to have to load
                    if(p_slot===undefined){
                        _lookup[pub_k] = {
                            'state' : 'loading'
                        };
                        load_arr.push(pub_k);
                    }


                // someone else asked fot this but it's not loaded yet
                }else if(p_slot.state==='loading'){
                    load_start_count+=1;
                }
            });

            // cool we had all the profiles already
            if(load_arr.length===0 && load_start_count===0){
                if(typeof(_on_load)==='function'){
                    _on_load();
                }
            }else{
                do_load(load_arr);
            }

        }
        init();
    };

    function search(args){
        let load_func = args.on_load;
        args.success = (data) =>{
            _do_store(data);
            if(typeof(load_func)==='function'){
                load_func(data);
            }
        }
        APP.remote.load_profiles(args);
    }

    function lookup(pub_k, callback){
        let ret = null,
            c_val = _lookup[pub_k];
        if(c_val!==undefined){
            if(c_val.state==='loaded'){
                ret = c_val.profile;
            }
        }
        return ret;
    }

    function put(p){
        /* ideally all profiles would be got via search/fetch or we register here to see updates
            on remote requests. At the moment all calls to do we profiles are not done through here
            so we expose a put method. The given profile will alway overwrite anything we have and be marked as loaded
        */

        // clean the profile obj to what we expect
        _clean_profile(p);

        c_val = _lookup[p.pub_k] = {
            'profile' : p,
            'state': 'loaded'
        };

        if(_session_cache){
            APP.nostr.data.state.put('profile-'+p.pub_k, JSON.stringify(p));
        }
        return c_val;
    }

    _data.event.add_listener('event', (type, evt) =>{
        // if we have update our cache, if we don't have cached we'll just let it get pulled normally
        let local_p,
            attrs;

        if((evt.kind==0) && (local_p = lookup(evt.pubkey)) && (evt.created_at>local_p.updated_at)){
            try{
                local_p.attrs = JSON.parse(evt.content);
                _clean_profile(local_p);
                // we should fire event here to sync

            }catch(e){
                console.log(e);
            }
        }
    });


    return {
        // used when we know what pks we want
        'fetch': fetch,
        // only used by the profile search screen at the moment and rets everything
        // (this also means all profiles will be cached after this point) obvs this is not
        // scalable. so in future it'll have some matches criteria and only ret a max no of profiles
        // though this will still be cached as everything else
        'search' : search,
        'lookup': lookup,
        'put': put
    };
}();


/*
    same thing but this is only for local profiles,
    ie the ones that we can use to mkae posts, edit their meta etc.
    done without the load code from above...probably need to add it...but work out what the fuck thats
    doing first because I thought the network code was stopping mutiple requests to the same resource...

    TODO... do we still need this?!?!?
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

/*
    returns a wrap around event JSON with some handy methods
*/
APP.nostr.data.nostr_event = function(event){
    const TEXT = 1,
        ENCRYPT = 4;

    let _data = event;

    function get_tag_values(name, test_func, break_on_match){
        let ret = [],
            tags = _data.tags,
            is_match,
            val;
        break_on_match = break_on_match===undefined ? false : break_on_match;

        for(let i=0;i<tags.length;i++){
            c_tag = tags[i];
            if(c_tag.length>1 && c_tag[0]===name){
                is_match = true;
                val = c_tag[1];
                if(typeof(test_func)==='function'){
                    is_match = test_func(val);
                }
                if(is_match){
                    ret.push(val);
                    if(break_on_match){
                        break;
                    }
                }
            }
        }
        return ret;
    }

    function get_first_tag_value(name, test_func){
        return get_tag_values(name, test_func, true);
    }

    // not sure if i like this... does mean we can access the evt fields like it was just the normal
    // {} obj though
    _data = _.extend({
        is_encrypt(){
            return _data.kind === ENCRYPT;
        },
        'get_tag_values' : get_tag_values,
//        get_p_tag_values(test_func, break_on_match){
//            return get_p_tag_values(test_func, break_on_match);
//        },
        'get_first_tag_value' : get_first_tag_value,
        get_first_p_tag_value(test_func){
            return get_first_tag_value('p', test_func);
        },
        get_first_e_tag_value(test_func){
            return get_first_tag_value('e', test_func);
        },
        copy(){
            return APP.nostr.data.nostr_event(_.extend({},_data));
        }

    }, _data);

    if(_data.react_event){
        _data.react_event = APP.nostr.data.nostr_event(_data.react_event)
    }

    return _data

};