/*
    renders the section at the top of the screen
*/
APP.nostr.gui.header = function(){
    let _con,
        _current_profile,
        _profile_but,
        _enable_media;

    // watches which profile we're using and calls set_profile_button when it changes
    function watch_profile(){
        // look for future updates
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(data.pub_k !== _current_profile.pub_k){
                _current_profile = data;
                set_profile_button();
            }
        });
    }

    // actually update the image on the profile button
    function set_profile_button(){
        let url;
        if(_current_profile.pub_k===undefined){
            _profile_but.html(APP.nostr.gui.templates.get('no_user_profile_button'));
        }else{
            _profile_but.html('');
            _profile_but.css('background-size',' cover');
            if(_current_profile.attrs && _current_profile.attrs.picture && _enable_media){
                url = _current_profile.attrs.picture;
            }else{
                url = APP.nostr.gui.robo_images.get_url({
                    'text' : _current_profile.pub_k
                });
            }
            _profile_but.css('background-image','url("'+url+'")');
        }
    }

    function create(args){
        args = args || {};
        _con = args.con || $('#header-con');
        _enable_media = args.enable_media != undefined ? args.enable_media : false;
        // this is just a str
        _con.html(APP.nostr.gui.templates.get('head'));
        _profile_but = $('#profile_button');
        _current_profile = APP.nostr.data.user.get_profile();
        set_profile_button();
        watch_profile();

        // add events
        _profile_but.on('click', function(){
            APP.nostr.gui.profile_select_modal.show();
        });

    }

    return {
        'create' : create
    }
}();

APP.nostr.gui.post_button = function(){
    /*
        put a buttom in the bottom right of the screen that when clicked brings up the post modal
    */
    let _post_html = [
            '<div id="post-button" class="post-div">',
                '<div style="width:50%;height:50%;margin:25%;">',
                        '<svg class="bi" style="height:100%;width:100%;">',
                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#send-plus"/>',
                        '</svg>',
                '</div>',
            '</div>'
        ].join(''),
        _post_el,
        _post_text_area;

    function create(){
        // should only ever be called once anyway but just incase
        if(_post_el===undefined){
            $(document.body).prepend(_post_html);
            _post_el = $('#post-button');
            _post_el.on('click', function(){
                APP.nostr.gui.modal.create({
                    'title' : 'make post',
                    'content' : '<div><textarea id="nostr-post-text" class="form-control" rows="10" placeholder="whats going down?"></textarea></div>',
                    'ok_text' : 'send',
                    'on_ok' : function(){
                        APP.remote.post_text({
                            'pub_k' : APP.nostr.data.user.get_profile().pub_k,
                            'text': _post_text_area.val()
                        });

                    }
                });
                _post_text_area = $('#nostr-post-text');
                APP.nostr.gui.modal.show();
            });
        }
    }

    return {
        'create' : create
    }
}();

