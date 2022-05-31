'use strict';

/*
    show all texts type events as they come in
*/
!function(){
        // lib shortcut
    let _gui = APP.nostr.gui,
        // websocket to recieve event updates
        _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        _pub_k = _params.get('pub_k'),
        // either viewing followers or contacts, default to contacts if not supplied
        _view_type = _params.get('view_type'),
        // inline media where we can, where false just the link is inserted
        _enable_media = true,
        // gui objs
        // main container where we'll draw out the followers/contacts
        _contacts_con = $('#contact-list-pane'),
        // shortcut
        _profiles = APP.nostr.data.profiles,
        // template for profile output
        _row_tmpl = [
            '{{#profiles}}',
                '<div id="{{pub_k}}-pubk" style="padding-top:2px;cursor:pointer">',
                    '<span style="display:table-cell;height:128px;width:128px; background-color:#111111;padding-right:10px;" >',
                        // TODO: do something if unable to load pic
                        '{{#picture}}',
                            '<img src="{{picture}}"  class="profile-pic-large"/>',
                        '{{/picture}}',
                    '</span>',
                    '<span style="height:128px;width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                        '<span style="color:cyan">{{pub_k}}</span><br>',
                        '{{#name}}',
                            '<div>',
                                '<span style="display:inline-block; width:100px; font-weight:bold;">name: </span><span>{{name}}</span>',
                            '</div>',
                        '{{/name}}',
                        '{{#about}}',
                            '<div>',
                                '<span style="display:table-cell; width:100px; font-weight:bold;">about: </span><span style="display:table-cell">{{{about}}}</span>',
                            '</div>',
                        '{{/about}}',
                    '</span>',
                '</div>',
            '{{/profiles}}'
        ].join('');

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
                let my_p = _profiles.lookup(_pub_k);
                my_p.load_contact_info(function(){
                    let render_obj = {
                        'profiles': []
                    },
                    to_add = _view_type==='followers' ? my_p.followers : my_p.contacts;
                    // lookup and add the actual profile info to render obj
                    to_add.forEach(function(c_key){
                        let the_profile = _profiles.lookup(c_key),
                            render_profile = {
                                'pub_k' : c_key
                            },
                            attrs;

                        if(the_profile!==undefined){
                            attrs = the_profile['attrs'];
                            render_profile['picture'] =attrs.picture;
                            render_profile['name'] = attrs.name;
                            render_profile['about'] = attrs.about;
                            if(render_profile.about!==undefined){
                                render_profile.about = APP.nostr.util.html_escape(render_profile.about);
                                render_profile.about = _gui.http_media_tags_into_text(render_profile.about, false);
                                render_profile.about.replace(/\n/g,'<br>');
                            }
                        }
                        if((render_profile.picture===undefined) ||
                            (render_profile.picture===null) ||
                                (_enable_media===false)){
                            render_profile.picture = APP.nostr.gui.robo_images.get_url({
                                'text' : c_key
                            });
                        }

                        render_obj['profiles'].push(render_profile);
                    });

                    _contacts_con.html(Mustache.render(_row_tmpl, render_obj));
                });

            }
        });

        // clicking row takes you to that profile
        // todo: links
        _contacts_con.on('click', function(e){
            let id = APP.nostr.gui.get_clicked_id(e),
            pub_k;
            if((id!==undefined) && (id.indexOf('-pubk')>0)){
                pub_k = id.replace('-pubk','');
                location.href = '/html/profile?pub_k='+pub_k;
            }
        });


        // to see events as they happen
        start_client();
    });
}();