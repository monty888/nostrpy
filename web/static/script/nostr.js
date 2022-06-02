// TODO: nostr stuff will be moved out to be share
APP.nostr = {
    'data' : {},
    'gui' : function(){
        let _id=0,
            // templates for rendering different media
            // external_link
            _link_tmpl = '<a href="{{url}}">{{url}}</a>',
            // image types e.g. jpg, png
            _img_tmpl = '<img src="{{url}}" width=640 height=auto style="display:block;" />',
            // video
            _video_tmpl = '<video width=640 height=auto style="display:block" controls>' +
            '<source src="{{url}}" >' +
            'Your browser does not support the video tag.' +
            '</video>';

        return {
            // a unique id in this page
            'uid' : function(){
                _id++;
                return 'guid-'+_id;
            },
            // from clicked el traverses upwards to first el with id if any
            // null if we reach the body el before finding an id
            'get_clicked_id' : function(e){
                let ret = null,
                    el = e.target;

                while((el.id===undefined || el.id==='') && el!==document.body){
                    console.log(el)
                    el = el.parentNode;
                }
                if(el!=document.body){
                    ret = el.id;
                }
                return ret;
            },
            /*
                for given ext returns media type which tells us how to render the content
                anything not understood is returned as external_link and will be rendered as <a> tag
            */
            'media_lookup': function media_lookup(ref_str){
                let media_types = {
                    'jpg': 'image',
                    'gif': 'image',
                    'png': 'image',
                    'mp4': 'video'
                    },
                    parts = ref_str.split('.'),
                    ext = parts[parts.length-1],
                    ret = 'external_link';

                if(ext in media_types){
                    ret = media_types[ext];
                }
                return ret;
            },
            'http_media_tags_into_text' : function(text, enable_media, tmpl_lookup){
                // first make the text safe
                let ret = APP.nostr.util.html_escape(text),
                    // look for link like strs
                    http_matches = APP.nostr.util.http_matches(ret);

                    /* by default everything, if enable_media is false everything will be rendered
                     as external_link, perhaps enable even this level to be turn off
                     or just dont call and just make text safe ... maybe enable media should
                     be changed from true/false
                        0 - no media whatsoever and text rendered unclickable (user has to physically copy paste)
                        1 - no media but hrefs are still rendered
                        2 - external media rendered where wee can, links otherwise
                        (0 could also just give yes/no alert?)
                     */
                    tmpl_lookup = tmpl_lookup || {
                        'image' : _img_tmpl,
                        'external_link' : _link_tmpl,
                        'video' : _video_tmpl
                    };
                    enable_media = enable_media || true

                    // and do replacements in the text
                    // do inline media and or link replacement
                    if(http_matches!==null){
                        http_matches.forEach(function(c_match){
                            // how to render, unless enable media is false in which case just the link is out put
                            // another level of safety would be that these links are rendered inactive and need the user
                            // to perform some action to actaully enable them
                            let media_type = enable_media===true ? APP.nostr.gui.media_lookup(c_match) : 'external_link';
                            ret = ret.replace(c_match,Mustache.render(tmpl_lookup[media_type],{
                                'url' : c_match
                            }));
                        });
                    }
                    return ret;
            }
        };
    }(),
    'util' : {
        'short_key': function (pub_k){
            return pub_k.substring(0, 3) + '...' + pub_k.substring(pub_k.length-4)
        },
        'html_escape': function (in_str){
            return in_str.replaceAll('&', '&amp;').
                replaceAll('<', '&lt;').
                replaceAll('>', '&gt;').
                replaceAll('"', '&quot;').
                replaceAll("'", '&#39;');
        },
        // copied from https://stackoverflow.com/questions/17678694/replace-html-entities-e-g-8217-with-character-equivalents-when-parsing-an
        // for text that is going to be rendered into page as html
        // {{{}}} in Mustache templates
        'html_unescape' : function (str) {//modified from underscore.string and string.js
//            var escapeChars = { lt: '<', gt: '>', quot: '"', apos: "'", amp: '&' };
            // reduced to just &n; style replacements, will need to come back and think about this properly
            var escapeChars = {amp: '&' };
            return str.replace(/\&([^;]+);/g, function(entity, entityCode) {
                var match;if ( entityCode in escapeChars) {
                    return escapeChars[entityCode];
                } else if ( match = entityCode.match(/^#x([\da-fA-F]+)$/)) {
                    return String.fromCharCode(parseInt(match[1], 16));
                } else if ( match = entityCode.match(/^#(\d+)$/)) {
                    return String.fromCharCode(~~match[1]);
                } else {
                    return entity;
                }
            });
        },
        'http_matches' : function(txt){
            const http_regex = /(https?\:\/\/[\w\.\/\-\%\?\=\~\+\@\&\;\#]*)/g
            return txt.match(http_regex);
        }

    }
};

// for relative times of notes from now
dayjs.extend(window.dayjs_plugin_relativeTime);

APP.nostr.gui.tabs = function(){
    /*
        creates a tabbed area, probably only used to set up the, and events for moving between tabs
        but otherwise caller can deal with rendering the content
    */
    let _head_tmpl = [
        '<ul class="nav nav-tabs">',
            '{{#tabs}}',
                '<li class="{{active}}"><a data-toggle="tab" href="#{{tab-ref}}">{{tab-title}}</a></li>',
            '{{/tabs}}',
            // extra area for e.g. search field,
            '<span style="display:table-cell;width:250px;padding-top:4px;">',
                // to remove
                '<input placeholder="search" type="text" class="form-control" id="search-in">',
            '</span>',
        '</ul>'
        ].join(''),
        _body_tmpl = [
            '<div class="tab-content">',
            '{{#tabs}}',
                '<div id="{{tab-ref}}" class="tab-pane {{transition}} {{active}}">',
                    '<div id="{{tab-ref}}-con">{{content}}</div>',
                '</div>',
            '{{/tabs}}',
            '</div>'
        ].join('');

    function create(args){
            // where we'll be drawn
        let _con = args.con,
            // data preped for template render
            _render_obj,
            // do a draw as soon as created
            _init_draw = args.do_draw|| false,
            // content if no content given for tab
            _default_content = args.default_content || '',
            _tabs = args.tabs||[];

        function create_render_obj(){
            _render_obj = {
                'tabs' : []
            };
            _tabs.forEach(function(c_tab){
                let to_add = {};
                to_add['tab-title'] = c_tab.title!==undefined ? c_tab.title : '?no title?';
                to_add['tab-ref'] = c_tab.id!==undefined ? c_tab.id : APP.nostr.gui.uid();
                to_add['content'] = c_tab.content!==undefined ? c_tab.content : _default_content;
                if(c_tab.active===true){
                    to_add['active'] = 'active';
                    to_add['transition'] = 'fade in';
                }else{
                    to_add['transition'] = 'fade';
                }
                _render_obj.tabs.push(to_add);

            });

        }

        function draw(){
            let render_html = [
                Mustache.render(_head_tmpl, _render_obj),
                Mustache.render(_body_tmpl, _render_obj)
                ].join('')
            // now render
            _con.html(render_html);

            // get the content objects and put in render_obj so we don't have to go through the
            // dom again
            _render_obj.tabs.forEach(function(c_tab){
                c_tab['tab_content_con'] = $('#'+c_tab['tab-ref']+'-con');
            });

        }

        function get_tab(ident){
            let ret = {},
                tab_render_obj;
            if(typeof(ident)=='number'){
                tab_render_obj = _render_obj.tabs[ident];
            }

            // TODO: by title

            // now copy relavent bits
            ret['content-con'] = tab_render_obj['tab_content_con'];

            return ret;
        }

        function init(){
            create_render_obj();
        }
        // do the init
        init();

        return {
            'draw': draw,
            'get_tab' : get_tab
        };
    };

    return {
        'create' : create
    }
}();



/*
    profiles data is global,
    the load will only be attempted once no matter how many times init is called
    so probably better to only do in one place and use on_load for other places
    in future clear the init flag on load fail so init can be rerun...
    obvs int the long run keeping lookup of all profiles in mem isn't going to scale...
*/
APP.nostr.data.profiles = function(){
    // as loaded
    let _profiles_arr,
    // key'd pubk for access
    _profiles_lookup,
    // called when completed
    _on_load = [],
    // set true when initial load is done
    _is_loaded = false,
    // has loaded started
    _load_started = false;

    function _get_load_contact_info(p){
        return function(callback){
            // make sure we're looking at same profile obj
            let my_p = _profiles_lookup[p.pub_k];
            // already loaded, caller can continue
            if(my_p.contacts!==undefined){
                callback();
            }
            // load required
            APP.remote.load_profile({
                'pub_k': p.pub_k,
                'include_followers': true,
                'include_contacts': true,
                'success' : function(data){
                    // update org profile with contacts and folloers
                    my_p.contacts = data['contacts'];
                    my_p.followers = data['followed_by'];
                    try{
                        callback();
                    }catch(e){
                        console.log(e);
                    }
                }
            });
        }
    }

    function _loaded(data){
        _profiles_arr = data['profiles'];
        _profiles_lookup = {};
        _profiles_arr.forEach(function(p){
            p.load_contact_info = _get_load_contact_info(p);
            _profiles_lookup[p['pub_k']] = p;
        });
        _is_loaded = true;
        _on_load.forEach(function(c_on_load){
            try{
                c_on_load();
            }catch(e){
                console.log(e);
            }
        });
    }

    function init(args){
        args = args || {};
        args.success = _loaded;

        if(_load_started===true){
            if(typeof(args.on_load)==='function'){
                if(_is_loaded){
                    args.on_load();
                }else{
                    _on_load.push(args.on_load);
                }
            }
            return;
        }

        _load_started = true;
        if(typeof(args.on_load)==='function'){
            _on_load.push(args.on_load);
        };

        APP.remote.load_profiles(args);
    };

    return {
        'init' : init,
        'is_loaded': function(){
            return _is_loaded;
        },
        'lookup': function(pub_k){
            return _profiles_lookup[pub_k];
        },
        'count' : function(){
            return _profiles_arr.length;
        }

    };
}();

APP.nostr.gui.event_view = function(){
        // short ref
    let _gui = APP.nostr.gui,
        // where we'll render
        _con,
        // notes as given to us (as they come from the load)
        _notes_arr,
        // data render to be used to render
        _render_arr,
        // global profiles obj
        _profiles = APP.nostr.data.profiles,
        // attempt to render external media in note text.. could be more fine grained to type
        // note also this doesn't cover profile img
        _enable_media,
        // have we drawn once already? incase profiles arrive after notes
        _draw_done = false,
        // filter for notes that will be added to notes_arr
        // not that currently only applied on add, the list you create with is assumed to already be filtered
        // like nostr filter but minimal impl just for what we need
        _sub_filter,
        // gui to click func map
        _click_map = {},
        // cache of tag replacement regexs
        _preregex = {},
        // template for individual event in the view, styleing should move to css and classes
        _row_tmpl = [
            '{{#notes}}',
                '<div style="padding-top:2px;border 1px solid #222222">',
                '<span style="height:60px;width:120px; word-break: break-all; display:table-cell; background-color:#111111;padding-right:10px;" >',
                    // TODO: do something if unable to load pic
                    '{{#picture}}',
                        '<img id="{{id}}-pp" src="{{picture}}" class="profile-pic-small" />',
                    '{{/picture}}',
                    // if no picture, again do something here
//                    '{{^picture}}',
//                        '<div id="{{id}}-pp" style="height:60px;width:64px">no pic</div>',
//                    '{{/picture}}',
                '</span>',
                '<span style="height:60px;width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                    '<div border-bottom: 1px solid #443325;">',
                        '<span id="{{id}}-pt" style="cursor:pointer" >',
                            '{{#name}}',
                                '<span style="font-weight:bold">{{name}}</span>@<span style="color:cyan">{{short_key}}</span>',
                            '{{/name}}',
                            '{{^name}}',
                                '<span style="color:cyan;font-weight:bold">{{short_key}}</span>',
                            '{{/name}}',
                        '</span>',
                        '<span id="{{id}}-time" style="float:right">{{at_time}}</span>',
                    '</div>',
                    '{{{content}}}',
                '</span>',
                '</div>',
            '{{/notes}}'
        ].join('');

    function _profile_clicked(pub_k){
        location.href = '/html/profile?pub_k='+pub_k;
    }

    function _add_click_funcs(for_content){
        let profile_click = {
            'func' : _profile_clicked,
            'data' : for_content.pub_k
        }
        // left profile img
        _click_map[for_content.id+'-pp'] = profile_click;
        // profile text
        _click_map[for_content.id+'-pt'] = profile_click;

    }

    function _create_contents(){
        _render_arr = [];
        _click_map = {};
        _notes_arr.forEach(function(c_note){
            let add_content = _note_content(c_note);
            _render_arr.push(add_content);
            _add_click_funcs(add_content);
        });
    };

    function _note_content(the_note){
        let name = the_note['pubkey'],
            p,
            attrs,
            pub_k = the_note['pubkey'],
            to_add = {
                'evt': the_note,
                'id' : APP.nostr.gui.uid(),
                'content' : the_note['content'],
                'short_key' : APP.nostr.util.short_key(pub_k),
                'pub_k' : pub_k,
                'picture' : APP.nostr.gui.robo_images.get_url({
                    'text' : pub_k
                }),
                'at_time': dayjs.unix(the_note.created_at).fromNow()
            };

        // insert media tags to content
        to_add.content = _gui.http_media_tags_into_text(to_add.content, _enable_media);
        // do p tag replacement
        to_add.content = do_tag_replacement(to_add.content, the_note.tags)
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

    /*
        returns the_note.content str as we'd like to render it
        i.e. make http::// into <a hrefs>, if inline media and allowed insert <img> etc
    */
    function get_note_html(the_note){
        let http_matches,
            link_tmpl = '<a href="{{url}}">{{url}}</a>',
            img_tmpl = '<img src="{{url}}" width=640 height=auto style="display:block;" />',
            video_tmpl = '<video width=640 height=auto style="display:block" controls>' +
            '<source src="{{url}}" >' +
            'Your browser does not support the video tag.' +
            '</video>',
            tmpl_lookup = {
                'image' : img_tmpl,
                'external_link' : link_tmpl,
                'video' : video_tmpl
            },

            ret = the_note['content'];


        // make str safe for browser render as we're going to insert html tags
        ret = APP.nostr.util.html_escape(ret);

        // add line breaks
        ret = ret.replace(/\n/g,'<br>');
        // look for link like strs
        http_matches = APP.nostr.util.http_matches(ret);
        // do inline media and or link replacement
        if(http_matches!==null){
            http_matches.forEach(function(c_match){
                // how to render, unless enable media is false in which case just the link is out put
                // another level of safety would be that these links are rendered inactive and need the user
                // to perform some action to actaully enable them
                let media_type = _enable_media===true ? _gui.media_lookup(c_match) : 'external_link';
                ret = ret.replace(c_match,Mustache.render(tmpl_lookup[media_type],{
                    'url' : c_match
                }));
            });
        }
        return ret;
    };

    /*
        does replacement of #[n] for pub tags in text
        pretty rough at the moment, the click to is done as a tag rather than our own clicker which may
        cause problems in future...(because with replaceall style we can give each instance if more than one a unique id,
        though browser don't actually seem to care...)
    */
    function do_tag_replacement(text, tags){
        tags.forEach(function(ct, i){
            if((ct[0]=='p')&&(ct.length>0)){
                let regex = _preregex[i],
                    replace_text = APP.nostr.util.short_key(ct[1]),
                    profile;

                if(_profiles.is_loaded()){
                    profile = _profiles.lookup(ct[1]);
                    if(profile!==undefined && profile.attrs.name!==undefined){
                        replace_text = profile.attrs.name;
                    }

                }

                if(regex===undefined){
                    regex = new RegExp('#\\['+i+'\\]','g');
                    _preregex[i] = regex;
                }
                text = text.replace(regex,'<a href="/html/profile?pub_k='+ct[1]+'" style="color:cyan;cursor:pointer;text-decoration: none;;">' + replace_text +'</a>');
            }
        });
        return text;
    };

    function create(args){
        _con = args.con;
        _enable_media = args.enable_media!==undefined ? args.enable_media : false;
        _sub_filter = args.filter!==undefined ? args.filter : {
            'kinds' : new Set([1])
        };

        function set_notes(the_notes){
            _notes_arr = the_notes;
            // makes [] that'll be used render display
            _create_contents();
            // now draw
            redraw();
            _draw_done = true;
        };

        // currently called externally but profiles data should eventually allow us to register that we want to know
        // that profiles have loaded
        function profiles_loaded(profiles){
            if(_draw_done){
                _create_contents();
                redraw();
            }
        }

        function _time_update(){
            _render_arr.forEach(function(c){
                let id = c.id,
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
                _con.prepend(Mustache.render(_row_tmpl,{
                    'notes' : [_render_arr[0]]
                }));

                _add_click_funcs(add_content);
            }
        }

        function redraw(){
            _con.html(Mustache.render(_row_tmpl, {
                'notes' : _render_arr
            }));
        };


        // listen for clicks
        $(_con).on('click', function(e){
            let id = APP.nostr.gui.get_clicked_id(e);
            if(_click_map[id]!==undefined){
                _click_map[id].func(_click_map[id].data);
            }
        });

        // update the since every 30s
        setInterval(_time_update, 1000*30);

        // methods for event_view obj
        return {
            'set_notes' : set_notes,
            // TODO - eventually this won't be required
            'profiles_loaded' : profiles_loaded,
            'add' : add_note
        };
    };

    return {
        'create' : create
    };
}();

APP.nostr.gui.profile_about = function(){
    let _con,
        // global profiles obj
        _profiles = APP.nostr.data.profiles,
        // pub_k we for
        _pub_k,
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
        _tmpl = [
                '<div style="padding-top:2px;">',
                '<span style="display:table-cell;height:128px;width:128px; background-color:#111111;padding-right:10px;" >',
                    // TODO: do something if unable to load pic
                    '{{#picture}}',
                        '<img id="{{pub_k}}-pp" src="{{picture}}" width="128" height="128" style="object-fit: cover;border-radius: 50%;cursor:pointer;" />',
                    '{{/picture}}',
                '</span>',
                '<span style="height:128px;width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                    '<span style="color:cyan">{{pub_k}}</span><br>',
                    '{{#name}}',
                        '<div>',
                            '<span class="profile-about-label">name: </span><span style="display:table-cell">{{name}}</span>',
                        '</div>',
                    '{{/name}}',
                    '{{#about}}',
                        '<div>',
                            '<span class="profile-about-label">about: </span><span style="display:table-cell">{{{about}}}</span>',
                        '</div>',
                    '{{/about}}',
                    '<div id="contacts-con" ></div>',
                    '<div id="followers-con" ></div>',
                '</span>',
                '</div>'
        ].join(''),
        // used to render a limited list of follower/contacts imgs and counts
        _fol_con_sub = [
            '<span class="profile-about-label">{{label}}: </span>',
            '<span style="display:table-cell; width:50px;">{{count}}</span>',
            '{{#images}}',
            '<span style="display:table-cell;">',
                '<img id="{{id}}" src="{{src}}" width="24" height="24" style="object-fit: cover;border-radius: 50%;" />',
            '</span>',
            '{{/images}}',
            '{{#trail}}',
                '<span style="display:table-cell">...</span>',
            '{{/trail}}'
        ].join('');

    function create(args){
        _con = args.con;
        _pub_k = args.pub_k,
        _enable_media = args.enable_media!==undefined ? args.enable_media : true;

        // called when one of our profiles either from follower or contact is clicked
        function _profile_clicked(pub_k){
            location.href = '/html/profile?pub_k='+pub_k;
        }

        function draw(){
            let render_obj = {
                'pub_k' : _pub_k
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
            _contacts = _profile.load_contact_info(function(){
                // max profiles to show
                let _max_show = 10;

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

                    if(to_show_max>_max_show-1){
                        args['trail'] = true;
                        to_show_max = _max_show;
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

                render_contact_section('follows', _contact_con, _profile.contacts);
                render_contact_section('followed by', _follow_con, _profile.followers);

                // listen for clicks
                $(_con).on('click', function(e){
                    let id = APP.nostr.gui.get_clicked_id(e);
                    if(_click_map[id]!==undefined){
                        _click_map[id].func(_click_map[id].data);
                    }
                });

            });

        };

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
        _profiles = APP.nostr.data.profiles,
        // template for profile output
        _row_tmpl = [
            '{{#profiles}}',
                '<div id="{{pub_k}}-pubk" style="padding-top:2px;cursor:pointer">',
                    '<span style="display:table-cell;height:64px;width:128px; background-color:#111111;padding-right:10px;" >',
                        // TODO: do something if unable to load pic
                        '{{#picture}}',
                            '<img src="{{picture}}"  class="profile-pic-small"/>',
                        '{{/picture}}',
                    '</span>',
                    '<span style="height:64px;width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
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

    function create(args){
            // container for list
        let _con = args.con,
            // pubk for the profile we want to look at
            _pub_k = args.pub_k,
            // inline media where we can, where false just the link is inserted
            _enable_media = args.enable_media || false,
            // profile we're viewing
            _the_profile = _profiles.lookup(_pub_k),
            // rendering the_profile.followers or contacts ?
            _view_type = args.view_type==='followers' ? 'followers' : 'contacts',
            // data preped for render to con by _create_render_obj
            _render_obj,
            _do_draw=false;

        // init the data
        _the_profile.load_contact_info(function(){
            try{
                // prep the intial render obj
                _create_render_obj();
                // draw was called before we were ready, draw now
                if(_do_draw){
                    draw();
                }
            }catch(e){
                console.log(e);
            }
        });

        // methods
        function draw(){
            if(_render_obj!==undefined){
                _con.html(Mustache.render(_row_tmpl, _render_obj));
            }else{
                _do_draw = true;
            }
        };

        /*
            fills data that'll be used with template to render
        */
        function _create_render_obj(){
            _render_obj = {
                'profiles': []
            };
            let to_add = _view_type==='followers' ? _the_profile.followers : _the_profile.contacts;

            to_add.forEach(function(c_key){
                _render_obj.profiles.push(_create_render_profile(c_key));
            });

        }

        // create profile render obj to be put in _renderObj['profiles']
        function _create_render_profile(pub_k){
            let the_profile = _profiles.lookup(pub_k),
                render_profile = {
                    'pub_k' : pub_k
                },
                attrs;

            if(the_profile!==undefined){
                attrs = the_profile['attrs'];
                render_profile['picture'] =attrs.picture;
                render_profile['name'] = attrs.name;
                render_profile['about'] = attrs.about;
                if(render_profile.about!==undefined){
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


        // add click events
        _con.on('click', function(e){
            let id = APP.nostr.gui.get_clicked_id(e),
            pub_k;
            if((id!==undefined) && (id.indexOf('-pubk')>0)){
                pub_k = id.replace('-pubk','');
                location.href = '/html/profile?pub_k='+pub_k;
            }
        });

        return {
            'draw': draw
        }
    }

    return {
        'create': create
    }
}();

/*
    using https://robohash.org/ so we can provide unique profile pictures even where user hasn't set one
    url route here so that at some point we can use the lib and create local route to do the same
*/
APP.nostr.gui.robo_images = function(){
    let _root_url = 'https://robohash.org/';

    return {
        // change the server that we're getting robos from
        'set_root': function(url){
            _root_url = url;
        },
        'get_url': function(args){
            let text = args.text;
                // got rid of size as it seems to be included in the hash which means you get a different robo with different
                // size val
//                size = args.size || '128x128';
            return _root_url+'/'+text;
        }
    }

}();
