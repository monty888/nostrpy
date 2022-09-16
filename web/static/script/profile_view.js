'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        _pub_k = _params.get('pub_k'),
        // main render area
        _main_con,
        // main container where we'll draw the tabs
        _tab_con,
        // about profile header rendered here
        _profile_con,
        // about profile obj
        _my_head,
        // tab for 2 views of events
        _my_tab,
        // only events with current profiles pub_k
        _post_view,
        _post_filter = APP.nostr.data.filter.create([{
            'kinds': [1],
            'authors': [_pub_k]
        }]),
        // events with profile pub_k or pub_k in p tag of event
        _reply_view,
        _reply_filter = APP.nostr.data.filter.create([
            {
                'kinds': [1],
                'authors': [_pub_k]
            },
            {
                'kinds': [1],
                '#p' : [_pub_k]
            }
        ]),
        // as the user we're looking at sees things
        _feed_view,
        _feed_filter,
        _reaction_view,
        _current_profile = APP.nostr.data.user.profile(),
        _profiles = APP.nostr.data.profiles,
        _chunk_size = 100;

    function do_load(view){
        view.loading = true;
        let filter = view.filter().as_object();
        if(view.until!==null){
            filter.forEach(function(c_f,i){
                c_f.until = view.until;
            });
        }

        filter = APP.nostr.data.filter.create(filter);
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

    // create screen, grabing various els as needed along the way
    function create_screen(){
        // main page struc
        _('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // add specifc page scafold
        _main_con = _('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-profile-view'));

        // this should now exist
        _profile_con = _('#about-pane');
        _tab_con = _('#tab-pane');

        // event tabs for this profile
        create_tabs();

    }

    function create_tabs(){
        _my_tab = APP.nostr.gui.tabs.create({
            'con' : _tab_con,
            'default_content' : 'loading...',
            'on_tab_change': function(i, con){
                if(i===0){
                    if(_post_view===undefined){
                        _post_view = init_view(con, _post_filter, function(){
                            do_load(_post_view);
                        });
                        _post_view.load_func();
                    }
                }else if(i===1){
                    if(_reply_view===undefined){
                        _reply_view = init_view(con, _reply_filter, function(){
                            do_load(_reply_view);
                        });
                        _reply_view.load_func();
                    };
                // feed tab
                }else if(i===2 && _feed_view===undefined){
                    _feed_view = init_view(con, null, () => {
                        _feed_view.loading = true;
                        let args = {
                            'pub_k' : _pub_k,
                            'limit': _chunk_size,
                            'success': function(data){
                                // nasty, but we don't know the filter till we loaded the data
                                _feed_view.filter(APP.nostr.data.filter.create(data['filter']));
                                set_view_loaded_data(_feed_view, data);
                            }
                        };

                        if(_feed_view.until!==null){
                            args['until'] = _feed_view.until;
                        };

                        APP.remote.load_notes_for_profile(args);
                    });
                    _feed_view.load_func();
                }else if(i==3){

                    // atleast for now no filter.. we could see the likes but then we'd still have to go and
                    // grab the actual event
                    _reaction_view = init_view(con, null, ()=>{
                        _reaction_view.loading = true;
                         let args = {
                            'pub_k' : _pub_k,
                            'limit': _chunk_size,
                            'success': function(data){
                                set_view_loaded_data(_reaction_view, data);
                            }
                        };
                        if(_reaction_view.until!==null){
                            args['until'] = _reaction_view.until;
                        };

                        APP.remote.load_reactions(args);
                    });
                    _reaction_view.load_func();



                }
            },
            'tabs' : [
                {
                    'title': 'posts'
                },
                {
                    'title': 'posts & replies'
                },
                {
                    'title': 'feed'
                },
                {
                    'title': 'reactions'
                }
            ],
            scroll_bottom(){
                let tab = _my_tab.get_selected_index(),
                    views = [_post_view, _reply_view, _feed_view, _reaction_view],
                    view = views[tab];
                view_scroll(view);
            }

        })

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




    // start when everything is ready
    document.addEventListener('DOMContentLoaded', () => {
        create_screen();

        // start client for future notes....
//        load_notes();
        // draw the tabs
        _my_tab.draw();


        _profiles.fetch({
            'pub_ks' : [_pub_k],
            'on_load' : function(){
                let name = APP.nostr.util.short_key(_pub_k),
                    cp = _profiles.lookup(_pub_k);

                if(cp.attrs.name!==undefined){
                    name = cp.attrs.name;
                }

                document.title = name;
                // profile about head
                _my_head = APP.nostr.gui.profile_about.create({
                    'con': _profile_con,
                    'pub_k': _pub_k
                });


            }
        });
//        profiles.init();

        // our own listeners
        // profile has changed
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(data.pub_k !== _current_profile.pub_k){
                _current_profile = data;

                _post_view !== undefined ? _post_view.draw() : false;
                _reply_view !== undefined ? _reply_view.draw(): false;
            }
        });

        // saw a new events
        APP.nostr.data.event.add_listener('event', function(type, event){

//            _my_event_view.draw();
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

        // for relay updates, note this screen is testing events as they come in
        APP.nostr.gui.post_button.create();
        APP.nostr_client.create();

    });
}();