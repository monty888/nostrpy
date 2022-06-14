'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // profiles helper
        _profiles = APP.nostr.data.profiles,
        // main draw area
        _main_con,
        // the search input
        _search_in,
        // delay action using timer
        _search_timer,
        // gui profile list objs
        _profiles_list;

    // start the client TODO: should update any profiles as we see meta events
//    function start_client(){
//        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
//            _client = client;
//        },
//        function(data){
////            _my_event_view.add(data);
//        });
//    }

    function set_list_filter(){
        _profiles_list.set_filter(_search_in.val());
    }

    // start when everything is ready
    $(document).ready(function() {
        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create({
            'enable_media': _enable_media
        });
        // add specifc page scafold
        _main_con = $('#main-con')
        _main_con.css('overflow','hidden');
        _main_con.html(APP.nostr.gui.templates.get('screen-profiles-search'));
        // grab the search button
        _search_in = $('#search-in');

        // init the profiles data
        _profiles.init({
            'on_load' : function(){
                let tool_html = [
                        '<div style="display:table-row">',
                            '<input style="display:table-cell;width:10em;"  placeholder="search" type="text" class="form-control" id="search-in">',
                            '<button id="full_search_but" style="display:table-cell;" type="button" class="btn btn-primary" >' +
                            '</button>',
                        '</div>'
                    ].join('');

                // create list objs
                let keys = [];
                _profiles.all().forEach(function(p){
                    keys.push(p.pub_k);
                });

                _profiles_list = APP.nostr.gui.profile_list.create({
                    'con': $('#profile-list-con'),
                    'profiles' : keys,
                    'view_type': 'contacts',
                    'enable_media': _enable_media
                });

                // finally draw
                _profiles_list.draw();

                _search_in.focus();

                _search_in.on('keyup', function(e){
                    clearTimeout(_search_timer);
                    _search_timer = setTimeout(function(){
                        set_list_filter();
                    },200);
                });

            }
        });

        // to see events as they happen
//        start_client();
    });
}();