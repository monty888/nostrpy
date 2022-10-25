'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // main container where we'll draw out the events
        _main_con,
        // for now we're using a standard event view, maybe in future
        // compress down into unique users
        _my_view,
        _current_profile = APP.nostr.data.user.profile(),
        _my_filter;

    function load_notes(){
        APP.remote.load_messages({
            'pub_k' : APP.nostr.data.user.profile().pub_k,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    _my_view = APP.nostr.gui.dm_list.create({
                        'con' : _main_con,
                        'events' : data['events']
                    });
                }
            }
        });
    }

    // start when everything is ready
    document.addEventListener('DOMContentLoaded', ()=> {

        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = _('#main-con');
        _main_con.css('overflow-y','auto');

        _my_filter = APP.nostr.data.filter.create([
            {
                'kinds' :[4],
                'authors' : [_current_profile.pub_k]
            },
            {
                'kinds': [4],
                '#p' : [_current_profile.pub_k]
            }
        ]);

        load_notes();

        // start client for future notes....
        APP.nostr_client.create();
        APP.nostr.gui.pack();

    });
}();