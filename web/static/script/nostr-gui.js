'use strict';

APP.nostr.gui = function(){
    let _id=0,
        // templates for rendering different media
        // external_link
        _link_tmpl = '<a href="{{url}}">{{text}}</a>',
        // image types e.g. jpg, png
        _img_tmpl = '<img src="{{url}}" width=100% height=auto style="display:block;border-radius:10px;" />',
        // video
        _video_tmpl = '<video width=100% height=auto style="display:block" controls>' +
        '<source src="{{url}}" >' +
        'Your browser does not support the video tag.' +
        '</video>',
        _notifications_con;

    // return a unique id in page
    function uid(){
        _id++;
        return 'guid-'+_id;
    }

    // from clicked el traverses upwards to first el with id if any
    // null if we reach the body el before finding an id
    function get_clicked_id(e, accept_map){
        let ret = null,
            el = e.target;

        while((el.id===undefined || el.id==='' || (accept_map && accept_map[el.id]===undefined)) && el!==document.body){
            el = el.parentNode;
        }

        if(el!=document.body){
            ret = el.id;
        }
        return ret;
    }

    /*
        for given ext returns media type which tells us how to render the content
        anything not understood is returned as external_link and will be rendered as <a> tag
    */
    function media_lookup(ref_str){
        let media_types = {
                'jpg': 'image',
                'jpeg' : 'image',
                'gif': 'image',
                'png': 'image',
                'mp4': 'video',
                'webm' : 'video',
                'mkv' : 'video'
            },
            parts = ref_str.toLowerCase().split('.'),
            ext = parts[parts.length-1],
            ret = 'external';

        if(ext in media_types){
            ret = media_types[ext];
        }
        return ret;
    }

    function http_media_tags_into_text(text, tmpl_lookup){
        // first make the text safe
        let ret = {
                'text': text,
                'image': [],
                'video': [],
                'external': []
            },
            // look for link like strs
            http_matches = APP.nostr.util.http_matches(text),
            enable_media = APP.nostr.data.user.enable_media();

        /* by default everything, if enable_media is false everything will be rendered
            as _link, perhaps enable even this level to be turn off
            or just dont call and just make text safe ... maybe enable media should
            be changed from true/false
            0 - no media whatsoever and text rendered unclickable (user has to physically copy paste)
            1 - no media but hrefs are still rendered
            2 - external media rendered where wee can, links otherwise
            (0 could also just give yes/no alert?)
        */
        tmpl_lookup = tmpl_lookup || {
            'image' : _img_tmpl,
            'external' : _link_tmpl,
            'video' : _video_tmpl
        };

        // and do replacements in the text
        // do inline media and or link replacement
        if(http_matches!==null){
            http_matches.forEach(function(c_match){
                // how to render, unless enable media is false in which case just the link is out put
                // another level of safety would be that these links are rendered inactive and need the user
                // to perform some action to actually enable them
                let media_type = enable_media===true ? APP.nostr.gui.media_lookup(c_match) : 'external',
                    url = c_match;
                // co/com style matches... should we default to https here?
                if(url.indexOf('http')!=0){
                    url = 'http://'+url;
                }

                ret[media_type].push(url);
                ret.text = ret.text.replace(c_match,Mustache.render(tmpl_lookup[media_type],{
                    'url': url,
                    'text': c_match
                }));
            });
        }
        return ret;
    }

    function notification(args){
        /*
            displays a messge at top of the screen that will clear after a few seconds
        */
        let _text = args.text,
            // boostrap alert types
            _type = args.type || 'success',
            _tmpl = APP.nostr.gui.templates.get('notification');
        function do_notification(){
            let _id = APP.nostr.gui.uid();
            _notifications_con.prepend(Mustache.render(_tmpl, {
                'text' : _text,
                'type' : _type,
                'id' : _id
            }));

            setTimeout(function(){

                let el = $('#'+_id);
                el.fadeOut(function(){
                    el.remove();
                });
            },5000);
        }
        // first notification
        if(_notifications_con===undefined){
            $(document.body).prepend(APP.nostr.gui.templates.get('notification-container'));
            _notifications_con = $('#notifications');
        }

        do_notification();
    }

    function get_note_content_for_render(evt){
        let content = evt.content,
            http_data;

        // make safe
        content = APP.nostr.util.html_escape(content);
        // insert media tags to content
        http_data = APP.nostr.gui.http_media_tags_into_text(content);
        content = http_data.text;
        // do p,e [n] tag replacement
        content = APP.nostr.gui.tag_replacement(content, evt.tags);
        // to in text tag replacement (hashtag)
        content = APP.nostr.gui.tag_text_replacement(content, evt.tags);
        // add line breaks
        content = content.replace(/\n/g,'<br>');
        // fix special characters as we're rendering in html el
        content = APP.nostr.util.html_unescape(content);

        return {
            'content': content,
            'external': http_data.external
        }
    }

    return {
        'uid' : uid,
        'get_clicked_id': get_clicked_id,
        'media_lookup' : media_lookup,
        'http_media_tags_into_text' : http_media_tags_into_text,
        'notification' : notification,
        'get_note_content_for_render' : get_note_content_for_render
    }

}();

/*
    given a string of text (events content) and tags
    will return the string with #[n]... replaced with tag links
    for #p and #e events
    maybe just hand event in?
*/
APP.nostr.gui.tag_replacement = function (){
    // cache of tag replacement regexs
    let _preregex = {},
        _replacements = {
            'e' : {
                'prefix' : '&',
                'url' : function(id){
                    return '/html/event?id='+id;
                }
            },
            'p' : {
                'prefix' : '@',
                'url' : function(id){
                    return '/html/profile?pub_k='+id
                },
                'text' : function(id, def){
                    let profile,
                        // if unable to sub
                        ret = def;
                    profile =  APP.nostr.data.profiles.lookup(id);

                    if(profile!==null && profile.attrs.name!==undefined){
                        ret = profile.attrs.name;
                    }

                    return ret;
                }
            }
        };

    // the actual function
    return function(text, tags){
        let tag_type,
            tag_val,
            replace_text,
            regex,
            replacer;

        tags.forEach(function(ct, i){
            tag_type = ct[0];
            tag_val = ct[1];

            if((_replacements[tag_type]!==undefined) && (tag_val!==undefined) && (tag_val!==null)){
                // replacement text is a short version of key
                // unless there is a lookup function provided
                replace_text = APP.nostr.util.short_key(ct[1]);
                regex = _preregex[i];
                if(regex===undefined){
                    regex = new RegExp('#\\['+i+'\\]','g');
                    _preregex[i] = regex;
                }
                replacer = _replacements[tag_type];
                if(replacer.text!==undefined){
                    replace_text = replacer.text(tag_val,replace_text);
                }

                // finally do the replacement
                text = text.replace(regex,'<a href="'+replacer.url(tag_val)+'" style="color:cyan;cursor:pointer;text-decoration: none;">' + replacer.prefix + replace_text +'</a>');
            }
        });
    return text;
    }
}();

APP.nostr.gui.tag_text_replacement = function(){
    /*
        similar to tag_replacement but simpler as just replacing given text with click to tags in the content
        (not [n] style)
        used currently for hashtag
    */
    let _preregex = {},
        _replacements = {
            'hashtag': {
                'get_match': function(val){
                    return get_regex('#'+val+'($|\\s)');
                },
                'get_replacement': function(val){
                    return '<a href="/html/event_search.html?search_str=%23'+ val +'" style="color:cyan;cursor:pointer;text-decoration: none;">#'+ val +'</a>'
                }
            }
        };

    function get_regex(val){
        let regex = _preregex[val];
        if(regex===undefined){
            regex = new RegExp(val,'g');
            _preregex[val] = regex;
        }
        return regex;
    }


    return function(text, tags){
        let todo,
            t_name,
            t_val;

        tags.forEach(function(c_tag,i){
            t_name = c_tag[0];
            todo = _replacements[t_name];
            if(todo){
                t_val = c_tag[1];
                text = text.replace(todo.get_match(t_val), todo.get_replacement(t_val+'$1'));
            }
        });
        return text;
    };
}();

APP.nostr.gui.util = function(){
    let _profiles = APP.nostr.data.profiles,
        _user = APP.nostr.data.user;

    function profile_picture_url(p){
        // p should either be pub_k or {} profile
        let pub_k,
            enable_media = _user.enable_media(),
            ret;

        if(typeof(p)==='string'){
            pub_k = p;
            p = _profiles.lookup(p)
        }else{
            pub_k = p.pub_k;
        }

        if(p!==null && p.attrs && p.attrs.picture && enable_media){
            ret = p.attrs.picture;
        }else{
            ret = APP.nostr.gui.robo_images.get_url({
                'text' : pub_k
            });
        }
        return ret;
    }




    return {
        'profile_picture_url' : profile_picture_url
    }
}();


