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
        // list container
        _list_con,
        // delay action using timer
        _search_timer,
        // gui profile list objs
        _profiles_list,
        // profiles being listed
        _profiles,
        _maybe_more,
        _c_off,
        _chunk_size = 100,
        _loading=false;

    // start when everything is ready
    document.addEventListener('DOMContentLoaded', () => {
        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // add specifc page scafold
        _main_con = _('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-profiles-search'));
        // grab the search button
        _search_in = _('#search-in');
        _list_con = _('#list-con');

        _search_in.focus();

        _search_in.on('keyup', function(e){
            clearTimeout(_search_timer);
            _search_timer = setTimeout(function(){
                load_profiles(true);
            },200);
        });
        load_profiles(true);

        function load_profiles(is_new){
            _loading = true;
            if(is_new){
                _maybe_more = false;
                _c_off = 0;
                _profiles = [];
            }
            let load_str = _search_in.val();

            APP.nostr.data.profiles.search({
                'match': load_str,
                'limit': _chunk_size,
                'offset': _c_off,
                'on_load' : function(data){
                    // old load
                    if(_search_in.val()!==load_str){
                        _loading = false;
                        return;
                    }

                    _profiles = _profiles.concat(data.profiles);
                    if(_profiles_list===undefined){
                        _profiles_list = APP.nostr.gui.profile_list.create({
                            'con': _list_con,
                            'profiles' : _profiles
                        });
                    }else{
                        if(is_new){
                            _profiles_list.set_data(_profiles);
                        }else{
                            _profiles_list.add_data(data.profiles);
                        }
                    };

                    // for loading more on scroll
                    _maybe_more = data.profiles.length === _chunk_size;
                    _c_off += _chunk_size;
                    _loading = false;
                }
            });
        }

        _list_con.scrollBottom(function(e){
            if(!_maybe_more || _loading){
                return;
            }
            load_profiles();
        });

        // any post/ reply we'll go to the home page
        APP.nostr.data.event.add_listener('post-success', function(type, event){
            event = event.event;
            if(event.kind===1){
                window.location = '/';
            }else if(event.kind===4){
                window.location = '/html/messages.html'
            }
        });
        APP.nostr_client.create();

    });
}();