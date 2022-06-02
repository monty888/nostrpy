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
        // profiles helper
        _profiles = APP.nostr.data.profiles,
        // tab for contacts/follow/search/+ rendered here
        _contacts_con = $('#contact-tabs'),
        _my_tab = APP.nostr.gui.tabs.create({
            'con' : _contacts_con,
            'default_content' : 'loading...',
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


    // start the client
    function start_client(){
        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
            _client = client;
        },
        function(data){
//            _my_event_view.add(data);
        });
    }

    // start when everything is ready
    $(document).ready(function() {
        if(_pub_k===null){
            alert('no pub_k supplied');
            return;
        }
        // default to view contacts if no viewtype given
        _view_type = _view_type===undefined ? 'contacts' : _view_type;

        // init the profiles data
        _profiles.init({
            'for_profile' : _pub_k,
            'on_load' : function(){
                _my_tab.draw();
                let contact_tab = _my_tab.get_tab(0),
                    follow_tab= _my_tab.get_tab(1),
                    contacts_list = APP.nostr.gui.profile_list.create({
                        'con': contact_tab['content-con'],
                        'pub_k': _pub_k,
                        'view_type': 'contacts',
                        'enable_media': _enable_media
                    }),
                    followers_list = APP.nostr.gui.profile_list.create({
                        'con': follow_tab['content-con'],
                        'pub_k': _pub_k,
                        'view_type': 'followers',
                        'enable_media': _enable_media
                    });


                // finally draw
                contacts_list.draw();
                followers_list.draw();


            }
        });

        // to see events as they happen
        start_client();
    });
}();