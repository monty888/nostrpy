'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // key of profile we're editing
        _pub_k = _params.get('pub_k'),
        // main container where we'll draw
        _main_con;


    // start when everything is ready
    $(document).ready(function() {

        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = $('#main-con');


        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){

            }
        });

        APP.nostr.gui.profile_edit.create({
            'con' : _main_con,
            'pub_k': _pub_k
        });

        // our own listeners
        // profile has changed
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            // nothing
        });

        // so we see new events
        APP.nostr.data.event.add_listener('event', function(type, event){
            // nothing
        });

        // any post/ reply we'll go to the home page
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            window.location = '/';
        });

        APP.nostr_client.create();

    });
}();