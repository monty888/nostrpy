'use strict';
var APP = {};

APP.remote = function(){
    // move all urls here so we can change in future if we want
    let _note_url = '/text_events',
        _note_for_profile_url = '/text_events_for_profile',
        _events_by_filter_url = '/events',
        _events_by_seach_str = '/events_text_search',
        // this will probably need to change in future
        _all_profiles = '/profiles',
        // details on a single profile
        _profile_url = '/profile',
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

    function do_query(args){
        let url = args['url'],
            params = make_params(args['params']),
            method = args['method'] || 'GET',
            data = args['data'],
            success = args['success'] || function(data){
                console.log('load notes success');
                console.log(data)
            },
            error = args['error'] || function(ajax, textstatus, errorThrown){
                console.log('error loading remote' + url);
                console.log(ajax.responseText);
                console.log(errorThrown);
            },
            call_args = {
                method : method,
                url: url+params,
                error: error,
                success: success
            },
            key = args.key!==undefined ? args.key : call_args.url,
            the_cache;

        if(data!==undefined){
            call_args['data'] = data;
        }

        if(call_args.method.toLowerCase()==='get'){
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
                        if(the_cache.data!==undefined){
                            success(the_cache.data);
                        }else{
                            error(the_cache.ajax, the_cache.textstatus, the_cache.errorThrown);
                        }
                    }catch(e){
                        console.log(e);
                    }

                }
                return;
            }

            // init a cache and put our success and error in place
            the_cache = _loading_cache[key] = {
                'success' : [],
                'error' : [],
                'is_loaded' : false
            };
            the_cache.success.push(success);
            the_cache.error.push(error);

            // intercept success/error with are own methods so that multiple calls can be reduced to single ajax req
            // out success and error that call back everyone in the queue
            call_args.success = function(data){
                the_cache.success.forEach(function(cSuccess){
                    try{
                        cSuccess(data);
                    }catch(e){};
                });
                // so late calls will just get run straight away rather than called
                the_cache.is_loaded = true;
                the_cache.data = data;
            };
            call_args.error = function(ajax, textstatus, errorThrown){
                the_cache.error.forEach(function(cError){
                    try{
                        cError(ajax, textstatus, errorThrown);
                    }catch(e){};
                });
                // as success but for immidiate error
                the_cache.is_loaded = true;
                the_cache.ajax = ajax;
                the_cache.textstatus = textstatus;
                the_cache.errorThrown = errorThrown;
            }

        };


        // make the call
        $.ajax(call_args)

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
                args['params']['pub_k'] = args['pub_k']
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
                'pub_k' : args['pub_k'],
                'include_followers': args.include_followers!==undefined ? args.include_followers : false,
                'include_contacts': args.include_contacts!==undefined ? args.include_contacts : false
            };
            do_query(args);
        },
//        'load_profile_contacts' : function(pub_k,callback){
//            $.ajax({
//                url: '/contact_list?pub_k=' + pub_k
//            }).done(callback);
//        },
//        'load_profile_notes' : function(pub_k, callback){
//            load_notes(callback, pub_k)
//        },
        'load_notes_from_profile': function(args){
            args['url'] = _note_url;
            args['params'] = {
                'pub_k' : args['pub_k']
            },
            do_query(args);
        },
        'load_notes_for_profile': function(args){
            args['url'] = _note_for_profile_url;
            args['params'] = {
                'pub_k' : args['pub_k']
            };

            do_query(args);
        },
        'load_events' : function(args){
            let filter = args.filter===undefined ? {'kinds':[1]} : args.filter;
            args['url'] = _events_by_filter_url;
            args['method'] = 'POST';
            args['data'] = 'filter=' + JSON.stringify(filter);
            do_query(args);
        },
        'text_events_search' : function(args){
            args['url'] = _events_by_seach_str;
            args['params'] = {
                'search_str' : args['search_str']
            };
            do_query(args);
        }


    }
}();

APP.nostr_client = function(){

    function create(args){
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
            console.log(e);
            let json = JSON.parse(e['data']);
            _on_data(json);
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


    return {
        'create' : create
    }
}();