APP.nostr.gui.event_view = function(){
        // short ref
    let _gui = APP.nostr.gui,
        // global profiles obj
        _profiles = APP.nostr.data.profiles,
        // template for individual event in the view, styleing should move to css and classes
        _row_tmpl = [
            '<div id="{{uid}}-{{event_id}}" style="padding-top:2px;border 1px solid #222222">',
            '<span style="height:60px;width:120px; word-break: break-all; display:table-cell; background-color:#111111;padding-right:10px;" >',
                // TODO: do something if unable to load pic
                '{{#picture}}',
                    '<img id="{{uid}}-{{event_id}}-pp" src="{{picture}}" class="profile-pic-small" />',
                '{{/picture}}',
                // if no picture, again do something here
//                    '{{^picture}}',
//                        '<div id="{{id}}-pp" style="height:60px;width:64px">no pic</div>',
//                    '{{/picture}}',
            '</span>',
            '{{#is_parent}}',
                '<div style="height:60px;min-width:10px;border-left: 2px dashed white; border-bottom: 2px dashed white;display:table-cell;background-color:#441124;" >',
                '</div>',
            '{{/is_parent}}',
            '{{#missing_parent}}',
                '<div style="height:60px;min-width:10px;border-right: 2px dashed white; border-top: 2px dashed white;display:table-cell;background-color:#221124;" >',
                '</div>',
            '{{/missing_parent}}',
            '{{^missing_parent}}',
                '{{#is_child}}',
                    '<div style="height:60px;min-width:10px;border-right:2px dashed white;background-color:#221124;display:table-cell;" >',
                    '</div>',
                '{{/is_child}}',
            '{{/missing_parent}}',
            '<span class="post-content" >',
                '<div border-bottom: 1px solid #443325;">',
                    '<span id="{{uid}}-{{event_id}}-pt" >',
                        '{{#name}}',
                            '<span style="font-weight:bold">{{name}}</span>@<span style="color:cyan">{{short_key}}</span>',
                        '{{/name}}',
                        '{{^name}}',
                            '<span style="color:cyan;font-weight:bold">{{short_key}}</span>',
                        '{{/name}}',
                    '</span>',
                    '<span id="{{uid}}-{{event_id}}-time" style="float:right">{{at_time}}</span>',
                '</div>',
                '{{{content}}}',
                '<div style="width:100%">',
//                    '<span style="color:gray;">{{short_event_id}}</span>',
                    '<span>&nbsp;</span>',
                    '<span style="float:right" >',
                        '<svg class="bi" >',
                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#reply-fill"/>',
                        '</svg>',
                        '<svg id="{{uid}}-{{event_id}}-expand" class="bi" >',
                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#three-dots-vertical"/>',
                        '</svg>',
                    '</span>',
                    '<div style="border:1px dashed gray;display:none" id="{{uid}}-{{event_id}}-expandcon" style="display:none">event detail...</div>',
                '</div>',
            '</span>',
            '</div>'
        ].join('');

    function _profile_clicked(pub_k){
        location.href = '/html/profile?pub_k='+pub_k;
    }

    function get_event_parent(evt){
        let parent = null;
        for(j=0;j<evt.tags.length;j++){
            tag = evt.tags[j];
            if(tag[0]==='e'){
                if(tag[1]!==undefined){
                    // we have a parent
                    parent = tag[1];
                }
                return parent;
            }
        }
        // no parent
        return null;
    };

    function _event_clicked(evt){
        let root = '';
        if(evt['missing_parent']!==undefined && evt.missing_parent===true){
            root = '&root='+get_event_parent(evt);
        }
        location.href = '/html/event?id='+evt.id+root;
    }

    function create(args){
        // notes as given to us (as they come from the load)
        let _notes_arr,
            // data render to be used to render
            _render_arr,
            // events data by id
            _event_map,
            // unique id for the event view
            _uid= _gui.uid(),
            // where we'll render
            _con = args.con,
            // attempt to render external media in note text.. could be more fine grained to type
            // note also this doesn't cover profile img
            _enable_media = args.enable_media!==undefined ? args.enable_media : false,
            // filter for notes that will be added to notes_arr
            // not that currently only applied on add, the list you create with is assumed to already be filtered
            // like nostr filter but minimal impl just for what we need
            // TODO: Fix this make filter obj?
            _sub_filter = args.filter!==undefined ? args.filter : {
                'kinds' : new Set([1])
            },
            // track which event details are expanded
            _expand_state = {},
            // underlying APP.nostr.gui.list
            _my_list;

        function uevent_id(event_id){
            return _uid+'-'+event_id;
        }

        function _note_content(the_note){
            let name = the_note['pubkey'],
            p,
            attrs,
            pub_k = the_note['pubkey'],
            to_add = {
                'is_parent' : the_note.is_parent,
                'missing_parent' : the_note.missing_parent,
                'is_child' : the_note.is_child,
                'uid' : _uid,
                'evt': the_note,
                'event_id' : the_note.id,
                'short_event_id' : APP.nostr.util.short_key(the_note.id),
                'content' : the_note['content'],
                'short_key' : APP.nostr.util.short_key(pub_k),
                'pub_k' : pub_k,
                'picture' : APP.nostr.gui.robo_images.get_url({
                    'text' : pub_k
                }),
                'at_time': dayjs.unix(the_note.created_at).fromNow()
            };


            // make safe
            to_add.content = APP.nostr.util.html_escape(to_add.content);
            // insert media tags to content
            to_add.content = _gui.http_media_tags_into_text(to_add.content, _enable_media);
            // do p tag replacement
            to_add.content = _gui.tag_replacement(to_add.content, the_note.tags)
            // add line breaks
            to_add.content = to_add.content.replace(/\n/g,'<br>');
            // fix special characters as we're rendering in html el
            to_add.content = APP.nostr.util.html_unescape(to_add.content);

            if(_profiles.is_loaded()){
            p = _profiles.lookup(name);
            if(p!==undefined){
                attrs = p['attrs'];
                if(attrs!==undefined){
                    if(attrs['name']!==undefined){
                        to_add['name'] = attrs['name'];
                    }
                    if(_enable_media && attrs['picture']!==undefined){
                        to_add['picture'] = attrs['picture'];
                    }

                }
            }
            };
            return to_add;
        }

        function _expand_event(e_data){
            let evt_id = e_data.id,
            con;
            if(_expand_state[evt_id]===undefined){
                con = $('#'+uevent_id(evt_id)+'-expandcon');
                _expand_state[evt_id] = {
                    'is_expanded' : true,
                    'con' : con,
                    'event_info' : APP.nostr.gui.event_detail.create({
                        'con' : con,
                        'event': e_data
                    })
                };
                _expand_state[evt_id].event_info.draw();
                con.fadeIn();
            }else{
                if(_expand_state[evt_id].is_expanded){
                    _expand_state[evt_id].con.fadeOut();
                }else{
                    _expand_state[evt_id].con.fadeIn();
                }
                _expand_state[evt_id].is_expanded = !_expand_state[evt_id].is_expanded;
            }

        }

        function _create_contents(){
            // profiles must have loaded before notes
            if(_notes_arr===undefined){
                return;
            };

            _render_arr = [];
            // event map contains both the event and event after we added our
            // extra fields
            _event_map = {};

            _notes_arr.forEach(function(c_evt){
                _event_map[c_evt.id] = {
                    'event' : c_evt
                }
            });
            // evts ordered and rendered for screen
            event_ordered().forEach(function(c_evt){
                let add_content = _note_content(c_evt);
                _render_arr.push(add_content);
                _event_map[c_evt.id].render_event = c_evt;
            });

            if(_my_list===undefined){
                _my_list = APP.nostr.gui.list.create({
                    'con' : _con,
                    'data' : _render_arr,
                    'row_tmpl': _row_tmpl,
                    'click' : function(id){
                        let parts = id.replace(_uid+'-','').split('-'),
                            event_id = parts[0],
                            type = parts[1],
                            evt = _event_map[event_id] !==undefined ? _event_map[event_id].event : null;
                        if(type==='expand'){
                            _expand_event(evt);
                        }else if(type==='pt' || type==='pp'){
                           _profile_clicked(evt.pubkey);
                        }else if(type===undefined && evt!==null){
                            // event clicked wants to see is_parent_missing field
                            // which mean using the render_event
                            // at the moment this won't exist for evts added to screen seen last refresh
                            // (via websocket) in which case it just gets the event and parent_missing assumned false
                            // the whole evts added after page load needs going through anyhow...
                            if(_event_map[event_id].render_event!==undefined){
                                evt = _event_map[event_id].render_event;
                            }
                            _event_clicked(evt);
                        }


                    }
                });
            }else{
                _my_list.set_data(_render_arr);
            }

            _my_list.draw();
        };


        function event_ordered(){
            /* where tags refrence a parent, if we have that event we'll lift it up so it appears
                before it's child event (otherwise everything is just date ordered)

            */
            let roots = {},
                ret = [],
                notes_arr_copy = [];

            function add_children(evt){
                // reverse the children so newest are first
                evt.children.reverse();
                evt.children.forEach(function(c_evt,j){
                    c_evt.is_child = true;
                    ret.push(c_evt);
                });
            }

            // 1. look through all events and [] thouse that have the same parent
            _notes_arr.forEach(function(c_evt,i){
                let tag,j,parent;
                // everything is done on a copy of tthe event as we're going to add some of
                // our own fields
                c_evt = jQuery.extend({}, c_evt);

                notes_arr_copy.push(c_evt);
                parent = get_event_parent(c_evt);

                if(parent!==null){
                    if(roots[parent]===undefined){
                        roots[parent] = {
                            'children' : []
                        }
                    }
                    roots[parent].children.push(c_evt);
                }else{
                    if(roots[c_evt.id]!==undefined){
                        roots[c_evt.id]['event'] = c_evt;
                    }else{
                        roots[c_evt.id] = {
                            'event' : c_evt,
                            'children': []
                        }
                    }
                }
            });

            // 3. now create the ordered version
            notes_arr_copy.forEach(function(c_evt,i){
                let parent = get_event_parent(c_evt);

                // parent, draw it and any children
                if(roots[c_evt.id]!==undefined && roots[c_evt.id].added!==true){
                    if(roots[c_evt.id].children.length>0){
                        c_evt.is_parent = true;
                    }

                    ret.push(c_evt);
//                    // now reverse the children and add
//                    roots[c_evt.id].children.reverse();
//                    roots[c_evt.id].children.forEach(function(c_evt,j){
//                        c_evt.is_child = true;
//                        order_arr.push(c_evt);
//                    });
                    add_children(roots[c_evt.id]);

                    roots[c_evt.id].added=true;
                // child of a parent, draw parent if we have it and all children
                }else if(parent!==null && roots[parent].added!==true){
                    // do we have parent event
                    if(roots[parent].event){
                        roots[parent].event.is_parent = true;
                        ret.push(roots[parent].event);
                    }
                    // now reverse the children and add
//                    roots[parent].children.reverse();
//                    roots[parent].children.forEach(function(c_evt,j){
//                        c_evt.is_child = true;
//                        order_arr.push(c_evt);
//                    });
                    add_children(roots[parent]);

                    roots[parent].added=true;
                }

            });
//            alert(order_arr.length)
//            alert(_notes_arr.length)
// 2. mark those missing a parent and those that are the last child we have
            for(let j in roots){
                if(roots[j].event===undefined){
                    roots[j].children[0].missing_parent=true;
//                    alert(roots[j].children[0].id);
                }
            }



            // 4. switch note_arr for the order_arr we created
            return ret;
        }

        function set_notes(the_notes){
            _notes_arr = the_notes;

            // makes [] that'll be used render display
            _create_contents();
        };

        function _time_update(){
            _render_arr.forEach(function(c){
                let id = uevent_id(c.event_id),
                    ntime = dayjs.unix(c['evt'].created_at).fromNow();

                // update in render obj, at the moment it never gets reused anyhow
                c['at_time'] = ntime;
                // actually update onscreen
                $('#'+id+'-time').html(ntime);
            });
        }

        /*
            minimal filter implementation, only testing note of correct kind and authorship
            for a single filter {}
        */
        function _test_filter(evt){
            let ret = true;
            if((_sub_filter.kinds!==undefined) && (!_sub_filter.kinds.has(evt.kind))){
                return false;
            }
            if((_sub_filter.authors!==undefined) && (!_sub_filter.authors.has(evt.pubkey))){
                return false;
            }
            return ret;
        };

        function add_note(evt){
            if(_test_filter(evt)){
                let add_content = _note_content(evt);
                // just insert the new event
                _notes_arr.unshift(evt);
                _render_arr.unshift(add_content);

                // we won't redraw the whole list just insert at top
                // which should be safe (end might be ok, but anywhere else would be tricky...)
                _con.prepend(Mustache.render(_row_tmpl,_render_arr[0]));
                _event_map[evt.id] = evt;
            }
        }

        // update the since every 30s
        setInterval(_time_update, 1000*30);

        // methods for event_view obj
        return {
            'set_notes' : set_notes,
            // TODO - eventually this won't be required
            'profiles_loaded' : function(){
                _create_contents();
            },
            'add' : add_note
        };
    };

    return {
        'create' : create
    };
}();

