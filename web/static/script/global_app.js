'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _text_con,
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

        APP.remote.load_events({
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
                _my_event_view.profiles_loaded();
            }
        });
        // to see events as they happen
        start_client();

    }).on('click', function(e){
        let id = APP.nostr.gui.get_clicked_id(e),
            parts,
            p_idents = new Set(['pp','pt']);

        if(id!==null){
            parts = id.split('-');
            if(parts.length>1 && p_idents.has(parts[1])){
                location.href = '/html/profile?pub_k='+parts[0];
            }

        }
    });
}();