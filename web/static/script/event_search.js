'use strict';

/*
    show all texts type events as they come in
*/
!function(){
    const // location so we can keep state
        _url = new URL(window.location);
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        _search_str = _params.get('search_str')===null ? '' : _params.get('search_str'),

        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // area for everything we draw
        _main_con,
        // main container where we'll draw out the events
        _list_con,
        // search input
        _search_in,
        // take action if we didn't see a key event for set time
        _input_timer,
        // timer before we add current val to history
        _history_timer,
        _my_event_view,
        _current_profile = APP.nostr.data.user.profile();

    function load_notes(on_done){

        APP.remote.text_events_search({
            // #>. because otherwise we'll lose it somewhere on teh way to the server because it's a specual char
            // nasty but will do for now...
            'search_str': _search_str===null ? '' : encodeURIComponent(_search_str),
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
    document.addEventListener('DOMContentLoaded', () => {
        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create({});
        // add specifc page scafold
        _main_con = _('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-events-search'));

        _search_in = _('#search-in');
        _search_in.val(_search_str);
        _search_in.focus();
        _list_con = _('#list-con');
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _list_con
        });

        // start client for future notes....
        load_notes();

        _search_in.on('keyup', function(e){
            clearTimeout(_input_timer);
            clearTimeout(_history_timer);

            // load notes if no new key for 250ms
            _input_timer = setTimeout(function(){
                _search_str = _search_in.val();
                load_notes();
            },250);
            // save the history if no new key for 1sec
            _history_timer = setTimeout(function(){
                _url.searchParams.set('search_str', _search_str);
                window.history.pushState({
                    'search_str': _search_str
                }, '', _url);
            },1000);
        });

        window.addEventListener('popstate', function (e) {
            _search_str = e.state['search_str'];
            _search_in.val(_search_str);
            load_notes();
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

        // saw a new events
        APP.nostr.data.event.add_listener('event', function(type, event){

//            _my_event_view.draw();
        });

        // any post/ reply we'll go to the home page
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            window.location = '/';
        });

        // for relay updates, note this screen is testing events as they come in
        APP.nostr_client.create();


    });
}();