APP.nostr.gui.profile_about = function(){
    // if showing max n of preview followers in head
    const MAX_PREVIEW_PROFILES = 10,
        ENABLE_MEDIA = APP.nostr.gui.enable_media,
        // global profiles obj
        _profiles = APP.nostr.data.profiles,
        _tmpl = [
                '<div style="padding-top:2px;">',
                '<span style="display:table-cell;width:128px; background-color:#111111;padding-right:10px;" >',
                    // TODO: do something if unable to load pic
                    '{{#picture}}',
                        '<img id="{{pub_k}}-pp" src="{{picture}}" class="{{profile_pic_class}}" />',
                    '{{/picture}}',
                '</span>',
                '<span style="width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                    '{{#name}}',
                        '<span>{{name}}@</span>',
                    '{{/name}}',
                    '<span class="pubkey-text" >{{pub_k}}</span>',
//                    '<svg id="{{pub_k}}-cc" class="bi" >',
//                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#clipboard-plus-fill"/>',
//                    '</svg>',
//                    '<br>',
//                    '{{#name}}',
//                        '<div>',
//                            '{{name}}',
//                        '</div>',
//                    '{{/name}}',
                    '{{#about}}',
                        '<div>',
                            '{{{about}}}',
                        '</div>',
                    '{{/about}}',
                    '<div id="contacts-con" ></div>',
                    '<div id="followers-con" ></div>',
                '</span>',
                '</div>'
        ].join(''),
        // used to render a limited list of follower/contacts imgs and counts
        _fol_con_sub = [
            '<span class="profile-about-label">{{label}} {{count}}</span>',
            '{{#images}}',
            '<span style="display:table-cell;">',
                '<img id="{{id}}" src="{{src}}" class="profile-pic-verysmall" />',
            '</span>',
            '{{/images}}',
            '{{#trail}}',
                '<span style="display:table-cell">',
                    '<svg class="bi" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#three-dots"/>',
                    '</svg>',
                '</span>',
            '{{/trail}}'
        ].join('');

    function create(args){
            // our container
        let _con = args.con,
            // pub_k we for
            _pub_k = args.pub_k,
            // and the profile {} for this pub_k
            _profile,
            // add this in and when false just render our own random images for profiles rather than going to external link
            // in future we could let the user provide there own images for others profiles
            //_enable_media = true,
            // follower info here
            _follow_con,
            // and contacts
            _contact_con,
            // gui to click func map
            _click_map = {},
            _enable_media = args.enable_media!==undefined ? args.enable_media : ENABLE_MEDIA,
            _show_follow_section = args.show_follows!=undefined ? args.show_follows : true;

        // called when one of our profiles either from follower or contact is clicked
        function _profile_clicked(pub_k){
            location.href = '/html/profile?pub_k='+pub_k;
        }

        function draw(){
            let render_obj = {
                'pub_k' : _pub_k,
                'profile_pic_class': _show_follow_section===true ? 'profile-pic-large' : 'profile-pic-small'
            },
            attrs,
            _contacts;
            _profile = _profiles.lookup(_pub_k);
            // fill from the profile if we found it
            if(_profile!==undefined){

                attrs = _profile['attrs'];
                render_obj['picture'] =attrs.picture;
                render_obj['name'] = attrs.name;
                render_obj['about'] = attrs.about;
                if(render_obj.about!==undefined){
                    render_obj.about = APP.nostr.gui.http_media_tags_into_text(render_obj.about, false);
                    render_obj.about = render_obj.about.replace().replace(/\n/g,'<br>');
                }
            }
            // give a picture based on pub_k event if no pic or media turned off
            if((render_obj.picture===undefined) ||
                (render_obj.picture===null) ||
                    (_enable_media===false)){
                render_obj.picture = APP.nostr.gui.robo_images.get_url({
                    'text' : _pub_k
                });
            }

            _con.html(Mustache.render(_tmpl, render_obj));
            // grab the follow and contact areas
            _contact_con = $('#contacts-con');
            _follow_con = $('#followers-con');

            // wait for folloer/contact info to be loaded
            if(_show_follow_section){
                _contacts = _profile.load_contact_info(function(){
                    render_followers();
                });
            }


        };

        function render_followers(){
                render_contact_section('follows', _contact_con, _profile.contacts);
                render_contact_section('followed by', _follow_con, _profile.followers);

                // listen for clicks
                $(_con).on('click', function(e){
                    let id = APP.nostr.gui.get_clicked_id(e);
                    if(_click_map[id]!==undefined){
                        _click_map[id].func(_click_map[id].data);
                    }
//                    else if((id!==null) && (id.indexOf('-cc')>0)){
////                        alert('clipboard copy!!!!' + id.replace('-cc',''));
//                        navigator.clipboard.writeText(id.replace('-cc',''));
//                    }
                });
        }

        function render_contact_section(label, con, pub_ks){
            let args = {
                'label': label,
                'count': pub_ks.length,
                'images' : []
            },
            to_show_max = pub_ks.length,
            c_p,
            img_src,
            id;

            if(to_show_max>MAX_PREVIEW_PROFILES-1){
                args['trail'] = true;
                to_show_max = MAX_PREVIEW_PROFILES;
            };

            if(to_show_max>0){
                con.css('cursor','pointer');
                _click_map[con[0].id] = {
                    'func' : function(){
                        let view_type = 'contacts';
                        if(con[0].id==='followers-con'){
                            view_type = 'followers';
                        }
                        location.href = '/html/contacts?pub_k='+_pub_k+'&view_type='+view_type;
                    }
                };
            }

            // add the images
            for(let i=0;i<to_show_max;i++){
                id = APP.nostr.gui.uid();
                c_p = _profiles.lookup(pub_ks[i]);
                // a profile doesn't necessarily exist
                if(c_p && c_p.attrs.picture!==undefined && _enable_media){
                    img_src = c_p.attrs.picture;
                }else{
                    img_src = APP.nostr.gui.robo_images.get_url({
                        'text' : pub_ks[i]
                    });
                }

                args.images.push({
                    'id' : id,
                    'src' : img_src
                })

                _click_map[id] = {
                    'func' : _profile_clicked,
                    'data' : pub_ks[i]
                };
            }

            // and render
            con.html(Mustache.render(_fol_con_sub, args));
        }



        // methods for event_view obj
        return {
            'profiles_loaded' : draw
        };
    };

    return {
        'create' : create
    };
}();

APP.nostr.gui.profile_list = function (){
        // lib shortcut
    let _gui = APP.nostr.gui,
        // short cut ot profiles helper
        _profiles = APP.nostr.data.profiles;

    function create(args){
            // container for list
        let _con = args.con,
            // profiles passed into us
            _view_profiles = args.profiles || [],
            // if pub key is passed we'll load profiles from either followers/contacts of that profile
            _pub_k = args.pub_k,
            // inline media where we can, where false just the link is inserted
            _enable_media = args.enable_media || false,
            // profile we're viewing
            _the_profile = _profiles.lookup(_pub_k),
            // rendering the_profile.followers or contacts ?
            _view_type = args.view_type==='followers' ? 'followers' : 'contacts',
            // data preped for render to con by _create_render_obj
            _render_obj,
            _do_draw=false,
            // only profiles that pass this filter will be showing
            _filter_text = args.filter || '',
            // so ids will be unique per this list
            _uid = APP.nostr.gui.uid(),
            // list obj that actually does the rendering
            _my_list,
            // template to render into
            _row_tmpl = APP.nostr.gui.templates.get('profile-list');

        // handed pub_k rather than profiles directly, attempt to load there followers/contacts
        // then set _view_profiles dependent on view_type
        if(_pub_k!==undefined){
            _the_profile.load_contact_info(function(){
                try{
                    // set the view_profiles
                    _view_profiles = _view_type==='followers' ? _the_profile.followers : _the_profile.contacts;
                    got_data();
                }catch(e){
                    console.log(e);
                }
            });
        }else{
            // can call straight away
            got_data();
        }


        // methods

        function got_data(){
            // prep the intial render obj
            _my_list = APP.nostr.gui.list.create({
                'con' : _con,
                'data' : create_render_data(),
                'row_tmpl': _row_tmpl,
                'filter' : test_filter,
                'click' : function(id){
                    let pubk = id.replace(_uid+'-','');
                    location.href = '/html/profile?pub_k='+pubk;
                }
            });

            // draw was called before we were ready, draw now
            if(_do_draw){
                _my_list.draw();
            }
        }

        function draw(){
            if(_my_list!==undefined){
                _my_list.draw();
            }else{
                _do_draw = true;
            }
        };

        /*
            fills data that'll be used with template to render
        */
        function create_render_data(){
            let ret = [];
            _view_profiles.forEach(function(c_key){
                ret.push(_create_render_profile(c_key));
            });
            return ret;
        }

        // create profile render obj to be put in _renderObj['profiles']
        function _create_render_profile(pub_k){
            let the_profile = _profiles.lookup(pub_k),
                render_profile = {
                    // required to make unique ids if page has more than one list showing same items on page
                    'uid' : _uid,
                    'pub_k' : pub_k,
                    'short_pub_k' : APP.nostr.util.short_key(pub_k)
                },
                attrs;

            if(the_profile!==undefined){
                attrs = the_profile['attrs'];
                render_profile['picture'] =attrs.picture;
                render_profile['name'] = attrs.name;
                render_profile['about'] = attrs.about;
                // be better to do this in our data class
                if(render_profile.about!==undefined && render_profile.about!==null){
//                    render_profile.about = APP.nostr.util.html_escape(render_profile.about);
                    render_profile.about = _gui.http_media_tags_into_text(render_profile.about, false);
                    render_profile.about = render_profile.about.replace(/\n/g,'<br>');
                }
            }
            if((render_profile.picture===undefined) ||
                (render_profile.picture===null) ||
                    (_enable_media===false)){
                render_profile.picture = APP.nostr.gui.robo_images.get_url({
                    'text': pub_k
                });
            }
            return render_profile;
        }

        function test_filter(render_obj){
            if(_filter_text.replace(' ','')==''){
                return true;
            };
            let test_txt = _filter_text.toLowerCase();
            if(render_obj.pub_k.toLowerCase().indexOf(test_txt)>=0){
                return true;
            };
            if((render_obj.name!==undefined) && (render_obj.name.toLowerCase().indexOf(test_txt)>=0)){
                return true;
            }
            if((render_obj.about!==undefined) && (render_obj.about.toLowerCase().indexOf(test_txt)>=0)){
                return true;
            }
        }

        function set_filter(str){
            _filter_text = str;
            _my_list.draw();
        }

        return {
            'draw': draw,
            'set_filter': set_filter
        }
    }

    return {
        'create': create
    }
}();

/*
    modal, we only ever create one of this and just fill the content differently
    used to make posts, maybe set options?
*/
APP.nostr.gui.modal = function(){
    let _modal_html = [
            '<div style="color:black;height:100%" id="nostr-modal" class="modal fade" role="dialog">',
                '<div class="modal-dialog">',
                    '<div class="modal-content">',
                        '<div class="modal-header">',
                            '<button type="button" class="close" data-dismiss="modal" style="opacity:1;color:white;" >&times;</button>',
                            '<h4 class="modal-title" id="nostr-modal-title"></h4>',
                        '</div>',
                        '<div class="modal-body" id="nostr-modal-content" >',
                        '</div>',
                        '<div class="modal-footer">',
                            '<button id="nostr-modal-ok-button" type="button" class="btn btn-default" data-dismiss="modal">Close</button>',
                        '</div>',
                    '</div>',
                '</div>',
            '</div>'
        ].join(''),
        _my_modal,
        _my_title,
        _my_content,
        _my_ok_button;

    function create(args){
        let title = args.title || '?no title?';
            content = args.content || '',
            ok_text = args.ok_text || '?no_text?',
            on_ok = args.on_ok;

        // make sure we only ever create one
        if(_my_modal===undefined){
            $(document.body).prepend(_modal_html);
            _my_modal = $('#nostr-modal');
            _my_title = $('#nostr-modal-title');
            _my_content = $('#nostr-modal-content');
            _my_ok_button = $('#nostr-modal-ok-button');

            // escape to hide
            $(document).on('keydown', function(e){
                if(e.key==='Escape' && _my_modal.hasClass('in')){
                    hide();
                }
            });

            _my_ok_button.on('click', function(){
                if(typeof(on_ok)==='function'){
                    on_ok();
                }
            });

        }
        _my_title.html(title);
        _my_content.html(content);
        _my_ok_button.html(ok_text);

    }

    function show(){
        // create must have been called before calling show
        _my_modal.modal()
    }

    function hide(){
        _my_modal.modal('hide');
    }

    function set_content(content){
        _my_content.html(content);
    }

    return {
        'create' : create,
        'show' : show,
        'hide' : hide,
        'set_content' : set_content
    };
}();

APP.nostr.gui.profile_select_modal = function(){
    let _uid = APP.nostr.gui.uid(),
        // short cut ot profiles helper
        _profiles = APP.nostr.data.profiles;

    function draw_profiles(profiles){
        let row_tmpl = APP.nostr.gui.templates.get('profile-list'),
            list,
            render_obj = [],
            create_render_obj = function(){
                profiles.forEach(function(c_p,i){
                    let img_src;

                    // a profile doesn't necessarily exist
                    if(c_p && c_p.attrs.picture!==undefined && true){
                        img_src = c_p.attrs.picture;
                    }else{
                        img_src = APP.nostr.gui.robo_images.get_url({
                            'text' : c_p.pub_k
                        });
                    }

                    let to_add = {
                        'uid' : _uid,
                        'short_pub_k' : APP.nostr.util.short_key(c_p.pub_k),
                        'pub_k' : c_p.pub_k,
                        'profile_name' : c_p.profile_name,
                        'name' : c_p.attrs.name,
                        'picture' : img_src
                    };

                    to_add.profile_name = c_p.profile_name;
                    render_obj.push(to_add);
                });
            };

        create_render_obj();

        APP.nostr.gui.modal.set_content('<div id="'+_uid+'"></div>');

        list = APP.nostr.gui.list.create({
            'con' : $('#'+_uid),
            'data' : render_obj,
            'row_tmpl': row_tmpl,
            'click' : function(id){
                let pub_k = id.replace(_uid+'-', '');
                APP.nostr.data.user.set_profile(_profiles.lookup(pub_k));
                APP.nostr.gui.modal.hide();
            }
        });
        list.draw();
    }

    function show(){
        // set the modal as we want it
        APP.nostr.gui.modal.create({
            'title' : 'choose profile',
            'content' : 'loading...',
            'ok_text' : 'ok'
        });

        // show it
        APP.nostr.gui.modal.show();

        APP.nostr.data.local_profiles.init({
            'success' : draw_profiles
        });

    }

    return {
        'show' : show
    }
}();
