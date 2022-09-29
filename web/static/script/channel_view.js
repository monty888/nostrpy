'use strict';
/*
    view channel messages, this is done in opposite direction of general posts which on done more twitter like with
    newest at top. Here we do telegram like, the newest message will be at the bottom and there should be a text area
    for us to post, replies should quote rather than thread and clicking that reply should focus back to that msg
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // channel to view
        _channel_id = _params.get('channel_id'),
        // main container where we'll draw out the events
        _main_con,
        _current_profile = APP.nostr.data.user.profile(),
        _my_filter = APP.nostr.data.filter.create({
            'kind': 42,
            '#e': [_channel_id]
        });

    function load_messages(){
        APP.remote.load_events({
            'filter' : _my_filter,
            'pub_k' : _current_profile.pub_k,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    let sorted_data = data.events;
                    sorted_data.sort((a,b) => {
                        return a.created_at - b.created_at;
                    });

                    APP.nostr.gui.channel_view_list.create({
                        'con': _main_con,
                        'data': sorted_data
                    });

                }
            }
        });
    }

    // start when everything is ready
    document.addEventListener('DOMContentLoaded', ()=> {
        if(_channel_id===null){
            alert('channel_id is required!!!');
            return;
        }

        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = _('#main-con');
        _main_con.css('overflowY','auto');
        _main_con.scrolledTop(function(){
            alert('top dude!!!');
        });

        load_messages();

        APP.nostr_client.create();

    });
}();