/*
    renders the section at the top of the screen
*/
APP.nostr.gui.header = function(){
    let _con,
        _current_profile,
        _profile_but,
        _home_but,
        _event_search_but,
        _profile_search_but,
        _relay_but,
        _message_but,
        _enable_media;

    // watches which profile we're using and calls set_profile_button when it changes
    function watch_profile(){
        // look for future updates
        APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
            if(window.location.pathname!=='/'){
                window.location='/';
            }else{
                _current_profile = data;
                set_profile_button();
                set_messages();
            }
        });
    }

    function watch_relay(){
        // look for future updates
        APP.nostr.data.event.add_listener('relay_status',function(of_type, data){
            _relay_but.css('background-color', relay_color(data));
//            if(data.connected){
//                if(data.connect_count===data.relay_count){
//                    _relay_but.css('background-color', 'green');
//                }else{
//                    _relay_but.css('background-color', 'orange');
//                }
//            }else{
//                _relay_but.css('background-color', 'red');
//            }

        });
    }

    function relay_color(state){
        let ret = 'red';
        if(state.connected){
            if(state.connect_count===state.relay_count){
                ret = 'green';
            }else{
                ret = 'orange';
            }
        }
        return ret;
    }

    // actually update the image on the profile button
    function set_profile_button(){
        let url;
        if(_current_profile.pub_k===undefined){
            _profile_but.html(APP.nostr.gui.templates.get('no_user_profile_button'));
            _profile_but.css('background-image','');
        }else{
            _profile_but.html('');
            _profile_but.css('background-size',' cover');
//            if(_current_profile.attrs && _current_profile.attrs.picture && _enable_media){
//                url = _current_profile.attrs.picture;
//            }else{
//                url = APP.nostr.gui.robo_images.get_url({
//                    'text' : _current_profile.pub_k
//                });
//            }
            url = APP.nostr.gui.util.profile_picture_url(_current_profile);
            _profile_but.css('background-image','url("'+url+'")');
        }
    }

    function set_messages(){
        if(_current_profile.pub_k===undefined){
            _message_but.css('display','none');
        }else{
            _message_but.css('display','');
        }

    }

    function render_head(){
        // the intial draw with state we have on page load
        let state = {
            'message_style': function(){
                return _current_profile.pub_k!==undefined ? 'style="display:default;"' : 'style="display:none;"';
            },
            'relay_style': function(){
                let relay_status = APP.nostr.data.relay_status.get();
                return 'background-color:'+relay_color(relay_status);
            }

        };

        _con.html(Mustache.render(APP.nostr.gui.templates.get('head'),state));
    }

    function create(args){
        args = args || {};
        _con = args.con || $('#header-con');
        _current_profile = APP.nostr.data.user.profile();
        _enable_media = APP.nostr.data.user.enable_media(),
        // draw the header bar
        render_head();
        // grab buttons
        _profile_but = $('#profile-but');
        _home_but = $('#home-but');
        _event_search_but = $('#event-search-but');
        _profile_search_but = $('#profile-search-but');
        _message_but = $('#message-but');
        _relay_but = $('#relay-but');

        set_profile_button();
        watch_profile();
        watch_relay();

        // add events
        _profile_but.on('click', function(){
            APP.nostr.gui.profile_select_modal.show();
        });

        _home_but.on('click', function(){
            if(window.location.pathname!=='/'){
                window.location='/';
            }else{
                APP.nostr.data.event.fire_event('home', null);
            }
        });

        _message_but.on('click', function(){
            if(window.location.pathname!=='/html/messages.html'){
                window.location='/html/messages.html';
            }
        });

        _event_search_but.on('click', function(){
            location.href = '/html/event_search.html';
        });

        _profile_search_but.on('click', function(){
            location.href = '/html/profile_search.html';
        });

        _relay_but.on('click', function(){
            APP.nostr.gui.relay_view_modal.show();
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
                        '<svg class="bi-post" style="height:100%;width:100%;">',
                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#send-plus"/>',
                        '</svg>',
                '</div>',
            '</div>'
        ].join(''),
        _post_el,
        _post_text_area

    function check_show(p){
        if(p.pub_k===undefined){
            _post_el.hide();
        }else{
            _post_el.show();
        }
    }

    function create(){
        // should only ever be called once anyway but just incase
        if(_post_el===undefined){
            $(document.body).prepend(_post_html);
            _post_el = $('#post-button');
            _post_el.on('click', function(){
                APP.nostr.gui.post_modal.show();
            });
            check_show(APP.nostr.data.user.profile());

            // if profile changes we check that it's a user that can post
            APP.nostr.data.event.add_listener('profile_set',function(of_type, data){
                check_show(data);
            });



        }
    }

    return {
        'create' : create
    }
}();

APP.nostr.gui.tabs = function(){
    /*
        creates a tabbed area, probably only used to set up the, and events for moving between tabs
        but otherwise caller can deal with rendering the content
    */
    let _head_tmpl = [
        '<ul class="nav nav-tabs" style="overflow:hidden;height:32px;" >',
            '{{#tabs}}',
                '<li class="{{active}}" ><a style="padding:3px;" data-toggle="tab" href="#{{tab-ref}}">{{tab-title}}</a></li>',
            '{{/tabs}}',
            // extra area for e.g. search field,
            '<span id="{{id}}-tool-con" class="tab-tool-area" >',
            '</span>',
        '</ul>'
        ].join(''),
        _body_tmpl = [
            '<div class="tab-content" style="overflow-y:auto;height:calc(100% - 32px);padding-right:5px;" >',
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
            _tabs = args.tabs||[],
            // our own id
            _id = APP.nostr.gui.uid(),
            // area to the right of tab heads for caller to render additional gui elements
            _tool_con,
            // index of currently selected tab
            _cur_index,
            // function called on a tab being selected
            _on_tab_change = args.on_tab_change;

        function create_render_obj(){
            _render_obj = {
                'id' : _id,
                'tabs' : []
            };
            _tabs.forEach(function(c_tab, i){
                let to_add = {};
                to_add['tab-title'] = c_tab.title!==undefined ? c_tab.title : '?no title?';
                to_add['tab-ref'] = c_tab.id!==undefined ? c_tab.id : APP.nostr.gui.uid();
                to_add['content'] = c_tab.content!==undefined ? c_tab.content : _default_content;
                if(c_tab.active===true){
                    to_add['active'] = 'active';
                    to_add['transition'] = 'fade in';
                    _cur_index = i;
                }else{
                    to_add['transition'] = 'fade';
                }
                _render_obj.tabs.push(to_add);
            });

            // no active tab given we'll set to 0
            if(_tabs.length>0 && _cur_index===undefined){
                _render_obj.tabs[0]['active'] = 'active';
                _render_obj.tabs[0]['transition'] = 'fade in';
                _cur_index = 0;
            }

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
            // and the tool area
            _tool_con = $("#"+_id+"-tool-con");

            // before anims
            $('.nav-tabs a').on('show.bs.tab', function(e){
                let id = e.currentTarget.href.split('#')[1];
                for(var i=0;i<_render_obj.tabs.length;i++){
                    if(_render_obj.tabs[i]['tab-ref']===id){
                        _cur_index = i;
                    }
                }

                if(typeof(_on_tab_change)==='function'){
                    _on_tab_change(_cur_index, _render_obj.tabs[_cur_index]['tab_content_con']);
                }

            });

            // after anims
            $('.nav-tabs a').on('shown.bs.tab', function(e){
            });

            // not sure we should count this as a change??
            // anyway on first draw fire _on_tab_change for selected tab
            if(typeof(_on_tab_change)==='function'){
                _on_tab_change(_cur_index, _render_obj.tabs[_cur_index]['tab_content_con']);
            }

        }


        /*
            TODO: ident is always the tab index at the moment,
             by id/title might be useful in the future
        */
        function get_tab(ident){
            let ret = {},
                tab_obj = _render_obj.tabs[ident];

            // now copy relevant bits
            ret['content-con'] = tab_obj['tab_content_con'];

            return ret;
        }

        function set_tab(ident){
            let tab_obj = _render_obj.tabs[ident],
                tab_a = $('a[href="#'+ tab_obj['tab-ref'] +'"]');

            tab_a.tab('show');
            _cur_index = ident;

        }


        function init(){
            create_render_obj();
        }
        // do the init
        init();

        return {
            'draw': draw,
            'get_tab' : get_tab,
            'get_tool_con' : function(){
                return _tool_con;
            },
            'get_selected_tab' : function(){
                return get_tab(_cur_index);
            },
            'get_selected_index' : function(){
                return _cur_index;
            },
            'set_selected_tab' : function(index){
                set_tab(index);
            }

        };
    };

    return {
        'create' : create
    }
}();

APP.nostr.gui.list = function(){
    const CHUNK_SIZE = 50,
        CHUNK_DELAY = 200,
        MAX_DRAW = null;

    function create(args){
        let _con = args.con,
            _data = args.data || [],
            _filter = args.filter || false,
            _row_tmpl = args.row_tmpl,
            _row_render = args.row_render,
            _render_chunk = args.chunk || true,
            _chunk_size = args.chunk_size || CHUNK_SIZE,
            _chunk_delay = args.chunk_delay || CHUNK_DELAY,
            _draw_timer,
            _uid = APP.nostr.gui.uid(),
            _click = args.click,
            _empty_message = args.empty_message || 'nothing to show!',
            _max_draw = args.max_draw || MAX_DRAW;

        // draw the entire list
        // TODO: chunk draw, max draw amount
        // future
        function draw(){
            let to_draw = _data.length;
            if(_max_draw!==null && _data.length>_max_draw){
                to_draw = _max_draw;
            }

            clearInterval(_draw_timer);
            _con.html('');
            if(to_draw===0){
                _con.html(_empty_message);
            }else if(_render_chunk && to_draw> _chunk_size){
                let c_start=0,
                    c_end=_chunk_size,
                    last_block = false;

                function _prog_draw(){
                    c_start = draw_chunk(c_start, c_end);
                    if(!last_block){
                        c_end+=_chunk_size;
                        if(c_end>= to_draw){
                            c_end = to_draw;
                            last_block = true
                        }


                        _draw_timer = setTimeout(_prog_draw,CHUNK_DELAY);

                    }


                }

                _prog_draw();
//                _draw_timer = setTimeout(_prog_draw,CHUNK_DELAY);


            }else{
                draw_chunk(0, to_draw);
            }
        }

        function draw_chunk(start,end){
            let draw_arr = [],
                r_obj,
                pos;
            for(pos=start;pos<end;pos++){
                r_obj = _data[pos];
                if((_filter===false)||(_filter(r_obj))){
                    draw_arr.push(get_row_html(r_obj, pos));
                }else if(end<_data.length){
                    // as we're not drawing move the end on
                    end+=1;
                }
            }
//            console.log(draw_arr);
            _con.append(draw_arr.join(''));

            return pos;
        }

        function get_row_html(r_obj, i){
            let ret,
                r_id = _uid+'-'+i;

            if(_row_render){
                ret = _row_render(r_obj, i);
            }else if(_row_tmpl!==undefined){
                ret = Mustache.render(_row_tmpl, r_obj);
            }else{
                ret = '?list row?';
            }
            return ret;
        }

        // add click to con
        if(_click!==undefined){
            $(_con).on('click', function(e){
                _click(APP.nostr.gui.get_clicked_id(e));
            });
        };


        return {
            'draw' : draw,
            'set_data' : function(data){
                _data = data;
            },
            'data' : function(data){
                if(data!==undefined){
                    _data = data;
                }
                return _data;
            }

        };
    }

    return {
        'create' : create
    }
}();

APP.nostr.gui.event_view = function(){
        // short ref
    let _gui = APP.nostr.gui,
        _data = APP.nostr.data;

    function _profile_clicked(pub_k){
        location.href = '/html/profile?pub_k='+pub_k;
    }

    function get_event_parent(evt){
        let parent = null,
            tag;
        for(let j=0;j<evt.tags.length;j++){
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
            _enable_media = APP.nostr.data.user.enable_media(),
            // filter for notes that will be added to notes_arr
            // not that currently only applied on add, the list you create with is assumed to already be filtered
            // like nostr filter but minimal impl just for what we need
            // TODO: Fix this make filter obj?
            _sub_filter = args.filter!==undefined ? args.filter : APP.nostr.data.filter.create([]),
            // track which event details are expanded
            _expand_state = {},
            // underlying APP.nostr.gui.list
            _my_list,
            // interval timer for updating times
            _time_interval,
            // for loading profiles
            _profiles = APP.nostr.data.profiles,
            // for preview render external links
            _web_preview_tmpl = APP.nostr.gui.templates.get('web-preview');

        function uevent_id(event_id){
            return _uid+'-'+event_id;
        }

        function _event_clicked(evt){
            let root = '',
                // the parent info only exits on the render obj currently
                render_evt = _event_map[evt.id].render_event;

            if(render_evt['missing_parent']!==undefined && render_evt.missing_parent===true){
                root = '&root='+get_event_parent(evt);
            }
            location.href = '/html/event?id='+evt.id+root;
        }

        function _note_content(the_note){
            let name = the_note['pubkey'],
            p,
            attrs,
            pub_k = the_note['pubkey'],
            preview_data,
            note_content = _gui.get_note_content_for_render(the_note, _enable_media),
            preview_url,
            to_add = {
                'is_parent' : the_note.is_parent,
                'missing_parent' : the_note.missing_parent,
                'is_child' : the_note.is_child,
                'uid' : _uid,
                'evt': the_note,
                'event_id' : the_note.id,
                'short_event_id' : APP.nostr.util.short_key(the_note.id),
                'content' : note_content.content,
                'short_key' : APP.nostr.util.short_key(pub_k),
                'pub_k' : pub_k,
                'picture' : APP.nostr.gui.robo_images.get_url({
                    'text' : pub_k
                }),
                'at_time': dayjs.unix(the_note.created_at).fromNow(),
                'can_reply' : function(){
                    return APP.nostr.data.user.profile().pub_k!==undefined;
                },
                'subject': the_note.get_first_tag_value('subject')
            };

            // should only happen if external media and web preview is allowed
            if(note_content.external.length>0){
                preview_url = note_content.external[0];
                if(to_add_preview(preview_url)){
                    to_add.external = preview_url;
                    preview_data = _data.state.get(note_content.external[0]);
                    if(preview_data!==null){
                        preview_data = JSON.parse(preview_data);
                        add_preview_content(to_add, preview_data);
                    }
                }
            }

            p = _profiles.lookup(name);
            if(p!==null){
                attrs = p['attrs'];
                to_add['name'] = attrs['name'];
                if(_enable_media){
                    to_add.picture = p.picture;
                }
            }

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

        function to_add_preview(url){
            let ret = false,
                url_split = url.split('.'),
                ignore = ['://twitter.com/'];

            function is_ignore(){
                let ret = false;
                for(let i=0;i<ignore.length;i++){
                    if(url.indexOf(ignore[i])>=0){
                        ret = true;
                        break;
                    }
                }
                return ret;
            }

            if(APP.nostr.data.user.enable_web_preview()){

                // .onions come through are url regex - perhaps we could not match?
                // anyway we can't preview these so remove...
                // possubly we're want to not preview others too anyway
                if((url_split[url_split.length-1].indexOf('onion')!=0) && (!is_ignore())){
                    ret = true;
                };
            }
            return ret;
        }

        function _get_preview_event(id){
            let evt_data = _event_map[id].render_event,
                url = evt_data.external,
                my_el = $('#'+_uid+'-'+id+'-preview');

            if(evt_data.preview!==true){
                APP.remote.web_preview({
                    'url': url,
                    'success': function(data){
                        add_preview_content(evt_data, data);
                        my_el.html(Mustache.render(_web_preview_tmpl, {
                            'wp_img': data.img,
                            'wp_title': data.title,
                            'wp_description': data.description
                        }));
                        _data.state.put(url, JSON.stringify(data));
                    }
                });
            // already showing, clicking goes to
            }else{
                window.location=url;
            }
        }

        function add_preview_content(r_event, p_data){
            r_event.preview = true;
            r_event.wp_img = p_data.img;
            r_event.wp_title = p_data.title;
            r_event.wp_description = p_data.description;
        }

        function _row_render(r_obj, i){
            return Mustache.render(_gui.templates.get('event'), r_obj,{
                'profile' : _gui.templates.get('event-profile'),
                'path' : _gui.templates.get('event-path'),
                'content' : _gui.templates.get('event-content'),
                'actions' : _gui.templates.get('event-actions'),
                'preview' : _web_preview_tmpl
            });
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
                _event_map[c_evt.id].render_event = add_content;
            });

            if(_my_list===undefined){
                _my_list = APP.nostr.gui.list.create({
                    'con' : _con,
                    'data' : _render_arr,
                    'row_render' : _row_render,
                    'click' : function(id){
                        let parts = id.replace(_uid+'-','').split('-'),
                            event_id = parts[0],
                            type = parts[1],
                            evt = _event_map[event_id] !==undefined ? _event_map[event_id].event : null;
                        if(type==='expand'){
                            _expand_event(evt);
                        }else if(type==='pt' || type==='pp'){
                           _profile_clicked(evt.pubkey);
                        }else if(type==='reply'){
                            // we actually pass the render_event, probably it'd be better if it could work from just evt
                            // maybe once we make the event render a bit more sane...
                            APP.nostr.gui.post_modal.show({
                                'type' : 'reply',
                                'event' : _event_map[event_id].event
                            });
                        // anywhere else click to event, to change
                        }else if(type==='preview'){
                            _get_preview_event(event_id);
                        }else if(evt!==null && type==='content'){
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
                // everything is done on a copy of the event as we're going to add some of
                // our own fields
                c_evt = c_evt.copy();

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
                    add_children(roots[c_evt.id]);

                    roots[c_evt.id].added=true;
                // child of a parent, draw parent if we have it and all children
                }else if(parent!==null && roots[parent].added!==true){
                    // do we have parent event
                    if(roots[parent].event){
                        roots[parent].event.is_parent = true;
                        ret.push(roots[parent].event);
                    }
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
            load_profiles();
            _create_contents();
        };

        function load_profiles(){
            let pub_ks = new Set([]);
            _notes_arr.forEach(function(c_note){
                pub_ks.add(c_note.pubkey);
                // also add all the p tags so we'll be able to replacements if needed
                c_note.tags.forEach(function(c_tag){
                    if(c_tag.length>=1 && c_tag[0]=='p'){
                        pub_ks.add(c_tag[1]);
                    }
                });

            });

            _profiles.fetch({
                'pub_ks': pub_ks,
                'on_load' : function(){
                    _create_contents();
                }
            });

        };


        /*
            note filter probably doesn't work quite as you'd expect...Its only applied
            in add_note to see if new events should be shown... We expect all the data we get at
            create to be ok for display (-- though it'd be easy to run through filter too)
        */
        function set_filter(filter){
            _sub_filter = filter;
        }

        function _time_update(){
            // think we've been killed ..?
            if(_render_arr===undefined){
                clearInterval(_time_interval);
                return;
            }

            _render_arr.forEach(function(c){
                let id = uevent_id(c.event_id),
                    ntime = dayjs.unix(c['evt'].created_at).fromNow();

                // update in render obj, at the moment it never gets reused anyhow
                c['at_time'] = ntime;
                // actually update onscreen
                $('#'+id+'-time').html(ntime);
            });
        }

        function add_note(evt){
            // does the event pass our filter and also just double check we don't already have it
            // the server should be trying not to send us duplicates anyhow
            if(_sub_filter.test(evt) && _event_map[evt.id]===undefined){
//                let add_content = _note_content(evt);
                // just insert the new event
                _notes_arr.unshift(evt);
                // this results in a full recheck of order and redraw
                // probably we could do more efficent but this is simplest and will do for now
//                _create_contents();
                // call load profiles cause it'll make sure we have the profile info before
                // redrawing, ajax call might be made
                load_profiles();
            }
        }

        // update the since every 30s
        _time_update = setInterval(_time_update, 1000*30);

        // methods for event_view obj
        return {
            'set_notes' : set_notes,
            'set_filter' : set_filter,
            'add' : add_note,
            'draw' : function(){
                _my_list.draw();
            }
        };
    };

    return {
        'create' : create
    };
}();

APP.nostr.gui.profile_about = function(){
    // if showing max n of preview followers in head
    const MAX_PREVIEW_PROFILES = 10,
        _tmpl = [
                // TODO: merge with template we use in lists?
                '<div style="height:100%;padding-top:2px;overflow-y:auto;">',
              //  '<span style="display:table-cell;width:128px; background-color:#111111;padding-right:10px;" >',
                    // TODO: do something if unable to load pic
                    '{{#picture}}',
                        '<img style="display:inline-block;float:left;" id="{{pub_k}}-pp" src="{{picture}}" class="{{profile_pic_class}}" />',
                    '{{/picture}}',
                    '<div style="text-align: justify; vertical-align:top;word-break: break-all;">',
                        '{{#name}}',
                            '<span>{{name}}@</span>',
                        '{{/name}}',
                        '<span class="pubkey-text" >{{pub_k}}</span>',
                        // options that we can if we're in profile and this is not our profile
                        '{{#other_profile}}',
                            '<span style="float:right;">',
                                '<svg id="{{pub_k}}-dm" class="bi" >',
                                    '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#envelope-fill"/>',
                                '</svg>',
                                '{{#follows}}',
                                    '<svg id="{{pub_k}}-fol" class="bi" >',
                                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star-fill"/>',
                                    '</svg>',
                                '{{/follows}}',
                                '{{^follows}}',
                                    '<svg id="{{pub_k}}-fol" class="bi" >',
                                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star"/>',
                                    '</svg>',
                                '{{/follows}}',
                            '</span>',
                        '{{/other_profile}}',
                        '{{#about}}',
                            '<div style="max-height:48px;overflow:auto;">',
                                '{{{about}}}',
                            '</div>',
                        '{{/about}}',
                    '<div id="contacts-con" ></div>',
                    '<div id="followers-con" ></div>',
                    '</div>',
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
            _profile = args.profile,
            // add this in and when false just render our own random images for profiles rather than going to external link
            // in future we could let the user provide there own images for others profiles
            //_enable_media = true,
            // follower info here
            _follow_con,
            // and contacts
            _contact_con,
            // gui to click func map
            _click_map = {},
            _enable_media = APP.nostr.data.user.enable_media(),
            _show_follow_section = args.show_follows!=undefined ? args.show_follows : true,
            _current_profile = APP.nostr.data.user.profile(),
            _render_obj;

        // called when one of our profiles either from follower or contact is clicked
        function _profile_clicked(pub_k){
            location.href = '/html/profile?pub_k='+pub_k;
        }


        function create_render_obj(){
            let attrs;

            _render_obj = {
                'pub_k' : _pub_k,
                'profile_pic_class': _show_follow_section===true ? 'profile-pic-large' : 'profile-pic-small'
            };

            // fill from the profile if we found it
            if(_profile!==null){
                attrs = _profile['attrs'];
                _render_obj['picture'] =attrs.picture;
                _render_obj['name'] = attrs.name;
                _render_obj['about'] = attrs.about;
                if(_render_obj.about!==undefined){
                    _render_obj.about = APP.nostr.gui.http_media_tags_into_text(_render_obj.about, false).text;
                    _render_obj.about = _render_obj.about.replace().replace(/\n/g,'<br>');
                }
                // we'll be able to dm, (mute future?) and follow unfollow
                if(_current_profile.pub_k!==undefined && _current_profile.pub_k!==_profile.pub_k){
                    _render_obj.other_profile = true;
                    _render_obj.follows = _current_profile.contacts.includes(_profile.pub_k);
                }
            }
            // give a picture based on pub_k event if no pic or media turned off
            if((_render_obj.picture===undefined) || (_render_obj.picture==='') ||
                (_render_obj.picture===null) ||
                    (_enable_media===false)){
                _render_obj.picture = APP.nostr.gui.robo_images.get_url({
                    'text' : _pub_k
                });
            }
        }

        function draw(){
            create_render_obj();
            _con.html(Mustache.render(_tmpl, _render_obj));
            // grab the follow and contact areas
            _contact_con = $('#contacts-con');
            _follow_con = $('#followers-con');
            // wait for follower/contact info to be loaded
            if(_show_follow_section){
                render_followers();
            }
        };

        function set_follow_el(is_following){
            _render_obj.follows = _current_profile.contacts.includes(_profile.pub_k);
            draw();
        }

        function render_followers(){
            function mod_follows(followed_by){
                // we don't reget followed by so we just do a base off if we follow or not +/- 1
                let ret = [];
                if(_current_profile.contacts && _current_profile.contacts.includes(_profile.pub_k)){
                    ret.push($.extend({},_current_profile));
                }

                followed_by.forEach(function(c_f){
                    if(c_f.pub_k!==_current_profile.pub_k){
                        ret.push(c_f);
                    }
                });

                return ret;
            }
            render_contact_section('follows', _contact_con, _profile.contacts);
            render_contact_section('followed by', _follow_con, mod_follows(_profile.followed_by));
        }

        function render_contact_section(label, con, profiles){
            let args = {
                'label': label,
                'count': profiles.length,
                'images' : []
            },
            to_show_max = profiles.length,
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
//                c_p = _profiles.lookup(pub_ks[i]);
                c_p = profiles[i];
                // a profile doesn't necessarily exist
                if(c_p && c_p.attrs && c_p.attrs.picture!==undefined && _enable_media){
                    img_src = c_p.attrs.picture;
                }else{
                    img_src = APP.nostr.gui.robo_images.get_url({
                        'text' : c_p.pub_k
                    });
                }

                args.images.push({
                    'id' : id,
                    'src' : img_src
                })

                _click_map[id] = {
                    'func' : _profile_clicked,
                    'data' : c_p.pub_k
                };
            }

            // and render
            con.html(Mustache.render(_fol_con_sub, args));
        }

        function add_events(){
            $(_con).on('click', function(e){
                let id = APP.nostr.gui.get_clicked_id(e);
                if(id!==null){
                    if(id.indexOf('-dm')>=0){
                        APP.nostr.gui.post_modal.show({
                            'kind' : 4,
                            'pub_k': id.replace('-dm','')
                        });
                    }else if(id.indexOf('-fol')>=0){
                        APP.nostr.data.user.follow_toggle(id.replace('-fol',''), function(data){
                            _current_profile = data.profile;
                            set_follow_el(_current_profile.contacts.includes(_pub_k));
                        });
                    }else if(_click_map[id]!==undefined){
                        _click_map[id].func(_click_map[id].data);
                    }


                }
            });

            APP.nostr.data.event.add_listener('contacts_updated', function(of_type, data){
                if(data.contacts.join(':')!==_current_profile.contacts.join(':')){
                    _current_profile = APP.nostr.data.user.profile();
                    set_follow_el(_current_profile.contacts.includes(_pub_k));
                }
            });
        }

        function init(){
            if(_profile===undefined){

                APP.remote.load_profile({
                    'pub_k': _pub_k,
                    'include_followers': _show_follow_section,
                    'include_contacts': _show_follow_section,
                    'full_profiles' : _show_follow_section,
                    'success' : function(data){
                        if(data.error!==undefined){
                            // probably we don't have the profile (or it doesn't exist it's not a requirement to post)
                            // NOTE thet could still have contacts though as it is we wouldn't return them currently
                            // tofix
                            _profile = {
                                'pub_k' : _pub_k,
                                'attrs' : {
                                    'about' : data.error
                                },
                                'contacts' : [],
                                'followed_by' : []
                            };
                        }else{
                            _profile = data;
                        }

                        try{
                            draw();
                            add_events();
                        }catch(e){
                            console.log(e)
                        }

                    }
                });

            }else{
                _pub_k = _profile.pub_k;
                draw();
                add_events();
            }
        }
        init();

        // methods for event_view obj
        return {
//            'profiles_loaded' : draw
        };
    };

    return {
        'create' : create
    };
}();

APP.nostr.gui.event_detail = function(){
    let _nv_template = [
            '{{#fields}}',
                '<div style="font-weight:bold;">{{name}}</div>',
                '<div id="{{uid}}-{{name}}" class="event-detail" style="{{clickable}}" >{{{value}}}</div>',
            '{{/fields}}',
            '<div style="font-weight:bold;">tags</div>',
            '{{^tags}}',
                '<div class="event-detail" >[]</div>',
            '{{/tags}}',
            '{{#tags}}',
                '<div style="font-weight:bold;">{{name}}</div>',
                '<div id="{{uid}}-{{name}}" class="event-detail" >{{.}}</div>',
            '{{/tags}}',

        ].join(''),
        _clicks = new Set(['event_id','sig','pubkey']);

    function create(args){
        let _con = args.con,
            _event = args.event,
            _render_obj,
            _uid = APP.nostr.gui.uid(),
            _my_tabs = APP.nostr.gui.tabs.create({
                'con' : _con,
                'on_tab_change': function(i, con){
                    if(i==2){
                        con.html('loading...');
                        let tmpl = [
                            '{{#relays}}',
                                '<div>{{relay_url}}</div>',
                            '{{/relays}}'
                        ].join('');
                        APP.remote.event_relay({
                            'event_id' : _event.id,
                            'success' : function(data){
                                con.html(Mustache.render(tmpl, data));
                            }
                        });
                    }
                },
                'tabs' : [
                    {
                        'title' : 'fields',
                    },
                    {
                        'title' : 'raw'
                    },
                    {
                        'title' : 'relays'
                    }
                ]
            });
        // methods
        function create_render_obj(){
            let block_split = function(oval){
                let blocks = oval.match(/.{1,32}/g);

                return blocks.join('<br>');
            },
            to_add = [
                {
                    'title' : 'event_id',
                    'field' : 'id',
                    'func' : block_split
                },
                {
                    'title' : 'created_at',
                    'func' : function(val){
                        return dayjs.unix(val).format();
                    }
                },
                {
                    'title' : 'kind'
                },
                {
                    'title' : 'content',
                    'func': APP.nostr.util.html_escape
                },
                {
                    'title' : 'pubkey',
                    'func' : block_split
                },
                {
                    'title' : 'sig',
                    'func' : block_split
                }
            ];

            _render_obj = {
                'fields': [],
                'tags' : _event.tags
            }

            to_add.forEach(function(c_f,i){
                let val = _event[c_f.field!==undefined ? c_f.field : c_f.title];
                if(c_f.func){
                    val = c_f.func(val);
                }
                _render_obj.fields.push({
                    'name' : c_f.title,
                    'value' : val,
                    'uid' : _uid,
                    'clickable' : navigator.clipboard!==undefined && _clicks.has(c_f.title) ? 'cursor:pointer;' : ''
                });
            });

        }

        function render_fields(){
            _my_tabs.get_tab(0)['content-con'].html(Mustache.render(_nv_template, _render_obj));
        }

        function render_raw(){
            _my_tabs.get_tab(1)['content-con'].html('<div style="white-space:pre-wrap;max-width:100%" class="event-detail" >' + APP.nostr.util.html_escape(JSON.stringify(_event, null, 2))+ '</div>');
        }

        function render_relays(){

        }

        function draw(){
            if(_render_obj===undefined){
                create_render_obj();
            }
            _my_tabs.draw();
            render_fields();
            render_raw();


            $(_con).on('click', function(e){
                let id = APP.nostr.gui.get_clicked_id(e);
                if(id.indexOf(_uid)>=0){
                    id = id.replace(_uid+'-','');
                    if(_clicks.has(id)){
                        id = id==='event_id' ? 'id' : id;
                        APP.nostr.util.copy_clipboard(_event[id], _event[id]+' - copied to clipboard');
                    }
                    e.stopPropagation()
                }

            });

        }

        // return funcs
        return {
            'draw': draw
        }
    }

    return {
        'create' : create
    };
}();

APP.nostr.gui.profile_edit = function(){

    function create(args){
        let con = args.con,
            pub_k = args.pub_k,
            pic_con,
            edit_con,
            save_but,
            key_but,
            publish_but,
            img_tmpl = [
                '<img style="margin-left: auto;margin-right: auto;display:block;" src="{{picture}}" class="profile-pic-large"  />'
            ].join(''),
            input_tmpl = [
                '<form>',
                    // private key, in the normal case this shouldn't be visible, only when linking to an existing profile
                    // or creating new
//                    '{{^can_sign}}',
//                        '{{#pub_k}}',
//                            '<div class="form-group">',
//                                '<label for="private-key">private key</label>',
//                                '<input type="text" class="form-control" id="private-key" aria-describedby="private key" placeholder="{{enter private key}}" value="{{private-key}}" >',
//                            '</div>',
//                        '{{/pub_k}}',
//                    '{{/can_sign}}',
                    '<div class="form-group">',
                        '<label for="profile_name">profile name</label>',
                        '<input {{disabled}} type="text" class="form-control" id="profile-name" aria-describedby="profile name" placeholder="local name for this profile" value="{{profile_name}}" >',
                    '</div>',
                    '<div class="form-group">',
                        '<label for="picture-url">picture url</label>',
                        '<input {{disabled}} type="text" class="form-control" id="picture-url" aria-describedby="picture url" placeholder="enter picture url" value="{{picture}}" >',
                    '</div>',
                    '<div class="form-group">',
                        '<label for="pname">name</label>',
                        '<input {{disabled}} type="text" class="form-control" id="pname" aria-describedby="alternative display for public key" placeholder="alternative display for public key" value="{{name}}">',
                    '</div>',
                    '<div class="form-group">',
                        '<label for="about">about</label>',
                        '<textarea {{disabled}} class="form-control" id="about" aria-describedby="descriptive text for this profile" ',
                        'placeholder="enter description for profile" rows=4 style="height:96px" maxlength=150>',
                        '{{about}}</textarea>',
                    '</div>',
                '</form>'
            ].join(''),
            // profile original data as we want it
            o_profile,
            // same with users edits applied
            e_profile,
            // o_profile as str to check changes
            o_str,
            // obj for render
            r_obj,
            mode;

        function init(){
            // initial page show
            let the_profile = APP.nostr.data.profiles.lookup(pub_k)
            set_state(the_profile)
            init_page();
        }

        function init_page(){
            // basic screen render, shows profile we're editing and what mode we're in
            con.html(Mustache.render(APP.nostr.gui.templates.get('screen-profile-struct'),{
                'mode' : mode,
                'pub_k' : pub_k,
                // if not can sign then the shows a button where we can give priv key so that we can edit or link existing
                'link_existing' : mode==='create',
                'link_suggest' : mode==='view',
                'view_priv' : mode==='edit'
            }));
            // grab screen widgets
            pic_con = $('#picture-con');
            edit_con = $('#edit-con');
            save_but = $('#save-button');
            publish_but = $('#publish-button');
            // action of this button depends on mode
            key_but = $('#private_key');

            set_r_obj();
            draw();
        }


       function set_state(profile){
            o_profile = profile;
            if(o_profile===null){
                o_profile = {
                    'pub_k' : /[0-9A-Fa-f]{64}/g.test(pub_k) ? pub_k : '',
                    'attrs' : {},
                    'can_sign' : false
                };
            }

            mode = 'edit';
            if(!o_profile.can_sign){
                if(o_profile.pub_k===''){
                    mode = 'create'
                }else{
                    mode = 'view';
                }
            };

            // make the profile easier to use
            o_profile = {
                'pub_k' : o_profile.pub_k,
                'name' : o_profile.attrs.name === undefined ? '' : o_profile.attrs.name,
                'about' : o_profile.attrs.about === undefined ? '' : o_profile.attrs.about,
                'picture' : o_profile.attrs.picture === undefined ? '' : o_profile.attrs.picture,
                'profile_name': o_profile.profile_name === undefined ? '' : o_profile.profile_name,
                // only needs to be set when linking to existing profile we donbt have priv_k for
                'private_key' : '',
                'can_sign' : o_profile.can_sign
            };

            o_str = JSON.stringify(o_profile);
            e_profile = $.extend({}, o_profile);

        }

        function set_r_obj(){
            r_obj = {
                'pub_k' : e_profile.pub_k,
                'short_pub_k': mode==='create' ? 'to be generated' : APP.nostr.util.short_key( e_profile.pub_k),
                'profile_name' : e_profile.profile_name,
                'picture' : e_profile.picture,
                'name' : e_profile.name,
                'about' : e_profile.about,
                'disabled' : mode==='view' ? 'disabled' : ''
            };
        }

        function render_head(){
            // TODO: make some basic check that this str is actually something we can use as a picture
            pic_con.html(Mustache.render(APP.nostr.gui.templates.get('profile-list'), r_obj));
        }

        function draw(){
            let enable_media = APP.nostr.data.user.enable_media();
            edit_con.html(Mustache.render(input_tmpl, r_obj));
            render_head();

            // add events
            $(":input").on('keyup', function(e){
                let id = e.target.id,
                    val = e.target.value;

                if(id==='picture-url'){
                    if(APP.nostr.util.http_matches(e.target.value)!==null){
                        e_profile.picture = e.target.value;
                    }else{
                        e_profile.picture = o_profile.picture;
                    }
                }else if(id==='pname'){
                    e_profile.name = val;
                }else if(id==='about'){
                    e_profile.about = val;
                }else if(id==='private-key'){
                    // 64 len hex str
                    if(/[0-9A-Fa-f]{64}/g.test(val)){
                        e_profile['private_key'] = val;
                    }else{
                        e_profile['private_key'] = '';
                    }
                }else if(id==='profile-name'){
                    // anything but empty
                    if(val.replace(/\s/g,'') !==''){
                        e_profile['profile_name'] = val;
                    }else{
                        e_profile['profile_name'] = '';
                    }
                }

                set_r_obj();
                render_head();

                // save button only visible when something has changed,
                // we allow the publish button at any time
                // (e.g. user just wants to make sure thier profile is on all relays they're attached to
                // but they're not actually changing)

                if((o_str!==JSON.stringify(e_profile) && e_profile.can_sign===true) ||
                    (e_profile.profile_name!=='' && e_profile.private_key!=='') ||
                    (e_profile.profile_name!=='' && e_profile.pub_k==='') ){
                    save_but.show();
                }else{
                    save_but.hide();
                }
            });

            function link_done(data){
                if(data.success===true){
                    set_state(data.profile)
                    init_page();
                    APP.nostr.data.event.fire_event('local_profile_update',{});
                }
            }

            key_but.on('click', function(){
                if(mode==='view'){
                    APP.nostr.gui.request_private_key_modal.show({
                        'link_profile': o_profile,
                        'on_link' : link_done
                    });
                }else if(mode==='create'){
                    APP.nostr.gui.request_private_key_modal.show({
                        'on_link' : link_done
                    });
                }else if(mode==='edit'){
                    APP.remote.export_profile({
                        'for_profile' : o_profile.profile_name,
                        'success' : function(data){
                            if(data.error!==undefined){
                                APP.nostr.gui.notification({
                                    'text' : data.error,
                                    'type' : 'warning'
                                });
                            }else{
                                APP.nostr.gui.notification({
                                    'text' : '[' + o_profile.profile_name + '] successfully exported to '+ data.output
                                });
                            }
                        }
                    })
                }

            });

            function do_update(is_publish){
                let save = o_str!==JSON.stringify(e_profile);

                APP.remote.update_profile({
                    'profile' : e_profile,
                    'save' : save,
                    'mode' : mode,
                    'publish' : is_publish,
                    'success' : function(data){
                        let msg_txt = 'profile saved';
                        if(data.save===true || data.publish===true){
                            // a publish we'll always result in a save, though if nothing has chanegd it won't be direct
                            // it'll be from seeing the meta event update
                            if(data.publish===true){
                                msg_txt+=' and published';
                            }
                            APP.nostr.gui.notification({
                                'text' : msg_txt
                            });
                            APP.nostr.data.profiles.put(data.profile, true);
                            APP.nostr.data.event.fire_event('local_profile_update',{});
                            set_state(data.profile)
                            init_page();

                        }
                    }
                });
            }

            save_but.on('click', function(){
                do_update(false);
            });

            publish_but.on('click', function(){
                do_update(true);
            });

        }

        if(pub_k){
            APP.nostr.data.profiles.fetch({
                'pub_ks': [pub_k],
                'on_load' : function(){
                    init();
                }
            });
        }else{
            init();
        }
    }

    return {
        'create' : create
    }
}();

APP.nostr.gui.profile_list = function (){
        // lib shortcut
    let _gui = APP.nostr.gui;

    function create(args){
            // container for list
        let _con = args.con,
            // profiles passed into us
            _view_profiles = args.profiles || [],
            // inline media where we can, where false just the link is inserted
            _enable_media = APP.nostr.data.user.enable_media(),
            // data in arr to be rendered
            _render_arr,
            // above on pub_k
            _render_lookup,
            // only profiles that pass this filter will be showing
            _filter_text = args.filter || '',
            // so ids will be unique per this list
            _uid = APP.nostr.gui.uid(),
            // list obj that actually does the rendering
            _my_list,
            // template to render into
            _row_tmpl = APP.nostr.gui.templates.get('profile-list'),
            _current_profile = APP.nostr.data.user.profile();

        // methods
        function init(){
            // prep the intial render obj
            create_render_data();
            _my_list = APP.nostr.gui.list.create({
                'con' : _con,
                'data' : _render_arr,
                'row_tmpl': _row_tmpl,
                'filter' : test_filter,
                'click' : function(id){
                    let click_data = get_click_info(id),
                        action = click_data.action,
                        pub_k = click_data.pub_k;

                    if(action===undefined){
                        location.href = '/html/profile?pub_k='+pub_k;
                    }else if(action=='profile-edit'){
                        window.location='/html/edit_profile?pub_k='+pub_k;
                    }else if(action==='profile-switch'){
                        APP.nostr.data.user.profile({
                            'pub_k' : pub_k
                        });
                    }else if(action==='profile-dm'){
                        APP.nostr.gui.post_modal.show({
                            'kind' : 4,
                            'pub_k': pub_k
                        });
                    }else if(action==='profile-fol'){
                        APP.nostr.data.user.follow_toggle(pub_k, function(data){
                            // this is tmp but should be correct, it'll be overridden when we actually see
                            // the contacts event back from a relay
                            _current_profile = data.profile;
                            update_follow(pub_k);
                        });
                    }
                }
            });
            draw();

            // happens when we get the update back from relay or if user is doing something in another window
            APP.nostr.data.event.add_listener('contacts_updated', function(of_type, data){
                let updates = [];
                // won't do anything for our own update as we should already be in sync
                if(data.contacts.join(':')!==_current_profile.contacts.join(':')){

                    // any key not in BOTH arrs needs to be updated
                    updates = data.contacts.filter(function(pk){
                        return !_current_profile.contacts.includes(pk);
                    });
                    _current_profile.contacts.forEach(function(pk){
                        if(!data.contacts.includes(pk)){
                            updates.push(pk);
                        }
                    });

                    _current_profile = APP.nostr.data.user.profile();
                    // actually render the updates
                    updates.forEach(function(pk){
                        update_follow(pk);
                    });
                }
            });

        }

        function update_follow(pub_k){
            let el = $('#'+_uid+'-'+pub_k+'-profile-fol'),
                follow = _current_profile.contacts.includes(pub_k),
                html = follow===true ? '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star-fill"/>' :
                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star"/>';

            // replace what is currently displayed
            el.html(html);

            // replace if re-rendered
            if(_render_lookup[pub_k]!==undefined){
                _render_lookup[pub_k].follows = _current_profile.contacts.includes(pub_k);
            }
        }

        function get_click_info(id){
                id = id.replace(_uid+'-','');
            let ret,
                pubk_eidx = id.indexOf('-');
            if(pubk_eidx>=0){
                ret = {
                    'pub_k' : id.substring(0,pubk_eidx),
                    'action' : id.substring(pubk_eidx+1)
                }
            }else{
                ret = {
                    'pub_k' : id
                };
            }

            return ret;
        }

        function draw(){
            _my_list.draw();
        };

        /*
            fills data that'll be used with template to render
        */
        function create_render_data(){
            _render_arr = [];
            _render_lookup = {};

            let r_obj;
            _view_profiles.forEach(function(p){
                r_obj = _create_render_profile(p);
                _render_lookup[p.pub_k] = r_obj;
                _render_arr.push(r_obj);
            });
        }

        // create profile render obj to be put in _renderObj['profiles']
        function _create_render_profile(the_profile){
            let pub_k = the_profile.pub_k,
                render_profile = {
                    // required to make unique ids if page has more than one list showing same items on page
                    'uid' : _uid,
                    'pub_k' : pub_k,
                    'short_pub_k' : APP.nostr.util.short_key(pub_k),
                    'profile_name': the_profile.profile_name
                },
                attrs;

            if(the_profile.attrs){
                attrs = the_profile['attrs'];
                render_profile['picture'] =attrs.picture;
                render_profile['name'] = attrs.name;
                render_profile['about'] = attrs.about;
                // be better to do this in our data class
                if(render_profile.about!==undefined && render_profile.about!==null){
//                    render_profile.about = APP.nostr.util.html_escape(render_profile.about);
                    render_profile.about = _gui.http_media_tags_into_text(render_profile.about, false).text;
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

            if(_current_profile.pub_k!==undefined){
                render_profile.can_edit = the_profile.can_sign;
                render_profile.follows = _current_profile.contacts.includes(pub_k);
                if(_current_profile.pub_k!==the_profile.pub_k){
                    render_profile.other_profile = true;
                    render_profile.can_dm = true;
                    render_profile.can_switch = the_profile.can_sign;
                }

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

        // prep and draw the list
        init();

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
   list component for messages page. On the messages page you only get the topmost event for each
   pub_k that we have messages to. We'll show the profile who we're messaging as well as the last message and
   who it was from either us or them. Clicking will take us to messages for that profile, further clicking to
   individual threads with that pub_k
*/
APP.nostr.gui.dm_list = function (){
        // lib shortcut
    let _gui = APP.nostr.gui,
        _gui_util = _gui.util,
        _profiles = APP.nostr.data.profiles,
        _nostr_event = APP.nostr.data.nostr_event;


    function create(args){
            // container for list
        let _con = args.con,
            // top level events for each pub_k we're talling to
            _events = args.events || [],
            // inline media where we can, where false just the link is inserted
            _enable_media = APP.nostr.data.user.enable_media(),
            // so ids will be unique per this list
            _uid = APP.nostr.gui.uid(),
            // data in arr to be rendered
            _render_arr,
            // above on pub_k
            _render_lookup,
            // list obj that actually does the rendering
            _my_list,
            // template to render into
            _row_tmpl = APP.nostr.gui.templates.get('dm-event'),
            _profile_tmpl = APP.nostr.gui.templates.get('event-profile'),
            _content_tmpl = APP.nostr.gui.templates.get('dm-content'),
            _current_profile = APP.nostr.data.user.profile(),
            _time_update;

        // methods
        function init(){
            // prep the intial render obj
            create_render_data();
            _my_list = APP.nostr.gui.list.create({
                'con' : _con,
                'data' : _render_arr,
                'row_render': row_render,
                'click' : do_click
            });
            set_events(_events);
            draw();
            // update the since every 30s
            _time_update = setInterval(time_update, 1000*30);

            // listen to new events, maybe add them/update display
            APP.nostr.data.event.add_listener('event', function(type, event){
                event = _nostr_event(event);
                if(is_our_dm(event)){
                    update(event);
                }
            });

        }

        function is_our_dm(evt){
            let to,
                ret = false;
            if(evt.is_encrypt()){
                to = evt.get_first_p_tag_value(function(val){
                    return val===_current_profile.pub_k;
                });

                ret = to.length>0 || evt.pubkey===_current_profile.pub_k;

            }
            return ret;
        }

        function update(evt){
            let c_evt,
                to_k = get_to_pub_k(evt),
                e_to_k;
            // if already event to this contact then remove
            for(let i=0;i<_events.length;i++){
                c_evt = _events[i];
                if(get_to_pub_k(c_evt)===to_k){
                    _events.splice(i,1);
                    _render_arr.splice(i,1);
                    delete _render_lookup[c_evt.id];
                    break;
                }
            }
            // insert at top and redraw
            _events.splice(0,0, evt);
            _render_arr.splice(0,0, _create_render_row(evt));
            _render_lookup[evt.id] = evt;
            draw();
        }

        function do_click(id){
            id = id.replace(_uid+"-","");
            let splits = id.split('-'),
                evt_id = splits[0],
                action = splits[1],
                evt = _render_lookup[evt_id],
                to_pub_k = get_to_pub_k(evt)

            // goto the person we're msgings profile
            if(action==='pp' || action==='pt'){
                window.location='/html/profile?pub_k='+to_pub_k;
            // goto profile of whoever msged last, either us or same as above
            }else if(action==='lastpp'){
                window.location='/html/profile?pub_k='+evt.pubkey;
            // all other cases go to message page for this profile
            }else{
                window.location='/html/messages_profile?pub_k='+to_pub_k;
            }

        }

        function row_render(r_obj, i){
            return Mustache.render(_row_tmpl, r_obj, {
                'profile' : _profile_tmpl,
                'content' : _content_tmpl
            })
        }

        function set_events(events){
            _events = events;
            fetch_profiles(function(){
                create_render_data();
                _my_list.set_data(_render_arr);
                draw();
            });

        }

        // this will make sure any profiles we need have been fetch if we can find them
        function fetch_profiles(callback){
            let to_ps = [];
            _events.forEach(function(c_evt){
                to_ps.push(get_to_pub_k(c_evt));
            });
            // should have us but just incase
            to_ps.push(_current_profile.pub_k);

            _profiles.fetch({
                'pub_ks' : to_ps,
                'on_load' : function(){
                    callback();
                }
            })
        }

        function draw(){
            _my_list.draw();
        }

        function get_to_pub_k(evt){
            // the to pub_k is the one thats not us, that might be on the evt or else we'll have to look at the p tags
            let ret = null,
                tags = evt.tags,
                c_tag;

            // the most recent event was to use
            if(evt.pubkey!==_current_profile.pub_k){
                ret = evt.pubkey;
            // most recent event was sent buy us
            }else{
                console.log(evt);
                tags = evt.get_first_p_tag_value(function(val){
                    return val!==_current_profile.pub_k;
                });
                if(tags.length>0){
                    ret = tags[0];
                }
            }

            // if we return null...probably drop the event cause don't know what we can do with it?!
            return ret;
        }

        /*
            fills data that'll be used with template to render
        */
        function create_render_data(){
            _render_arr = [];
            _render_lookup = {};
            _events.forEach(function(c_evt){
                _render_arr.push(_create_render_row(c_evt));
                _render_lookup[c_evt.id] = c_evt;
            });
        }

        // create profile render obj to be put in _renderObj['profiles']
        function _create_render_row(evt){
            let ret = {
                    'uid' : _uid,
                    'event_id' : evt.id,
                    'pub_k' : get_to_pub_k(evt),
                    'content' : _gui.get_note_content_for_render(evt).content,
                    'at_time' : dayjs.unix(evt.created_at).fromNow()
                },
                to_p = _profiles.lookup(ret.pub_k);

            ret.picture = _gui_util.profile_picture_url(ret.pub_k);
            ret.short_key = APP.nostr.util.short_key(ret.pub_k);
            ret.sender_picture = _gui_util.profile_picture_url(evt.pubkey);
            if(to_p!==null){
                ret.name = to_p.attrs.name;
            }

            return ret;
        }

        function uevent_id(event_id){
            return _uid+'-'+event_id;
        }

        function time_update(){
            // think we've been killed ..?
            if(_events===undefined){
                clearInterval(_time_interval);
                return;
            }

            _events.forEach(function(evt){
                let id = uevent_id(evt.id),
                    ntime = dayjs.unix(evt.created_at).fromNow();

                // update in render obj, at the moment it never gets reused anyhow
//                c['at_time'] = ntime;
                // actually update onscreen
                $('#'+id+'-time').html(ntime);

            });
        }


        // prep and draw the list
        init();

        return {
            'draw': draw,
            'set_events' : set_events
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
                            '<span style="display:none" id="nostr-modal-footer"></span>',
                            '<button id="nostr-modal-ok-button" type="button" class="btn btn-default" data-dismiss="modal">Close</button>',
                        '</div>',
                    '</div>',
                '</div>',
            '</div>'
        ].join(''),
        _my_modal,
        _my_title,
        _my_content,
        _my_ok_button,
        _my_foot_con,
        _title,
        _content,
        _ok_text,
        _on_ok,
        _ok_hide,
        _on_show,
        _on_hide,
        // if set doing own bottom buttons
        _footer_content,
        _was_ok;

    function create(args){
        args = args||{};
        _title = args.title || '?no title?',
        _content = args.content || '',
        _ok_text = args.ok_text || '?no_text?',
        _on_ok = args.on_ok,
        _ok_hide = args.ok_hide===undefined ? false : args.ok_hide,
        _on_show = args.on_show,
        _on_hide = args.on_hide,
        // if set doing own bottom buttons
        _footer_content = args.footer_content,
        _was_ok = false;

        // make sure we only ever create one
        if(_my_modal===undefined){
            $(document.body).prepend(_modal_html);
            _my_modal = $('#nostr-modal');
            _my_title = $('#nostr-modal-title');
            _my_content = $('#nostr-modal-content');
            _my_ok_button = $('#nostr-modal-ok-button');
            _my_foot_con = $('#nostr-modal-footer');

            // escape to hide
            $(document).on('keydown', function(e){
                if(e.key==='Escape' && _my_modal.hasClass('in')){
                    hide();
                }
            });

            _my_modal.on('shown.bs.modal', function () {
                if(typeof(_on_show)==='function'){
                    _on_show();
                }
            });

            _my_modal.on('hidden.bs.modal', function () {
                if(typeof(_on_hide)==='function'){
                    _on_hide();
                }
            });

            _my_ok_button.on('click', function(){
                _was_ok = true;
                if(typeof(_on_ok)==='function'){
                    _on_ok();
                }
            });

        }
        _my_title.html(_title);
        _my_content.html(_content);
        _my_ok_button.html(_ok_text);
        if(_footer_content!==undefined){
            _my_foot_con.html(_footer_content);
            _my_foot_con.css('display','');
            hide_ok();
        }else{
            _my_foot_con.css('display','none');
            show_ok();
        }

        if(_ok_hide){
            hide_ok();
        }

    }

    function show(){
        // create must have been called before calling show
        _my_modal.modal();
    }

    function hide(){
        _my_modal.modal('hide');
    }

    function set_content(content){
        _my_content.html(content);
    }

    function show_ok(){
        _my_ok_button.css('display','');
    }

    function hide_ok(){
        _my_ok_button.css('display','none');
    }

    return {
        'create' : create,
        'show' : show,
        'hide' : hide,
        'set_content' : set_content,
        'get_container' : function(){
            return _my_content;
        },
        'show_ok' : show_ok,
        'hide_ok' : hide_ok,
        'was_ok' : function(){
            return _was_ok;
        }

//        'is_showing' : function(){
//            return _my_modal!==undefined && _my_modal.hasClass('in');
//        }
    };
}();

APP.nostr.gui.post_modal = function(){

    // TODO as https://github.com/nostr-protocol/nips/blob/master/10.md
    // add reply and root markers, we need a preferred relay first though
    // as it's not optional
    function add_reply_tags(o_event){
        let ret = [],
            to_pub_key = o_event.pubkey,
            to_evt_id = o_event.id,
            t_name,
            t_val,
            to_add;


        function good_value(t_val){
            return t_val!==undefined && t_val!==null && t_val!=='';
        }
        function our_add(t_name, t_val){
            return (t_name==='p' && t_val===to_pub_key) ||
                (t_name==='e' && t_val===to_evt_id);
        }

        // copy all tags, don't thinnk it matters much but also check that
        // we're not going to dupl the p or e tags that we are going to add
        o_event.tags.forEach(function(c_tag,i){
            // tags from the original event that are kept
            const keep = new Set(['p','e','subject']);
            t_name = c_tag[0];
            t_val = c_tag[1];
            // its a tag we keep on replies
            if(keep.has(t_name) && good_value(t_val) && !our_add(t_name, t_val)){
                to_add = [t_name,t_val];
                if(t_name==='e' && c_tag[3]==='reply'){
                    to_add.push('');
                    to_add.push('root');
                }
                ret.push(to_add);
            };
        });

        // tags we're specifically adding
        ret.push(['p', to_pub_key]);
        ret.push(['e', to_evt_id, '', 'reply']);

        return ret;
    }

    function show(args){
        args =args || {};
        var gui = APP.nostr.gui,
            user = APP.nostr.data.user,
            profiles,
            type = args.type!==undefined ? args.type : 'post',
            // in case of reply this is ignored and the kind is taken from the event we're replying to
            kind = args.kind || 1,
            // same as kind
            pub_k = args.pub_k,
            event = args.event !==undefined ? args.event : {
                'id' : '?',
                'content' : 'something has gone wrong!!',
                'tags' :[]
            },
            render_obj= {},
            enable_media = APP.nostr.data.user.enable_media(),
            uid = gui.uid(),
            picture,
            title,
            name,
            note_text_area;

            function get_reply_title(){
                let ret;
                if(event.kind===1){
                    ret = 'reply to event';
                }else if(event.kind===4){
                    ret = 'reply to encrypted event';
                }
                return ret + ' <span class="pubkey-text" >'+APP.nostr.util.short_key(event.id)+'<span/>';
            }

            function get_post_title(){
                let ret;
                if(kind===1){
                    ret = 'make post';
                }else if(kind===4){
                    ret = 'make encrypted post';
                }
                return ret;
            }

            function get_title(){
                let ret;
                if(kind===1){
                    ret = get_post_title();
                }else if(kind===4){
                    ret = get_reply_title();
                }
                return ret;
            }

            function add_post_tags(){
                let ret = [];
                if(pub_k){
                    ret.push(['p',pub_k])
                }
                return ret;
            }

            function add_profile_render(r_obj, pub_k){
                let p = APP.nostr.data.profiles.lookup(pub_k);
                if(p!==null){
                    picture = p.picture;
                    name = p.attrs.name;
                }else{
                    name = '';
                    picture = APP.nostr.gui.robo_images.get_url({
                        'text' : pub_k
                    });
                }
                r_obj['short_key'] = APP.nostr.util.short_key(pub_k);
                r_obj['name'] = name;
                r_obj['picture'] = picture;
            }

            function create(){
                APP.nostr.gui.modal.create({
                    'title' : title,
                    'content' : Mustache.render(gui.templates.get('modal-note-post'),render_obj, {
                        'event' : gui.templates.get('event'),
                        'profile' : gui.templates.get('event-profile'),
                        'content' : gui.templates.get('event-content'),
                    }),
                    'ok_text' : 'send',
                    'on_ok' : function do_post(){
                        let n_tags = type==='reply' ? add_reply_tags(event) : add_post_tags(),
                            content = note_text_area.val(),
                            hash_tags = (content).match(/(^|\s)\#\w*[\S|$]/g),
                            evt = {
                                'pub_k' : user.profile().pub_k,
                                'content': content,
                                'tags' : n_tags,
                                'kind' : type==='reply' ? event.kind : kind
                            };
                        // add hashtags
                        if(hash_tags!==null){
                            // fixes the matches we got... theres probably a better group based way to do this
                            // but this is simple
                            hash_tags.forEach(function(c_tag){
                                n_tags.push(['hashtag',c_tag.substring(c_tag.indexOf('#')+1)]);
                            });
                        }

                        if(user.is_add_client_tag()===true){
                            n_tags.push(['client', user.get_client()]);
                        }

                        APP.remote.post_event({
                            'event' : evt,
                            'pub_k' : user.profile().pub_k,
                            'success' : function(data){
                                // notify anyone interested
                                APP.nostr.data.event.fire_event('post-success', {
                                    'event': evt,
                                    'type': type
                                });
                            }
                        });
                    },
                    'on_show' : function(){
                        note_text_area.focus();
                    }
                });
            }

            if(type==='post'){
                title = get_post_title();
                if(pub_k!==undefined){
                    // hacky but required to get render at mo
                    render_obj['event'] = jQuery.extend({}, event);
                    add_profile_render(render_obj, pub_k);
                }
            } else if(type==='reply'){
                title = get_reply_title();
                // because we're going to give another id just so we don't get mutiple els with same id in dom
                render_obj['event'] = jQuery.extend({}, event);
                render_obj['event'].uid = uid;
                add_profile_render(render_obj, event.pubkey);
                render_obj['content'] = gui.get_note_content_for_render(event).content;
            }



        // nothing is clickable!
        if(type==='reply'){
            $('#'+uid+'-'+render_obj.event.event_id+'-pp').css('cursor','default');
            $('#'+uid+'-'+render_obj.event.event_id-'content').css('cursor','default !important');
        }
        create();
        note_text_area = $('#nostr-post-text');
        APP.nostr.gui.modal.show();

    }

    return {
        'show': show
    }
}();

APP.nostr.gui.profile_select_modal = function(){
    let _uid = APP.nostr.gui.uid(),
        // short cut ot profiles helper
        _profiles_lookup,
        _user_profiles,
        _list,
        _list_data = [],
        _row_tmpl,
        _current_profile,
        _selected_profile;

    function draw_profiles(profiles){
        _user_profiles = profiles;
        _profiles_lookup = {};
        // just incase it didn't get inted yet

        _row_tmpl = APP.nostr.gui.templates.get('profile-list');
        _selected_profile = _current_profile = APP.nostr.data.user.profile();
        APP.nostr.gui.modal.set_content('<div id="'+_uid+'"></div>');

        create_list_data();
        create_list();
        _list.draw();
    }

    function create_list_data(){
        _list_data = [{
            // the no profile profile.. just browse
            'uid' : _uid,
            'profile_name' : 'lurker',
            'detail-selected' : _selected_profile.pub_k===undefined ? 'profile-detail-area-selected' : '',
            'picture-selected' : _selected_profile.pub_k===undefined ? 'profile-picture-area-selected' : '',
            'about' : 'browse without using a profile'
        }];

        _user_profiles.forEach(function(c_p,i){
            _profiles_lookup[c_p.pub_k] = c_p;

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
                'detail-selected' : _selected_profile.pub_k===c_p.pub_k ? 'profile-detail-area-selected' : '',
                'picture-selected' : _selected_profile.pub_k===c_p.pub_k ? 'profile-picture-area-selected' : '',
                'profile_name' : c_p.profile_name,
                'name' : c_p.attrs.name,
                'picture' : img_src,
                'can_edit' : true,
                'can_view' : true
            };

            to_add.profile_name = c_p.profile_name;
            _list_data.push(to_add);
        });
    };

    function create_list(){
        _list = APP.nostr.gui.list.create({
            'con' : $('#'+_uid),
            'data' : _list_data,
            'row_tmpl': _row_tmpl,
            'click' : function(id){
                id = id.replace(_uid+'-', '');
                let parts = id.split('-'),
                    pub_k = parts[0],
                    p = _profiles_lookup[pub_k],
                    cmd = '';

                // get cmd if any
                if(parts.length>1){
                    cmd = parts.slice(1).join('-');
                }

                // just selected profile
                if(cmd===''){
                    if(p===undefined){
                        p = {};
                    }

                    _selected_profile = p;
                    create_list_data();
                    _list.set_data(_list_data);
                    _list.draw();


                // go to edit page for this profile
                }else if(cmd==='profile-edit'){
                    window.location='/html/edit_profile?pub_k='+pub_k;
                }else if(cmd==='profile-view'){
                    window.location='/html/profile?pub_k='+pub_k;
                }

            }
        });
    }

    function show(){
        let footer_html = [
            '<button id="nostr-profile_select-new-button" type="button" class="btn btn-default" >new</button>',
            '<button id="nostr-profile_select-ok-button" type="button" class="btn btn-default" data-dismiss="modal">ok</button>'
        ].join('');

        // set the modal as we want it
        APP.nostr.gui.modal.create({
            'title' : 'choose profile',
            'content' : 'loading...',
            'footer_content' : footer_html
        });

        $('#nostr-profile_select-new-button').on('click', function(){
            window.location = '/html/edit_profile';
        });

        $('#nostr-profile_select-ok-button').on('click', function(){
            if(_current_profile.pub_k!==_selected_profile){
                APP.nostr.data.user.profile(_selected_profile);
//                window.location = '/';
            }
            APP.nostr.gui.modal.hide();
        });

        // show it
        APP.nostr.gui.modal.show();

        APP.remote.local_profiles({
            'success' : function(data){
                draw_profiles(data.profiles);
            }
        });
    }

    return {
        'show' : show
    }
}();

APP.nostr.gui.relay_list = function(){
    const _gui = APP.nostr.gui;

    function create(args){
        let con = args.con,
            uid = APP.nostr.gui.uid(),
            o_relay_status = APP.nostr.data.relay_status.get(),
            c_relay_status = o_relay_status,
            my_list,
            summary_con,
            list_con,
            is_edit = args.edit===undefined ? false : args.edit,
            list_tmpl = _gui.templates.get('relay-list'),
            row_tmpl = _gui.templates.get('modal-relay-list-row'),
            list_con_status_tmpl = _gui.templates.get('relay_list-status'),
            sum_con_status_tmpl = _gui.templates.get('relay-con-status'),
            relay_map = {};

        function get_last_connect_str(r_status){
            let ret = 'never ';

            if(r_status.last_connect !== null){
                ret = dayjs.unix(r_status.last_connect).fromNow();
                if(ret==='now'){
                    ret = 'recently';
                }else{
                    ret += ' ago';
                }

            }
            return ret;
        }

        function summary_data(){
            return {
                'uid' : uid,
                'status' : c_relay_status.connected===true ? 'connected' : 'not-connected',
                'relay-count': c_relay_status.relay_count,
                'connect-count' : c_relay_status.connect_count,
            }
        }

        function list_data(){
            let r_status,
                ret = [],
                relay_uid,
                relay_data;


            for(let relay in c_relay_status.relays){
                r_status = c_relay_status.relays[relay];
                relay_uid = relay_map[relay]===undefined ? _gui.uid() : relay_map[relay].uid;

                relay_data = {
                    'url' : relay,
                    'connected' : r_status.connected,
                    'last_err' : r_status.last_err,
                    'last_connect' : get_last_connect_str(r_status),
                    'mode_text' : get_mode_text(r_status),
                    'is_mode_edit' : is_edit,
                    'relay_uid' : relay_uid
                };
                ret.push(relay_data);

                relay_map[relay] = {
                    'data' : relay_data,
                    'uid' : relay_uid
                };

            }
            return ret;
        }

        function add_relay(url){
            let data = my_list.data();
            data.unshift({
                'url' : url,
                'last_err' : '',
                'is_edit_mode' : is_edit
            });
            my_list.data(data);
            my_list.draw();
        }
        function remove_relay(url){
            let data= my_list.data();
            for(let i=0;i<data.length;i++){
                if(data[i].url===url){
                    data.splice(i,1);
                    break;
                }
            }
            my_list.data(data);
            my_list.draw();
        }

        function init_draw(){
            // also creates the list area
            con.html(Mustache.render(list_tmpl,summary_data(),
                {
                    'status' : list_con_status_tmpl
                }
            ));
            summary_con = $('#'+uid+'-header');
            list_con = $('#'+uid+"-list");
            my_list = _gui.list.create({
                'con' : list_con,
                'data' : list_data(),
                'row_render' : function(r){
                    return Mustache.render(row_tmpl,r,
                        {
                            'con-status' :  sum_con_status_tmpl
                        });
                },
                'click': function(id){
                    let parts = id.replace(uid+'-','').split('-'),
                        relay_uid,
                        action,
                        relay;
                    if(parts.length===3){
                        relay_uid = parts[0]+'-'+parts[1];
                        action = parts[2];
                        relay = get_relay_with_uid(relay_uid);
                        alert(action);
                        if(action==='remove'){
                            alert('do delete '+ relay.data.url);
                        }

                    }
                }
            });
            my_list.draw();
        }

        // why have we only mapped on url?
        function get_relay_with_uid(uid){
            let relay;
            for(let k in relay_map){
                relay = relay_map[k];
                if(relay.uid===uid){
                    return relay;
                }
            }
            // not found?!?
            return null;
        }

        function get_mode_text(r_status){
            let ret = '?';
            if((r_status.read===true) && (r_status.write===true)){
                ret = 'read/write';
            }else if(r_status.write===true){
                ret = 'write only';
            }else if(r_status.read===true)
                ret = 'read only';
            return ret;
        }

        function set_summary(){
            summary_con.html(
                Mustache.render(list_con_status_tmpl,summary_data())
            );
        }

        function draw(){
            set_summary();
            // we need to be able to partial update if editing so we'll live it for now TODO: FIXME
            let data = list_data();
            data.forEach(function(c_relay){
               $('#'+c_relay.relay_uid+"-con-status").html(Mustache.render(sum_con_status_tmpl, c_relay));
            });
        }

        function my_listener(of_type, data){
            c_relay_status = data;
            draw();
        }

        function init(){
            APP.nostr.data.event.add_listener('relay_status', my_listener);
            init_draw();
        }

        init();

        return {
            'stop' : function(){
                APP.nostr.data.event.remove_listener('relay_status', my_listener);
            }
        }

    }

    return {
        'create' : create
    };
}();

// make generic select?
APP.nostr.gui.relay_select = function(){

    const my_html = [
        '<div style="height:100%">',
            '<label for="relays-search">relays</label>',
            '<div style="display:table-row" >',
                '<div style="display:table-cell;">',
                    '<input style="min-width:280px;" type="text" class="form-control" id="relays-search" aria-describedby="available relays" placeholder="search relays" list="relay-options" />',
                '</div>',
                '<div style="display:table-cell;vertical-align:top;" >',
                    '<button type="button" class="btn btn-primary">+</button>',
                '</div>',
            '</div>',
            '<datalist id="relay-options">',
            '</datalist>',
        '</div>'
    ].join('');

    function create(args){
        let con = args.con,
            search_in,
            my_list,
            list_con,
            current_user = APP.nostr.data.user.profile();

        function draw(){
            con.html(my_html);
            search_in = $('#relays-search');
            list_con = $('#relay-options');
            search_in.focus();
        }

        function load_relays(){
            APP.remote.relay_list({
                'success' : function(data){
                    list_con.html('loaded!');
                    my_list = APP.nostr.gui.list.create({
                        'con': list_con,
                        'data' : data.relays,
                        'row_render' : function(r){
                            return '<option value="'+r+'" >';
                        }
                    });

                    my_list.draw();
                }
            });
        }

        draw();
        load_relays();
    }

    return {
        'create' : create
    };
}();

APP.nostr.gui.relay_edit = function(){
    const _gui = APP.nostr.gui;

    function create(args){
        let con = args.con,
            relay_con,
            select_con;


        function init(){
            con.html(APP.nostr.gui.templates.get('screen-relay-edit-struct'));
            relay_con = $('#current-con');
            select_con = $('#edit-con');

            _gui.relay_select.create({
                'con' : select_con
            });

            _gui.relay_list.create({
                'con' : relay_con,
                'edit' : true
            });


        }

        init();

    }

    return {
        'create' : create
    };
}();


APP.nostr.gui.relay_view_modal = function(){
    const _gui = APP.nostr.gui;

    function show(){
        let footer_html = [
            '<button id="relay-view-edit-button" type="button" class="btn btn-default" >edit</button>',
            '<button id="relay_view-ok-button" type="button" class="btn btn-default" data-dismiss="modal">ok</button>'
        ].join(''),
        relay_list;

        // set the modal as we want it
        _gui.modal.create({
            'title' : 'current relays',
            'content' : 'loading...',
            'footer_content' : footer_html,
            'on_hide' : function(){
                relay_list.stop();
            },
            'click' : function(id){
                alert(id);
            }

        });
        // show it
        $('#relay-view-edit-button').on('click', function(){
            window.location = '/html/edit_relays';
        });

        relay_list = _gui.relay_list.create({
            'con': _gui.modal.get_container()
        });
        _gui.modal.show();

    }

    return {
        'show' : show
    }
}();

APP.nostr.gui.request_private_key_modal = function(){
    /* modal to link a private key either to a given prexisiting pub_k (it'll only allow matches to that)
        or any priv_k where it'll look up the profile and the user can ok if they want to link
    */
    let _uid = APP.nostr.gui.uid(),
        _gui = APP.nostr.gui;

    function show(args){
        const content = [
        '{{> profile}}',
        '<div class="form-group">',
            '<label for="private-key">private key</label>',
            '<input type="password" autocomplete="off" class="form-control" id="private-key" aria-describedby="private key" placeholder="enter private key" value="" >',
            '<div id="pk_modal_error_con"></div>',
        '</div>'
        ].join('');


        let link_profile = args.link_profile || {},
            user_link_profile = null,
            on_link = args.on_link;

        let priv_in,
            last_val,
            error_con,
            uid = APP.nostr.gui.uid(),
            link_given_profile =function(priv_k, pub_k){
                APP.remote.link_profile({
                    'priv_k' : priv_k,
                    'pub_k' : pub_k,
                    'success' : function(data){
                        if(data.error!==undefined){
                            error_con.html(data.error);
                        }else{
                            APP.nostr.gui.modal.hide();
                            APP.nostr.gui.notification({
                                'text' : APP.nostr.util.short_key(pub_k)+' linked successfully!!!'
                            });
                            if(typeof(on_link)==='function'){
                                on_link(data);
                            }
                        }
                    }
                });
            },
            link_priv_key_profile = function(key){
                APP.remote.load_profile({
                    'priv_k' : key,
                    'success' : function(data){
                        if(data.error!==undefined){
                            user_link_profile = null;
                            error_con.html(data.error);
                            APP.nostr.gui.modal.hide_ok();
                        }else{
                            error_con.html('');
                            user_link_profile = data;
                            data.picture = data.attrs.picture;
                            data.name = data.attrs.name;
                            data.about = data.attrs.about;
                            data.priv_k = key;
                            $('#'+uid+'-'+'pk-modal-profile').html(Mustache.render(APP.nostr.gui.templates.get('profile-list'),data));
                            APP.nostr.gui.modal.show_ok();
                        }
                    }
                })
            };

        // set the modal as we want it
        let render_obj = $.extend({
                'uid' : uid,
            },link_profile);
        if(render_obj.pub_k===undefined){
            render_obj.pub_k = 'pk-modal-profile'
        }

        APP.nostr.gui.modal.create({
            'title' : 'enter private key to link',
            'content' : Mustache.render(content,render_obj,{
                'profile' : APP.nostr.gui.templates.get('profile-list')
            }),
            'on_hide' : function(){
                if(user_link_profile!==null && APP.nostr.gui.modal.was_ok()){
                    link_given_profile(user_link_profile.priv_k, user_link_profile.pub_k);
                }
            },
            'ok_hide': true,
            'ok_text' : 'ok'
        });


        // show it
        APP.nostr.gui.modal.show();

        // grab el
        priv_in = $('#private-key');
        error_con = $('#pk_modal_error_con');

        priv_in.on('keyup', function(e){
            let val = e.target.value,
                p;

            if(val!==last_val){
                if(/[0-9A-Fa-f]{64}/g.test(val)){
                    if(link_profile.pub_k!==undefined){
                        link_given_profile(val, link_profile.pub_k)
                    }else{
                        // no particular profile to link to, will look up the priv_k and show the user what
                        // we get for them to ok on
                        link_priv_key_profile(val)
                    }
                }else{
                    if(link_profile.pub_k===undefined){
                        user_link_profile = null;
                        APP.nostr.gui.modal.hide_ok();
                    }
                }
            }


            last_val = val
        });

    }



    return {
        'show' : show
    }
}();



/*
    using https://robohash.org/ so we can provide unique profile pictures
    now moved to a local route using code from robohash 1.1
    https://pypi.org/project/robohash/ which is the source for the website
*/
APP.nostr.gui.robo_images = function(){
//    let _root_url = 'https://robohash.org/';
    let _root_url = '/robo_images';
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