'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        //
        _pub_k = _params.get('pub_k'),
        // main container where we'll draw out the events
        _main_con,
        // for now we're using a standard event view, maybe in future
        // compress down into unique users
        _my_event_view,
        _current_profile = APP.nostr.data.user.profile(),
        _my_filter;

    function load_notes(){
        APP.remote.load_events({
            'pub_k' : APP.nostr.data.user.profile().pub_k,
            'filter' : _my_filter,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    _my_event_view.set_notes(data['events']);
                }
            }
        });
    }

    // start when everything is ready
    document.addEventListener('DOMContentLoaded', ()=> {
        if(_pub_k===null){
            alert('pub_k is required');
            return;
        }

        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = _('#main-con');
        _main_con.css('overflow-y','auto');

        _my_filter = APP.nostr.data.filter.create([
            {
                'kinds' :[4],
                'authors' : [_current_profile.pub_k],
                '#p': [_pub_k]
            },
            {
                'kinds': [4],
                'authors' : [_pub_k],
                '#p' : [_current_profile.pub_k]
            }
        ]);
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _main_con,
            'filter' : _my_filter
        });

        load_notes();
        // init the profiles data
//        APP.nostr.data.profiles.init({
//            'on_load' : function(){
//                _my_event_view.profiles_loaded();
//            }
//        });


        APP.nostr.gui.post_button.create();
        // our own listeners
        // profile has changed
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            // it'll go to home now anyhow
        });

        // so we see new events
        APP.nostr.data.event.add_listener('event', function(type, event){
            _my_event_view.add(event);
        });

        // any post
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            // its just a post better go back to the reply screen
            if(event.type!=='reply'){
                window.location = '/';
            }
        });

        // start client for future notes....
        APP.nostr_client.create();

    });
}();