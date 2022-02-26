'use strict';
var APP = {};

APP.remote = function(){
    // move all urls here so we can change in future if we want
    let _note_url = '/notes';

    function load_notes(callback, pub_k){
        // set up the query
        let url = '/notes';
        if(pub_k!==undefined){
            url = url + '?pub_k=' + pub_k
        }

        // make the call
        $.ajax({
            url: url
        }).done(callback);
    }

    return {
        'load_profiles' : function(callback){
            $.ajax({
                url: '/profiles'
            }).done(callback);
        },
        'load_profile_contacts' : function(pub_k,callback){
            $.ajax({
                url: '/contact_list?pub_k=' + pub_k
            }).done(callback);
        },
        'load_profile_notes' : function(pub_k, callback){
            load_notes(callback, pub_k)
        },
        'load_notes' : function(callback){
            load_notes(callback);
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