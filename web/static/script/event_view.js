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
        // main container where we'll draw out the events
        _main_con,
        _my_event_view,
        _current_profile = APP.nostr.data.user.get_profile(),
        _my_filter;

    function create_filter(){
        let filter = [
            {
                'ids' : [_event_id]
            },
            {
                '#e' : [_event_id]
            }
        ];

        if(_root_id!==null){
            filter.push({
                'ids' : [_root_id]
            });
            filter.push({
                '#e' : [_root_id]
            });
        }
        _my_filter = APP.nostr.data.filter.create(filter);
    }

    function load_notes(){
        APP.remote.load_events({
            'filter' : _my_filter,
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
        create_filter();

        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = $('#main-con');
        _main_con.css('overflow-y','auto');
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _main_con,
            'filter' : _my_filter
        });

        // start client for future notes....
        load_notes();
        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){
                _my_event_view.profiles_loaded();
            }
        });


        APP.nostr.gui.post_button.create();
        // our own listeners
        // profile has changed
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(data.pub_k !== _current_profile.pub_k){
                _current_profile = data;
                _my_event_view.draw();
            }
        });

        // so we see new events
        APP.nostr.data.event.add_listener('event', function(type, event){
            _my_event_view.add(event);
        });

        // any post/ reply we'll go to the home page
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            // its just a post better go back to the reply screen
            if(event.type!=='reply'){
                window.location = '/';
            }
        });


        APP.nostr_client.create();

    });
}();