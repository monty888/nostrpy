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
        // either viewing followers or contacts, default to contacts if not supplied
        _view_type = _params.get('view_type'),
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // profile we're looking at
        _profile,
        // tab for contacts/follow/search/+ rendered here
        _contacts_con,
        _my_tab,
        _main_con,
        // the search input
        _search_in,
        // delay action using timer
        _search_timer,
        // gui profile list objs
        _contacts_list,
        _followers_list,
        // about this profile con
        _profile_con,
        // the head obj
        _my_head;


    // start the client
//    function start_client(){
//        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
//            _client = client;
//        },
//        function(data){
////            _my_event_view.add(data);
//        });
//    }

    function create_tabs(){
        _contacts_con = $('#contact-tabs');
        _my_tab = APP.nostr.gui.tabs.create({
            'con' : _contacts_con,
            'default_content' : 'loading...',
            'on_tab_change': function(i){
                set_list_filter();
            },
            'tabs' : [
                {
                    'title': 'follows',
                    'active': _view_type!=='followers'
                },
                {
                    'title': 'followers',
                    'active': _view_type==='followers'
                }
            ]
        });
    }

    function add_search(){
        let tool_html = [
//            '<div style="display:table-row">',
//                '<input style="display:table-cell;width:8em;"  placeholder="search" type="text" class="form-control" id="search-in">',
//                '<button id="full_search_but" style="display:table-cell;" type="button" class="btn btn-primary" >' +
//                '<svg class="bi" >',
//                    '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-plus-fill"/>',
//                '</svg>',
//                '</button>',
//            '</div>'
            '<span style="max-height:100%;float:right;">',
                '<input style="display:table-cell;width:8em;"  placeholder="search" type="text" class="form-control" id="search-in">',
                '<button id="full_search_but" style="display:table-cell;" type="button" class="btn btn-primary" >' +
                '<svg class="bi" >',
                    '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-plus-fill"/>',
                '</svg>',
                '</button>',
            '</span>'


            ].join('');

        _my_tab.get_tool_con().html(tool_html);
        _search_in = $('#search-in');
        _search_in.focus();

        _search_in.on('keyup', function(e){
            clearTimeout(_search_timer);
            _search_timer = setTimeout(function(){
                set_list_filter();
            },200);
        });

        // takes us to a page where we can search for all profiles not just currently looking at profile
        $('#full_search_but').on('click', function(){
            location.href = '/html/profile_search.html';
        });
    }

    function set_list_filter(){
        let list = _my_tab.get_selected_index()===0 ? _contacts_list : _followers_list;
            if(list!==undefined){
                list.set_filter(_search_in.val());
            }
    };

    // start when everything is ready
    $(document).ready(function() {
        if(_pub_k===null){
            alert('no pub_k supplied');
            return;
        }

        // default to view contacts if no viewtype given
        _view_type = _view_type===undefined ? 'contacts' : _view_type;

        // main page struc
        $('#main_container').html(APP.nostr.gui.templates.get('screen'));
        APP.nostr.gui.header.create({});
        // get the main con and render page specific scafold
        _main_con = $('#main-con');
        _main_con.html(APP.nostr.gui.templates.get('screen-contact-view'));
        _profile_con = $('#about-con');

        // create follow/ers tabs
        create_tabs();
        APP.remote.load_profile({
            'pub_k': _pub_k,
            'include_followers': true,
            'include_contacts': true,
            'full_profiles' : true,
            'success' : function(data){
                _profile = data;
                _my_head = APP.nostr.gui.profile_about.create({
                    'con': _profile_con,
                    'profile': _profile,
                    'show_follows': false
                });

                // hack to make contact profiles available by lookup, should be transparent to use really
                APP.nostr.data.profiles.put(_profile);
                _profile.contacts.forEach(function(c_p){
                    APP.nostr.data.profiles.put(c_p);
                })
                //

                _my_tab.draw();
                add_search();

                let contact_tab = _my_tab.get_tab(0),
                    follow_tab= _my_tab.get_tab(1);

                // create list objs
                _contacts_list = APP.nostr.gui.profile_list.create({
                    'con': contact_tab['content-con'],
                    'profiles': _profile.contacts,
                    'view_type': 'contacts'
                });
                _followers_list = APP.nostr.gui.profile_list.create({
                    'con': follow_tab['content-con'],
                    'profiles': _profile.followed_by,
                    'view_type': 'followers'
                });

            }
        });
        APP.nostr_client.create();
    });
}();