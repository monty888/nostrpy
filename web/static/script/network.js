'use strict';
var APP = {};

APP.remote = function(){
    // move all urls here so we can change in future if we want
    let _note_url = '/text_events',
        _note_for_profile_url = '/text_events_for_profile',
        _events_by_filter_url = '/events',
        // this will probably need to change in future
        _all_profiles = '/profiles',
        // details on a single profile
        _profile_url = '/profile';

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
            };

        if(data!==undefined){
            call_args['data'] = data;
        }
        // make the call
        $.ajax(call_args)

    }

    return {
        'load_profiles' : function(args){
            args['url'] = _all_profiles;
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
            args['url'] = _events_by_filter_url;
            args['method'] = 'POST';
            args['data'] = 'filter=' + JSON.stringify({
                'kinds' : [1]
            });
            do_query(args);
        }

    }
}();

APP.nostr_client = function(){

    function create(to_url, callback, data_handler){
        let _url = to_url,
            _socket = new WebSocket(_url),
            _isopen = false,
            _data_handler = data_handler;

        _socket.onclose = function(e){
            console.log('socket onclose - ');
            console.log(e);
        };

        _socket.onmessage = function(e) {
            console.log('socket onmessage - ');
            console.log(e);
            let json = JSON.parse(e['data']);
            if(_data_handler!==undefined){
                _data_handler(json);
            }
        };

        _socket.onerror = function(e) {
            console.log('socket onerror - '+e);
        };

        _socket.onopen = function(e){
            console.log('socket onopen - ');
            console.log(e);
            callback({
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