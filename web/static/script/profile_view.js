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
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // gui objs
        // main container where we'll draw the tabs
        _main_con = $('#main-pane'),
        // about this profile con
        _profile_con = $('#about-pane'),
        // the head obj
        _my_head = APP.nostr.gui.profile_about.create({
            'con': _profile_con,
            'pub_k': _pub_k,
            'enable_media': _enable_media
        }),
        // tab for 2 views of events
        _my_tab = APP.nostr.gui.tabs.create({
            'con' : _main_con,
            'default_content' : 'loading...',
            'on_tab_change': function(i, con){
                if(i===0){
                    if(_post_view===undefined){
                        _post_view = init_view(con, _post_filter);
                        do_load(function(data){
                            _post_view.set_notes(data['events']);
                        }, _post_filter);
                    }
                }else if(i==1){
                    if(_reply_view===undefined){
                        _reply_view = init_view(con, _reply_filter);
                        do_load(function(data){
                            _reply_view.set_notes(data['events']);
                        }, _reply_filter);

                    };
                }
            },
            'tabs' : [
                {
                    'title': 'posts'
                },
                {
                    'title': 'posts & replies'
                }
            ]
        }),
        // only events with current profiles pub_k
        _post_view,
        _post_filter = [{
            'kinds': [1],
            'authors': [_pub_k]
        }],
        // events with profile pub_k or pub_k in p tag of event
        _reply_view,
        _reply_filter = [
            {
                'kinds': [1],
                'authors': [_pub_k]
            },
            {
                'kinds': [1],
                '#p' : [_pub_k]
            }
        ];

    function init_view(con, filter){
        return APP.nostr.gui.event_view.create({
            'con': con,
            'enable_media': _enable_media,
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


    function start_client(){
        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
            _client = client;
        },
        function(data){
            _my_event_view.add(data);
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

    // start when everything is ready
    $(document).ready(function() {
        // start client for future notes....
//        load_notes();
        // draw the tabs
        _my_tab.draw();

        // init the profiles data
        APP.nostr.data.profiles.init({
            'on_load' : function(){
                _my_head.profiles_loaded();
                if(_post_view!==undefined){
                    _post_view.profiles_loaded();
                }

                let name = APP.nostr.util.short_key(_pub_k),
                    cp = APP.nostr.data.profiles.lookup(_pub_k);
                if(cp.attrs.name!==undefined){
                    name = cp.attrs.name;
                }

                document.title = name;
            }
        });
        // to see events as they happen
        start_client();
    });
}();