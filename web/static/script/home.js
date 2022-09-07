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
        _chunk_size = 100;

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
                    'load_func' : do_load
                },
                {
                    'title' : 'feed',
                    'active' : true,
                    'load_func' : function(success){
                        let args = {
                            'pub_k' : _current_profile.pub_k,
                            'success': function(data){
                                let view = _views[1];
                                view.loading = true;
                                // nasty, but we don't know the filter till we loaded the data
                                view.filter(APP.nostr.data.filter.create(data['filter']));
                                set_view_loaded_data(view, data);
                            }
                        };

                        if(_views[1].until!==null){
                            args['until'] = _views[1].until;
                        }

                        APP.remote.load_notes_from_profile(args);
                    }
                },
                {
                    'title' : 'post & replies',
                    'filter' : reply_filter,
                    'load_func' : do_load
                },
                {
                    'title' : 'posts',
                    'filter' : post_filter,
                    'load_func' : do_load
                }
            ];

            _my_tabs = APP.nostr.gui.tabs.create({
                'con' : _main_con,
                'default_content' : 'loading...',
                'on_tab_change': function(i, con){
                    if(_views[i]===undefined){
                        _views[i] = init_view(con,
                            tabs_objs[i].filter,
                            tabs_objs[i].load_func);

                        _views[i].load_func(_views[i]);
                    }
                },
                'scroll_bottom': function(){
                    let tab = _my_tabs.get_selected_index(),
                        view = _views[tab];
                    view_scroll(view);
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
        _views['global'] = init_view(_main_con, _global_filter, function(){
            do_load(_views['global']);
        });
        do_load(_views['global']);
    }

    function init_view(con, filter, load_func){
        let ret = APP.nostr.gui.event_view.create({
            'con': con,
            'filter' : filter
        });

        //tack on some extra properties to track scroll
        ret.maybe_more = false;
        ret.until = null;
        ret.events = [];
        ret.load_func = load_func;
        return ret;
    }

    function do_load(view){
        view.loading = true;
        let filter = view.filter().as_object();
        if(view.until!==null){
            filter.forEach(function(c_f,i){
                c_f.until = view.until;
            });
        }

        filter = APP.nostr.data.filter.create(filter);;

        APP.remote.load_events({
            'filter' : filter,
            // maybe at somepoint see if we can reduce loads by tracking changes
            'cache' : false,
            'limit': _chunk_size,
            'success': function(data){
                set_view_loaded_data(view, data);
            }
        });
    }

    function set_view_loaded_data(view, data){
        if(data['error']!==undefined){
            alert(data['error']);
        }else{
            if(view.events.length==0){
                view.events = data.events;
                view.set_notes(view.events);
            // onwards scroll
            }else{
                view.events = view.events.concat(data.events);
                view.append_notes(data.events);
            }
            view.maybe_more = data.events.length === _chunk_size;
        }
        view.loading = false;
    }

    function view_scroll(view){
        if(view.events===undefined || !view.maybe_more || view.loading===true){
            return;
        }
        view.until = null;
        if(view.events.length>0){
            view.until = view.events[view.events.length-1].created_at-1;
        }
        view.load_func(view);
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

        // scroll for global only view (lurker)
        _main_con.scrollBottom(function(e){
            let view;
            if(_current_profile.pub_k===undefined){
                view_scroll(_views['global']);
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