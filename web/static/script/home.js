'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // websocket to recieve event updates
    let _client,
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        _views = {},
        _current_profile,
        _main_con;

    function start_client(){
        APP.nostr_client.create({
            'on_data' : function(data){
                for(let i in _views){
                    _views[i].add(data)
                }
            }
        });
    }

    function home_view(){
        // kill old views if any
        _views = {};

        let global_filter = {
                'kinds': [1]
            },
            feed_filter = {},
            post_filter = [{
                'kinds': [1],
                'authors': [_current_profile.pub_k]
            }],
            reply_filter = [
                {
                    'kinds': [1],
                    'authors': [_current_profile.pub_k]
                },
                {
                    'kinds': [1],
                    '#p' : [_current_profile.pub_k]
                }
            ],
            // the tabs also the data needed to load
            tabs_objs = [
                {
                    'title' : 'global',
                    'filter' : global_filter,
                    'load_func' : function (success){
                        do_load(success, global_filter);
                    }
                },
                {
                    'title' : 'feed',
                    'active' : true,
                    'load_func' : function(success){
                        APP.remote.load_notes_from_profile({
                            'pub_k' : _current_profile.pub_k,
                            'success': function(data){
                                feed_filter = data['filter'];
                                success(data);
                            }
                        })
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
            ],
            tabs_gui = APP.nostr.gui.tabs.create({
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

        _main_con.css('overflow-y','hidden');
        tabs_gui.draw();
    }

    // when using lurker
    function global_only_view(){
        _main_con.css('overflow-y','scroll');
        _views['global'] = init_view(_main_con, {});
        do_load(function(data){
            _views['global'].set_notes(data['events']);
        },{});
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
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else if(typeof(success)==='function'){
                    success(data);
                }
            }
        });
    }


    // start when everything is ready
    $(document).ready(function() {
        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create({
            'enable_media': APP.nostr.data.user.enable_media()
        });
        // main container where we'll draw out the events
        _main_con = $('#main-con');
//        _main_con.css('height','100%');

//        _main_con.css('max-height','100%');
        _current_profile = APP.nostr.data.user.get_profile();

        function render_screen(){
            if(_current_profile.pub_k!==undefined){
                home_view();
            // if not logged in then just global events, maybe add a popular based on profile follower ranks
            }else{
                global_only_view();
            }
        }

        // if profile changes then we have to redraw everything...
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(data.pub_k !== _current_profile.pub_k){
                _current_profile = data;
                render_screen();
            }
        });

        APP.nostr.gui.post_button.create();


        render_screen();
        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){
                for(let c_v in _views){
                    _views[c_v].profiles_loaded();
                }
            }
        });
        // so we see new events
        start_client();


    });
}();