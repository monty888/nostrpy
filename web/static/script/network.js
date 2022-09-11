'use strict';
var APP = {};

APP.remote = function(){
    // move all urls here so we can change in future if we want
    let _note_url = '/text_events',
        _note_for_profile_url = '/text_events_for_profile',
        _reactions_for_profile = '/profile_reactions',
        _events_by_filter_url = '/events',
        _messages_url = '/messages',
        _events_by_seach_str = '/events_text_search',
        // this will probably need to change in future
        _all_profiles = '/profiles',
        _local_profiles_url = '/local_profiles',
        _update_profile_url = '/update_profile',
        _update_follows_url = '/update_follows',
        _export_profile_url = '/export_profile',
        _link_profile_url = '/link_profile',
        _set_profile_url = '/set_profile',
//        _current_profile_url = '/current_profile',
        // details on a single profile
        _profile_url = '/profile',
        _post_text_url = '/post_text',
        _post_event_url = '/post_event',
        _relay_info_url = '/relay_status',
        _relay_list_url = '/relay_list',
        _relay_remove_url = '/relay_remove',
        _relay_add_url = '/relay_add',
        _relay_update_mode_url = '/relay_update_mode',
        _event_relay_url = '/event_relay',
        _web_preview_url = '/web_preview',

        // to stop making duplicate calls we key here only one call per key will be made
        // either supply a key field else the call_args string is used
        // which will be url+params, no caching is done fo post methods
        _loading_cache = {}

    function make_params(params){
        let ret = '',
            sep = '?',
            key;

        if(params!==undefined){
            for(key in params){
                ret += sep+key+'='+params[key];
                sep = '&'
            }
        }

        return ret;
    }

//    function do_query(args){
//        let url = args['url'],
//            params = make_params(args['params']),
//            method = args['method'] || 'GET',
//            data = args['data'],
//            success = args['success'] || function(data){
//                console.log('load notes success');
//                console.log(data)
//            },
//            error = args['error'] || function(ajax, textstatus, errorThrown){
//                console.log('error loading remote' + url);
//                console.log(ajax.responseText);
//                console.log(errorThrown);
//            },
//            prepare = args.prepare,
//            call_args = {
//                method : method,
//                url: url+params,
//                error: error,
//                success: success
//            },
//            key = args.key!==undefined ? args.key : call_args.method.toLowerCase()==='get' ? call_args.url : data,
//            // by default gets are cached, not posts unless cache is set true
//            cache = args.cache===undefined ? call_args.method.toLowerCase()==='get' : args.cache,
//            the_cache,
//            //TODO: remove this - why not just set cache false?
//            force_new = args.force_new===undefined ? false : args.force_new;
//
//        if(data!==undefined){
//            call_args['data'] = data;
//        }
//        if(args['contentType']!==undefined){
//            call_args['contentType'] = args['contentType'];
//        }
//
//        if(cache){
//            if(force_new!==true){
//                the_cache = _loading_cache[key];
//            }
//
//            // just add to the queue and return
//            if(the_cache!==undefined){
//                // load started but not returned, queue
//                if(the_cache.is_loaded===false){
//                    the_cache.success.push(success);
//                    the_cache.error.push(error);
//                // load has already been done, call either error or success method straight away
//                }else{
//                    try{
//                        if(the_cache.data!==undefined){
//                            success(the_cache.data);
//                        }else{
//                            error(the_cache.ajax, the_cache.textstatus, the_cache.errorThrown);
//                        }
//                    }catch(e){
//                        console.log(e);
//                    }
//
//                }
//                return;
//            }
//
//            // init a cache and put our success and error in place
//            the_cache = _loading_cache[key] = {
//                'success' : [],
//                'error' : [],
//                'is_loaded' : false
//            };
//            the_cache.success.push(success);
//            the_cache.error.push(error);
//
//            // intercept success/error with are own methods so that multiple calls can be reduced to single ajax req
//            // out success and error that call back everyone in the queue
//            call_args.success = function(my_cache){
//                return function(data){
//                    if(typeof(prepare)==='function'){
//                        data = prepare(data);
//                    }
//
//                    my_cache.success.forEach(function(cSuccess){
//                        try{
//                            cSuccess(data);
//                        }catch(e){};
//                    });
//                    // so late calls will just get run straight away rather than called
//                    my_cache.is_loaded = true;
//                    my_cache.data = data;
//                };
//            }(the_cache);
//            call_args.error = function(my_cache){
//                return function(ajax, textstatus, errorThrown){
//                    my_cache.error.forEach(function(cError){
//                        try{
//                            cError(ajax, textstatus, errorThrown);
//                        }catch(e){};
//                    });
//                    // as success but for immidiate error
//                    my_cache.is_loaded = true;
//                    my_cache.ajax = ajax;
//                    my_cache.textstatus = textstatus;
//                    my_cache.errorThrown = errorThrown;
//                }
//            }(the_cache);
//
//        };
//
//        // make the call
//        $.ajax(call_args)
//
////        fetch(call_args.url, {
////            'filter': [{"kinds":[1]}]
////        }, {
////            'method': call_args.method
////        })
////        .then((response) => response.json())
////        .then((data) => {
////            if(call_args.success!==undefined){
////                call_args.success(data);
////            };
////        });
//
//
//    }

    function do_query(args){
        let url = args['url'],
            params = make_params(args['params']),
            query_str = url+params,
            method = args['method'] || 'get',
            data = args['data'] || {},
            success = args['success'] || function(data){
                console.log('load notes success');
                console.log(data)
            },
            error = args['error'] || function(ajax, textstatus, errorThrown){
                console.log('error loading remote' + url);
                console.log(ajax.responseText);
                console.log(errorThrown);
            },
            prepare = args.prepare,
            call_args = {
                error: error,
                success: success
            },
            // internal cache so multiple request don't make multiple fetchs... test browser header level cache
            // it might achive the same
            key,
            // by default gets are cached, not posts unless cache is set true
            cache,
            the_cache;

        method = method.toLowerCase();
        key = args.key!==undefined ? args.key : method==='get' ? query_str : data;
        cache = args.cache===undefined ? method==='get' : args.cache;

        function init_cache(key){
            return _loading_cache[key] = {
                'success' : [],
                'error' : [],
                'is_loaded' : false
            };
        }

        function get_data_cache(key){
            let ret = false;
            the_cache = _loading_cache[key];
            // just add to the queue and return
            if(the_cache!==undefined){
                // load started but not returned, queue
                if(the_cache.is_loaded===false){
                    the_cache.success.push(success);
                    the_cache.error.push(error);
                // load has already been done, call either error or success method straight away
                }else{
                    try{
                        ret = true
                        if(the_cache.data!==undefined){
                            success(the_cache.data);
                        }else{
                            // TODO have cache but error
                            //error(the_cache.ajax, the_cache.textstatus, the_cache.errorThrown);
                        }
                    }catch(e){
                        console.log(e);
                    }

                }
            }
            return ret;
        }


        if(data!==undefined){
            call_args['data'] = data;
        }

        if(cache){

            if(get_data_cache(key)){
                return;
            }

            // init a cache and put our success and error in place
            the_cache = init_cache(key);
            the_cache.success.push(success);
            the_cache.error.push(error);

            // intercept success/error with are own methods so that multiple calls can be reduced to single ajax req
            // out success and error that call back everyone in the queue
            call_args.success = function(my_cache){
                return function(data){
                    if(typeof(prepare)==='function'){
                        data = prepare(data);
                    }

                    my_cache.success.forEach(function(cSuccess){
                        try{
                            cSuccess(data);
                        }catch(e){};
                    });
                    // so late calls will just get run straight away rather than called
                    my_cache.is_loaded = true;
                    my_cache.data = data;
                };
            }(the_cache);
// TODO: error handling will be different than before
//            call_args.error = function(my_cache){
//                return function(ajax, textstatus, errorThrown){
//                    my_cache.error.forEach(function(cError){
//                        try{
//                            cError(ajax, textstatus, errorThrown);
//                        }catch(e){};
//                    });
//                    // as success but for immediate error
//                    my_cache.is_loaded = true;
//                    my_cache.ajax = ajax;
//                    my_cache.textstatus = textstatus;
//                    my_cache.errorThrown = errorThrown;
//                }
//            }(the_cache);

        };

        let request_obj = {
            'method': method
        };
        if(method==='post'){
            request_obj['body'] = data;
        }

        // actually make a request
        fetch(url+params, request_obj)
        .then((response) => response.json())
        .then((data) => {
            if(call_args.success!==undefined){
                call_args.success(data);
            };
        }).catch((error)=>{
            alert(error);
        });


    }

    function make_events(evt_data){
        let ret = []
        evt_data.forEach(function(c_evt){
            ret.push(APP.nostr.data.nostr_event(c_evt));
        });
        return ret
    }

    return {
        'load_profiles' : function(args){

            args['url'] = _all_profiles;
            // in future you'll probably want to supply one of this because the no params load everyone
            // is likely to become a problem at some point, in any case we'll probably use storage client side
            // (indexed db) and then only attempt to load what we don't have and havent tried for a set period of
            // time (as they may not exist anyhow) or let the nostr events get things upto date
            // pub_k can be used to supplement for_profile
            args['params'] = {};
            // single or , seperated list of pub_ks
            if(args.pub_k!==undefined){
                // changed to post to deal with large amounts of followers/contacts
                // though the GET method is still mounted so will work for smaller n of pub_ks
                // TODO add ti load profile gets full contact info and not just keys...
//                args['params']['pub_k'] = args['pub_k']
                args['data'] = 'pub_k='+args['pub_k'];
                args['method'] = 'POST';
            }
            if(args.match){
                args.params.match = args.match;
            }
            if(args.limit){
                args.params.limit = args.limit;
            }
            if(args.offset){
                args.params.offset = args.offset;
            }

            // all followers contacts for this profile
            if(args.for_profile!==undefined){
                args['params']['for_profile'] = args['for_profile']
            }
            do_query(args);
        },
        'load_profile' : function(args){
            args['url'] = _profile_url;
            args['params'] = {
                'include_followers': args.include_followers!==undefined ? args.include_followers : false,
                'include_contacts': args.include_contacts!==undefined ? args.include_contacts : false,
                'full_profiles': args.full_profiles!==undefined ? args.full_profiles : false
            };

            if(args.pub_k!==undefined){
                args.params['pub_k'] = args['pub_k'];
            }

            if(args.priv_k!==undefined){
                args.params['priv_k'] = args['priv_k'];
            }

            do_query(args);
        },
        'local_profiles' : function(args){
            args['url'] = _local_profiles_url;
            do_query(args);
        },
        'update_follows' : function(args){
            let follows = args.to_follow===undefined ? [] : args.to_follow,
                unfollows = args.to_unfollow===undefined ? [] : args.to_unfollow;

            args['url'] = _update_follows_url;
            args['params'] = {
                'pub_k' : args['pub_k'],
                'to_follow' : follows.join(','),
                'to_unfollow' : unfollows.join(',')
            };
            do_query(args);
        },
//        'set_profile' : function(args){
//            args['url'] = _set_profile_url;
//            args['method'] = 'POST';
//            args['params'] = {
//                // either pub key or profile name, if undefined then it's no profile
//                // (the lurker)
//                'profile' : args['key']!==undefined ? args['key'] : ''
//            };
//            do_query(args);
//        },
//        'current_profile' : function(args){
//            args['url'] = _current_profile_url;
//            do_query(args);
//        },
        'load_notes_for_profile': function(args){
            let o_success = args.success;

            args['url'] = _note_for_profile_url;
            args['params'] = {
                'pub_k' : args['pub_k']
            };
            if(args.until){
                args.params.until = args.until;
            }
            args.params.limit = args.limit || 100;

            args.success = function(data){
                data.events = make_events(data.events);
                o_success(data);
            };
            do_query(args);
        },
        'load_events' : function(args){
            let filter = args.filter===undefined ? APP.nostr.data.filter.create({'kinds':[1]}) : args.filter,
                o_success = args.success;

            args['url'] = _events_by_filter_url;
            args['method'] = 'POST';
            // this should be pub_k of the profile were using and is only required
            // if decrypt is needed
            args.params = {};
            if(args.pub_k){
                args.params.pub_k = args.pub_k;
            }
            args.params.limit = args.limit || 100;

            args['data'] = 'filter='+filter.as_str()

            args.success = function (data){
                data.events = make_events(data.events);
                o_success(data);
            };
            do_query(args);
        },
        'load_messages' : function(args){
            args['url'] = _messages_url;
            args['params'] = {
                'pub_k' : args.pub_k
            };
            args['prepare'] = function (data){
                data.events = make_events(data.events);
                return data;
            };
            do_query(args);
        },
        'load_reactions' : function(args){
            args['url'] = _reactions_for_profile;
            args['params'] = {
                'pub_k' : args.pub_k
            };
            args.params.limit = args.limit || 100;
            if(args.until!==undefined){
                args.params.until = args.until;
            }

            args['prepare'] = function (data){
                data.events = make_events(data.events);
                return data;
            };
            do_query(args);
        },
        'text_events_search' : function(args){
            let o_success = args.success;

            args['url'] = _events_by_seach_str;
            args['params'] = {
                'search_str' : args['search_str'],
                'limit' : args.limit || 100
            };
            if(args.until && args.until!==null){
                args.params.until = args.until;
            }

            args.success = function (data){
                data.events = make_events(data.events);
                o_success(data);
            };
            do_query(args);
        },
        'post_event' : function(args){

            args['url'] = _post_event_url;
            args['method'] = 'POST';
            let evt = _.extend({}, args.event);
            let content = encodeURIComponent(evt.content);
            evt.content = '';
            args['data'] = 'event=' + JSON.stringify(evt);
            args['data'] += '&content='+content;

            args['params'] = {
                'pub_k' : args['pub_k']
            };

            do_query(args);
        },
        'update_profile' : function(args){
            // default is to just save locally
            let save = args.save!==undefined ? args.save : true,
                publish = args.publish!==undefined ? args.publish : false,
                mode = args.mode!==undefined ? args.mode : 'edit';

            args['url'] = _update_profile_url;
            args['method'] = 'POST';
            args['data'] = 'profile=' + JSON.stringify(args.profile)+ '&save='+save+'&publish='+publish+'&mode='+mode
            do_query(args);
        },
        'export_profile' : function(args){
            // default is to just save locally
            args['params'] = {
                'for_profile' : args.for_profile
            };
            args['url'] = _export_profile_url;
            args['method'] = 'POST';
            do_query(args);

        },
        'link_profile' : function(args){
            args['url'] = _link_profile_url;
            args['method'] = 'POST';
            args['params'] = {
                'pub_k' : args.pub_k,
                'priv_k' : args.priv_k
            };
            do_query(args);
        },
        'relay_info' : function(args){
            args['url'] = _relay_info_url;
            do_query(args);
        },
        'relay_list' : function(args){
            args['url'] = _relay_list_url;
            if(args.pub_k!==undefined){
                args['params'] = {
                    'pub_k' : args.pub_k
                };
            };
            do_query(args);
        },
        'relay_remove': function(args){
            args['params'] = {
                'url' : args.url
            };
            args['url'] = _relay_remove_url;
            args.cache = false;
            do_query(args);
        },
        'relay_update_mode': function(args){
            args['params'] = {
                'url' : args.url,
                'mode' : args.mode
            };
            args['url'] = _relay_update_mode_url;
            args.cache = false;
            do_query(args);
        },
        'relay_add': function(args){
            args['params'] = {
                'url' : args.url,
                'mode' : args.mode
            };
            args['url'] = _relay_add_url;
            args.cache = false;
            do_query(args);
        },
        'event_relay' : function(args){
            args['url'] = _event_relay_url;
            args['params'] = {
                'event_id' : args.event_id
            };
            do_query(args);
        },
        'web_preview' : function(args){
            args['params'] = {
                'for_url' : args.url
            };
            args['url'] = _web_preview_url;
            do_query(args);
        }

    }
}();

