'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        _pub_k = _params.get('pub_k'),
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // gui objs
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
        // the feed obj
        _my_event_view = APP.nostr.gui.event_view.create({
            'con': _text_con,
            'enable_media': _enable_media,
            'filter' : {
                'kinds': new Set([1]),
                'authors': new Set([_pub_k])
            }
        }),
        // about this profile con
        _profile_con = $('#about-pane'),
        // the head obj
        _my_head = APP.nostr.gui.profile_about.create({
            'con': _profile_con,
            'pub_k': _pub_k,
            'enable_media': _enable_media
        });

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

    // start when everything is ready
    $(document).ready(function() {
        // start client for future notes....
        load_notes();
        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){
                _my_head.profiles_loaded({
                    'pub_k' : _pub_k
                });
                _my_event_view.profiles_loaded();
                let name = APP.nostr.util.short_key(_pub_k),
                    cp = APP.nostr.data.profiles.lookup(_pub_k);
                if(cp.attrs.name!==undefined){
                    name = cp.attrs.name;
                }

                document.title = name;
            }
        });
        // to see events as they happen
        start_client();
    });
}();