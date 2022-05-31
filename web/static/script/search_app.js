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
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
        // search input
        _search_in = $('#search-in'),
        // take action if we didn't see a key event for set time
        _input_timer,
        // timer before we add current val to history
        _history_timer,
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _text_con,
            'enable_media': _enable_media
        });

    function load_notes(on_done){

        APP.remote.text_events_search({
            'search_str': _search_str===null ? '' : _search_str,
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
        _search_in.val(_search_str);
        // start client for future notes....
        load_notes();
        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){
                _my_event_view.profiles_loaded();
            }
        });

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

        // maybe just do a periodic refresh as otherwise we'd have to duplicate a fulltext seach in the client
        // that gives the same results as we get via backend...
        // to see events as they happen
        // start_client();

        window.addEventListener('popstate', function (e) {
            _search_str = e.state['search_str'];
            _search_in.val(_search_str);
            load_notes();
        });


    });
}();