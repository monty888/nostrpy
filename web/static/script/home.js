'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        _views = {},
        _current_profile,
        _main_con,
        _global_filter = APP.nostr.data.filter.create({
            'kinds' : [1]
        }),
        _my_tabs,
        _chunk_size = 50;

    function home_view(){
        // kill old views if any
        _views = {};

        let post_filter = APP.nostr.data.filter.create([{
                'kinds': [1],
                'authors': [_current_profile.pub_k]
            }]),
            reply_filter = APP.nostr.data.filter.create([
                {
                    'kinds': [1],
                    'authors': [_current_profile.pub_k]
                },
                {
                    'kinds': [1],
                    '#p' : [_current_profile.pub_k]
                }
            ]),
            // the tabs also the data needed to load
            tabs_objs = [
                {
                    'title' : 'global',
                    'filter' : _global_filter,
                    'load_func' : function (success){
                        do_load(success, _global_filter);
                    }
                },
                {
                    'title' : 'feed',
                    'active' : true,
                    'load_func' : function(success){
                        APP.remote.load_notes_from_profile({
                            'pub_k' : _current_profile.pub_k,
                            'success': function(data){
                                // nasty, but we don't know the filter till we loaded the data
                                _views[1].set_filter(APP.nostr.data.filter.create(data['filter']));
                                success(data);
                            }
                        });
                    }
                },
                {
                    'title' : 'post & replies',
                    'filter' : reply_filter,
                    'load_func' : function (success){
                        do_load(success, reply_filter);
                    }
                },
                {
                    'title' : 'posts',
                    'filter' : post_filter,
                    'load_func' : function (success){
                        do_load(success, post_filter);
                    }
                }
            ];

            _my_tabs = APP.nostr.gui.tabs.create({
                'con' : _main_con,
                'default_content' : 'loading...',
                'on_tab_change': function(i, con){
                    if(_views[i]===undefined){
                        _views[i] = init_view(con, tabs_objs[i].filter);
                        tabs_objs[i].load_func(function(data){
                            _views[i].set_notes(data['events']);
                        })
                    }

                },
                'tabs' : tabs_objs
            });

        _main_con.css('overflowY', 'hidden');
        _my_tabs.draw();
    }

    // when using lurker
    function global_only_view(){
        _views = {};
        _main_con.css('overflowY', 'scroll');
        _views['global'] = init_view(_main_con, _global_filter);
        do_load(function(data){
            try{
                _views['global'].set_notes(data['events']);
            }catch(e){
                console.log(e);
            }

        },_global_filter);
    }

    function init_view(con, filter){
        return APP.nostr.gui.event_view.create({
            'con': con,
            'filter' : filter
        });
    }

    function do_load(success, filter){
        APP.remote.load_events({
            'filter' : filter,
            // maybe at somepoint see if we can reduce loads by tracking changes
            'cache' : false,
            'limit': _chunk_size,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else if(typeof(success)==='function'){
                    success(data);
                }
            }
        });
    }

    document.addEventListener('DOMContentLoaded', ()=> {
        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));

        APP.nostr.gui.header.create();
        // main container where we'll draw out the events
        _main_con = _('#main-con');
//        _main_con.css('height','100%');

//        _main_con.css('max-height','100%');
        _current_profile = APP.nostr.data.user.profile();

        function render_screen(){
            if(_current_profile.pub_k!==undefined){
                home_view();
            // if not logged in then just global events, maybe add a popular based on profile follower ranks
            }else{
                global_only_view();
            }
        }

        _main_con.scrollBottom(function(e){
            if(_current_profile.pub_k===undefined){
//                alert('mofo!!!');
            }
        });


        APP.nostr.gui.post_button.create();

        // our own listeners
        // profile has changed
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(data.pub_k !== _current_profile.pub_k){
                _current_profile = data;
                render_screen();
            }
        });

        APP.nostr.data.event.add_listener('home',function(of_type, data){
            if(_my_tabs){
                _my_tabs.set_selected_tab(1);
            }
        });

        // saw a new events
        APP.nostr.data.event.add_listener('event', function(type, event){
            for(let i in _views){
                _views[i].add(event)
            }
        });

        render_screen();
        APP.nostr_client.create();

    });

}();