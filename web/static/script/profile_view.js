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
        _current_profile = APP.nostr.data.user.profile(),
        _profiles = APP.nostr.data.profiles;

    function init_view(con, filter){
        return APP.nostr.gui.event_view.create({
            'con': con,
            'filter' : filter
        });
    }

    function do_load(success, filter){
        APP.remote.load_events({
            'filter' : filter,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    success(data);
                }
            }
        });
    }

    function load_notes(){
        if(_pub_k===null){
            alert('no pub_k supplied');
        }

        APP.remote.load_notes_from_profile({
            'pub_k' : _pub_k,
            'success': function(data){
                try{
                    if(data['error']!==undefined){
                        alert(data['error']);
                    }else{
                        _my_event_view.set_notes(data['events']);
                    }
                }catch(e){
                    console.log(e)
                }
            }
        });
    }

    // create screen, grabing various els as needed along the way
    function create_screen(){
        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create();
        // add specifc page scafold
        _main_con = $('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-profile-view'));

        // this should now exist
        _profile_con = $('#about-pane');
        _tab_con = $('#tab-pane');

        // profile about head
        _my_head = APP.nostr.gui.profile_about.create({
            'con': _profile_con,
            'pub_k': _pub_k
        });

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
                        _post_view = init_view(con, _post_filter);
                        do_load(function(data){
                            _post_view.set_notes(data['events']);
                        }, _post_filter);
                    }
                }else if(i===1){
                    if(_reply_view===undefined){
                        _reply_view = init_view(con, _reply_filter);
                        do_load(function(data){
                            _reply_view.set_notes(data['events']);
                        }, _reply_filter);

                    };
                // feed tab
                }else if(i===2){
                    _feed_view = init_view(con);
                    APP.remote.load_notes_from_profile({
                        'pub_k' : _pub_k,
                        'success': function(data){
                            // nasty, but we don't know the filter till we loaded the data
                            _feed_view.set_filter(APP.nostr.data.filter.create(data['filter']));
                            _feed_view.set_notes(data['events']);
                        }
                    });
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
                }
            ]
        })

    }


    // start when everything is ready
    $(document).ready(function() {
        create_screen();

        // start client for future notes....
//        load_notes();
        // draw the tabs
        _my_tab.draw();

        // init the profiles data
//        APP.nostr.data.profiles.init({
//            'on_load' : function(){
//                _my_head.profiles_loaded();
//
//                if(_post_view!==undefined){
//                    _post_view.profiles_loaded();
//                }
//
//                let name = APP.nostr.util.short_key(_pub_k),
//                    cp = APP.nostr.data.profiles.lookup(_pub_k);
//                if(cp.attrs.name!==undefined){
//                    name = cp.attrs.name;
//                }
//
//                document.title = name;
//            }
//        });


        _profiles.fetch({
            'pub_ks' : [_pub_k],
            'on_load' : function(){
                let name = APP.nostr.util.short_key(_pub_k),
                    cp = _profiles.lookup(_pub_k);

                if(cp.attrs.name!==undefined){
                    name = cp.attrs.name;
                }

                document.title = name;
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
        APP.nostr_client.create();
        APP.nostr.gui.post_button.create();


    });
}();