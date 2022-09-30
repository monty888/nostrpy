'use strict';
/*
    view channel messages, this is done in opposite direction of general posts which on done more twitter like with
    newest at top. Here we do telegram like, the newest message will be at the bottom and there should be a text area
    for us to post, replies should quote rather than thread and clicking that reply should focus back to that msg
*/
!function(){
    const _user = APP.nostr.data.user,
        _filter = APP.nostr.data.filter;
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // channel to view
        _channel_id = _params.get('channel_id'),
        // main container where we'll draw out the events
        _main_con,
        _chunk_size = 100,
        _loading,
        _maybe_more,
        _until = null,
        _current_profile = _user.profile(),
        _events = [],
        _my_list,
        _my_filter = _filter.create({
            'kinds': [42],
            '#e': [_channel_id]
        });

    function load_messages(){
        _loading = true;
        let c_filter = _my_filter;

        if(_until!==null){
            c_filter = _my_filter.as_object();
            c_filter[0].until = _until;
            _my_filter = _filter.create(c_filter);
        }

        APP.remote.load_events({
            'filter' : _my_filter,
            'limit': _chunk_size,
            'pub_k' : _current_profile.pub_k,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    let sorted_data = data.events;
                    sorted_data.sort((a,b) => {
                        return a.created_at - b.created_at;
                    });
                    if(_my_list===undefined){
                        _my_list = APP.nostr.gui.channel_view_list.create({
                            'con': _main_con,
                            'data': sorted_data
                        });

                    }else{
                        _my_list.prepend_data(sorted_data);
                    }

                    if(_events.length===0){
                        _events = sorted_data;
                    }else{
                        _events = sorted_data.concat(_events);
                    }
                }
                _maybe_more = data.events.length === _chunk_size;
                _loading = false;
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
            if(_maybe_more){
                _until = _events[0].created_at-1;
                load_messages();
            }
        });

        load_messages();

        APP.nostr_client.create();

    });
}();