APP.nostr_client = function(){

    function _create_ws(args){
        let _url,
            _socket,
            _isopen = false,
            _on_data = args.on_data || function(data){
                console.log(data);
            },
            _on_open = args.on_open || function(){},
            _protocol = location.protocol==='https' ? 'wss://' : 'ws://';

       // default where no url supplied, mostly this will be wants required
        if(_url===undefined){
            _url = _protocol + location.host + '/websocket'
        }
        // now we can open
        _socket = new WebSocket(_url);

        _socket.onclose = function(e){
            console.log('socket onclose - ');
            console.log(e);
        };

        _socket.onmessage = function(e) {
            console.log('socket onmessage - ');
            _on_data(JSON.parse(e['data']));
        };

        _socket.onerror = function(e) {
            console.log('socket onerror - '+e);
        };

        _socket.onopen = function(e){
            console.log('socket onopen - ');
            console.log(e);
            _on_open({
                'post' : function(){
                    _socket.send('wtf');
                }
            });
        }
    };

    function start_client(){

//        function make_status_str(status){
//            let ret = status.connected+';';
//            // using a pool, we probably always would
//            if(status.relays!==undefined){
//                for(let c_relay in status.relays){
//                    ret+=c_relay+'-'+status.relays[c_relay].connected+';'
//                }
//            }
//            return ret;
//        }

        _create_ws({
            'on_data' : function(data){
                let n_relay_status;
                if(data[0]==='relay_status'){
                    // relay modal uses this, it fires for every status we get so we can update times
                    APP.nostr.data.event.fire_event('relay_status', data[1]);
                // assumed event
                }else{
                    // nostr event
                    if(data.kind!==undefined){
                        APP.nostr.data.event.fire_event('event', APP.nostr.data.nostr_event(data));
                    }
                }
            }
        });
    }

    return {
        'create' : start_client
    }
}();