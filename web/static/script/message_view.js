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
                    try{
                        _main_con.html('<div style="position:sticky;top: 0;width:100%;background-color:black">stuff here</div><div id="msgs" ></div>');
                        _my_view = APP.nostr.gui.dm_list.create({
                            'con' : _('#msgs'),
                            'events' : data['events']
                        });
                    }catch(e){
                        console.log(e);
                    }
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

        // any post
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            // its just a post better go back to the reply screen
            if(event.type!=='reply'){
                window.location = '/';
            }
        });

        // start client for future notes....
        APP.nostr_client.create();
        APP.nostr.gui.pack();

    });
}();