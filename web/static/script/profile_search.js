'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // main draw area
        _main_con,
        // the search input
        _search_in,
        // delay action using timer
        _search_timer,
        // gui profile list objs
        _profiles_list,
        // profiles being listed
        _profiles,
        // create the search in
        _search_html = [
            '<div style="display:table-row">',
                '<input style="display:table-cell;width:10em;"  placeholder="search" type="text" class="form-control" id="search-in">',
                '<button id="full_search_but" style="display:table-cell;" type="button" class="btn btn-primary" >' +
                '</button>',
            '</div>'
        ].join('');

    function set_list_filter(){
        _profiles_list.set_filter(_search_in.val());
    }

    // start when everything is ready
    $(document).ready(function() {
        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // add specifc page scafold
        _main_con = $('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-profiles-search'));
        // grab the search button
        _search_in = $('#search-in');

        try{
            APP.nostr.data.profiles.search({
                'on_load' : function(data){
                    _profiles = data.profiles;
                    _profiles_list = APP.nostr.gui.profile_list.create({
                        'con': $('#list-con'),
                        'profiles' : _profiles
                    });
                    // finally draw
//                    _profiles_list.draw();

                    _search_in.focus();

                    _search_in.on('keyup', function(e){
                        clearTimeout(_search_timer);
                        _search_timer = setTimeout(function(){
                            set_list_filter();
                        },200);
                    });
                }
            });
        }catch(e){
            console.log(e)
        }

        // for relay updates
//        APP.nostr_client.create();

    });
}();