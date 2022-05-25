'use strict';

/*
    show all texts type events as they come in
*/
!function(){
    // websocket to recieve event updates
    let _client,
    // gui objs
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
        // url params
        _params = new URLSearchParams(window.location.search),
        _pub_k = _params.get('pub_k'),
    // data
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _text_con
        }),
    // inline media where we can, where false just the link is inserted
        _enable_media = true;

    function start_client(){
        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
            _client = client;
        },
        function(data){
            _my_event_view.add(data);
        });
    }

    function load_notes(){
        if(_pub_k===null){
            alert('no pub_k supplied');
        }

        APP.remote.load_notes_from_profile({
            'pub_k' : _pub_k,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    _my_event_view.set_notes(data['events']);
                }
            }
        });
    }

    function load_profiles(){
        APP.remote.load_profiles(function(data){
            _my_event_view.set_profiles(data['profiles']);
        });
    }

    // start when everything is ready
    $(document).ready(function() {
        // start client for future notes....
        load_notes();
        // obvs this way of doing profile lookups isn't going to scale...
        load_profiles();
        // to see events as they happen
        start_client();
    });
}();