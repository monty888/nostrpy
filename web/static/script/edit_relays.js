'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // main container where we'll draw out the events
        _main_con,
        _current_con,
        _edit_con,
        _current_profile = APP.nostr.data.user.profile();

    // start when everything is ready
    $(document).ready(function() {

        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = $('#main-con');
        _main_con.css('overflow-y','auto');

        APP.nostr.gui.relay_edit.create({
            'con' : _main_con
        });

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

    });
}();