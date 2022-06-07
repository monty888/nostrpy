'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // event we want to look at
        _event_id = _params.get('id'),
        // where we clicked to this page and the root wasn't visible we add it so
        // hopefully to put the post in somesort of context
        _root_id = _params.get('root'),
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _text_con,
            'enable_media': _enable_media
        });

    function start_client(){
        APP.nostr_client.create({
            'on_open':function(client){
                _client = client;
            },
            'on_data':function(data){
                _my_event_view.add(data);
            }
        });
    }

    function load_notes(){
        let filter = [
            {
                'kinds' :[1],
                'ids' : [_event_id]
            },
            {
                'kinds' :[1],
                '#e' : [_event_id]
            }
        ];

        if(_root_id!==null){
            filter.push({
                'kinds' :[1],
                'ids' : [_root_id]
            });
            filter.push({
                'kinds' :[1],
                '#e' : [_root_id]
            });
        }
        console.log(filter);

        APP.remote.load_events({
            'filter' : filter,
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
        if(_event_id===''){
            alert('no event id!!!');
            return;
        }
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
    });
}();