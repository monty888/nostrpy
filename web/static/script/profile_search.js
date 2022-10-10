'use strict';

/*
    show all texts type events as they come in
*/
!function(){
    const _user = APP.nostr.data.user;
        // websocket to recieve event updates
    let _client,
        // main draw area
        _main_con,
        // the search input
        _search_in,
        _search_val = '',
        // delay action using timer
        _search_timer,
        // profiles being listed
        _chunk_size = 100,
        _my_tabs,
        _filter_but,
        _tab_objs = [
            {
                'title' : 'people',
                load_func(i,con){
                    _tab_objs[0].con = con;
                    load_profiles();
                }
            },
            {
                'title': 'channels',
                load_func(i,con){
                    _tab_objs[1].con = con;
                    load_channels();
                }
            }
        ],
        _tool_html = [
            '<div class="input-group mb-2" >',
                '<input style="max-width:10em" placeholder="search" type="text" class="form-control" id="search-in">',
                '<button style="padding-top:0px" id="filter_but" type="button" class="btn btn-primary" >' +
                '<svg class="nbi-btn" >',
                    '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#filter-square"/>',
                '</svg>',
                '</button>',
            '</span>'
        ].join(''),
        _current_profile = APP.nostr.data.user.profile(),
        _pub_k = _current_profile.pub_k;

        function reset_tab(tab_obj){
            tab_obj.maybe_more = false;
            tab_obj.c_off = 0;
            tab_obj.data = [];
        }

        function reset_selected_tab(){
            let c_tab = _my_tabs.get_selected_index(),
                tab_obj = _tab_objs[c_tab];

            reset_tab(tab_obj);
            tab_obj.load_func();
        }

        function load_profiles(){
            // our state is held here
            let my_obj = _tab_objs[0];

            my_obj.loading = true;
            let load_str = _search_val;
            APP.nostr.data.profiles.search({
                'use_pub_k': _pub_k,
                'match': _search_val,
                'limit': _chunk_size,
                'include': _user.get(_pub_k+'.profile-search-include', 'everyone'),
                'offset': my_obj.c_off,
                on_load(data){
                    // old load
                    if(_search_val !== load_str){
                        my_obj.loading = false;
                        return;
                    }

                    my_obj.data = my_obj.data.concat(data.profiles);
                    if(my_obj.profiles_list===undefined){
                        try{
                            my_obj.profiles_list = APP.nostr.gui.profile_list.create({
                                'con': my_obj.con,
                                'data' : my_obj.data
                            });
                        }catch(e){
                            console.log(e);
                        }

                    }else{
                        if(my_obj.c_off===0){
                            my_obj.profiles_list.set_data(my_obj.data);
                        }else{
                            my_obj.profiles_list.add_data(data.profiles);
                        }
                    };

                    // for loading more on scroll
                    my_obj.maybe_more = data.profiles.length === _chunk_size;
                    my_obj.c_off += _chunk_size;
                    my_obj.loading = false;

                }
            });
        }

        function load_channels(){
            // our state is held here
            let my_obj = _tab_objs[1];

            if(my_obj.loading===undefined){
                reset_tab(my_obj);
            }
            my_obj.loading = true;
            let load_str = _search_val;
            APP.remote.load_channels({
                'pub_k': _pub_k,
                'include': _user.get(_pub_k+'.channel-search-include', 'anyone'),
                'match': _search_val,
                'limit': _chunk_size,
                'offset': my_obj.c_off,
                success(data){
                    // old load
                    if(_search_val !== load_str){
                        my_obj.loading = false;
                        return;
                    }

                    my_obj.data = my_obj.data.concat(data.channels);
                    if(my_obj.channels_list===undefined){
                        my_obj.channels_list = APP.nostr.gui.channel_list.create({
                            'con': my_obj.con,
                            'data' : my_obj.data
                        });
                    }else{
                        if(my_obj.c_off===0){
                            my_obj.channels_list.set_data(my_obj.data);
                        }else{
                            my_obj.channels_list.add_data(data.channels);
                        }
                    };

                    // for loading more on scroll
                    my_obj.maybe_more = data.channels.length === _chunk_size;
                    my_obj.c_off += _chunk_size;
                    my_obj.loading = false;

                }
            });
        }


    // start when everything is ready
    document.addEventListener('DOMContentLoaded', () => {
        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // add specifc page scafold
        _main_con = _('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-profiles-search'));

        create_tabs();
        init_search();

        function create_tabs(){
            _my_tabs = APP.nostr.gui.tabs.create({
                'con' : _main_con,
                'default_content' : 'loading...',
                'on_tab_change': function(i, con){
                    reset_tab(_tab_objs[i]);
                    _tab_objs[i].load_func(i,con);
                },
                'scroll_bottom': function(i, con){
                    let tab_obj = _tab_objs[i];
                    if(!tab_obj.maybe_more || tab_obj.loading){
                        return;
                    }
                    try{
                        tab_obj.load_func(i,con);
                    }catch(e){
                        console.log(e);
                    }


                },
                'tabs' : _tab_objs
            });
            _main_con.css('overflowY', 'hidden');
            _my_tabs.draw();
            _my_tabs.get_tool_con().html(_tool_html);
            _filter_but = _('#filter_but');
            _filter_but.on('click', (e) => {
                let args = {
                        on_change(){
                            reset_selected_tab();
                        }
                    },
                    c_tab = _my_tabs.get_selected_index();

                if(c_tab===0){
                    APP.nostr.gui.profile_search_filter_modal.show(args);
                }else{
                    APP.nostr.gui.channel_search_filter_modal.show(args);
                }

            });
        }

        function init_search(){
            // grab the search button
            _search_in = _('#search-in');
            _search_in.focus();

            _search_in.on('keyup', function(e){
                _search_val = _search_in.val();
                clearTimeout(_search_timer);
                _search_timer = setTimeout(function(){
                    reset_selected_tab();
                },200);
            });

        }



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
        APP.nostr.gui.pack();

    });
}();