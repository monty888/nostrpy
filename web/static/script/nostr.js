// TODO: nostr stuff will be moved out to be share
APP.nostr = {
    'data' : {},
    'gui' : function(){
        let _id=0,
            // templates for rendering different media
            // external_link
            _link_tmpl = '<a href="{{url}}">{{url}}</a>',
            // image types e.g. jpg, png
            _img_tmpl = '<img src="{{url}}" width=100% height=auto style="display:block;border-radius:10px;" />',
            // video
            _video_tmpl = '<video width=100% height=auto style="display:block" controls>' +
            '<source src="{{url}}" >' +
            'Your browser does not support the video tag.' +
            '</video>',
            _notifications_con;

        return {
            'enable_media' : true,
            // a unique id in this page
            'uid' : function(){
                _id++;
                return 'guid-'+_id;
            },
            // from clicked el traverses upwards to first el with id if any
            // null if we reach the body el before finding an id
            'get_clicked_id' : function(e, accept_map){
                let ret = null,
                    el = e.target;

                while((el.id===undefined || el.id==='' || (accept_map && accept_map[el.id]===undefined)) && el!==document.body){
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
                let ret = text,
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
            },
            'notification' : function(args){
                /*
                    displays a messge at top of the screen that will clear after a few seconds
                */
                let _text = args.text;
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
                    },1000);
                }
                // first notification
                if(_notifications_con===undefined){
                    $(document.body).prepend(APP.nostr.gui.templates.get('notification-container'));
                    _notifications_con = $('#notifications');
                }

                do_notification();
            }

        };
    }(),
    'util' : {
        'short_key': function (key){
            return key.substring(0, 3) + '...' + key.substring(key.length-4)
        },
        'html_escape': function (in_str, ignore){
            let _replacements = [
                ['&','&amp'],
                ['<','&lt;'],
                ['>','&gt;'],
                ['"','&quot;'],
                ["'",'&#39;']
            ];
            _replacements.forEach(function(c_rep,i){
                let val = c_rep[0],
                    rep = c_rep[1];
                if(ignore===undefined || ignore[val]===undefined){
                    in_str = in_str.replace(val, rep);
                }
            });
            return in_str;
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
        },
        'copy_clipboard' : function copy_clipboard(value, success_text, fail_text){
            if(navigator.clipboard===undefined){
                // do some shit here to try and get access,
                // think that it won't be possible unless https
                navigator.permissions.query({name:'clipboard-write'}).then(function(r){
                    console.log(r)
                });

            }else{
                navigator.clipboard.writeText(value);
                if(success_text!==undefined){
                    APP.nostr.gui.notification({
                        'text' : success_text
                    });
                }

            }
        }


    }
};

/*
    given a string of text (events content) and tags
    will return the string with #[n]... replaced with tag links
    for #p and #e events
    maybe just hand event in?
*/
APP.nostr.gui.tag_replacement = function (text, tags){
    // cache of tag replacement regexs
    let _preregex = {},
        // profile helper for p lookups
        _profiles,
        //
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
                    if(_profiles.is_loaded()){
                        profile = _profiles.lookup(id);
                        if(profile!==undefined && profile.attrs.name!==undefined){
                            ret = profile.attrs.name;
                        }
                    }
                    return ret;
                }
            }
        };

    // can't be assigned until doc loaded
    $(document).ready(function(){
        _profiles = APP.nostr.data.profiles;
    });

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

            if((_replacements[tag_type]!==undefined) && (tag_val!==undefined)){
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
                    replace_text = replacer.text(tag_val);
                }

                // finally do the replacement
                text = text.replace(regex,'<a href="'+replacer.url(tag_val)+'" style="color:cyan;cursor:pointer;text-decoration: none;">' + replacer.prefix + replace_text +'</a>');
            }
        });
    return text;
    }
}();

// for relative times of notes from now
dayjs.extend(window.dayjs_plugin_relativeTime);
// so we can shorten the time formats
dayjs.extend(window.dayjs_plugin_updateLocale);

dayjs.updateLocale('en', {
  relativeTime: {
    // relative time format strings, keep %s %d as the same
    future: 'in %s', // e.g. in 2 hours, %s been replaced with 2hours
    past: '%s',
    s: 'now',
    m: '1m',
    mm: '%dm',
    h: '1h',
    hh: '%dh', // e.g. 2 hours, %d been replaced with 2
    d: '1d',
    dd: '%dd',
    M: '1mth',
    MM: '%dmth',
    y: '1y',
    yy: '%dy'
  }
});


APP.nostr.gui.tabs = function(){
    /*
        creates a tabbed area, probably only used to set up the, and events for moving between tabs
        but otherwise caller can deal with rendering the content
    */
    let _head_tmpl = [
        '<ul class="nav nav-tabs" style="overflow:hidden;" >',
            '{{#tabs}}',
                '<li class="{{active}}"><a data-toggle="tab" href="#{{tab-ref}}">{{tab-title}}</a></li>',
            '{{/tabs}}',
            // extra area for e.g. search field,
            '<span id="{{id}}-tool-con" class="tab-tool-area" >',
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
            'get_tab' : get_tab,
            'get_tool_con' : function(){
                return _tool_con;
            },
            'get_selected_tab' : function(){
                return get_tab(_cur_index);
            },
            'get_selected_index' : function(){
                return _cur_index;
            }
        };
    };

    return {
        'create' : create
    }
}();

/*
    same thing but this os only for local profiles,
    ie the ones that we can use to mkae posts, edit their meta etc.
    done without the load code from above...probably need to add it...but work out what the fuck thats
    doing first because I thought the network code was stopping mutiple requests to the same resource...
*/
APP.nostr.data.local_profiles = function(){
        // as loaded
    let _profiles_arr,
        // set true when initial load is done
    _is_loaded = false,
        // has loaded started
    _load_started = false;

    function init(args){
        let o_success = args.success;
        _load_started = true;
        args.success = function(data){
            _is_loaded = true;
            _profiles_arr = data['profiles'];
            if(typeof(o_success)==='function'){
                o_success(o_success)
            }
        }

        if(_is_loaded){
            o_success(_profiles_arr);
        }else{
            APP.remote.local_profiles(args);
        }
    };

    return {
        'init' : init,
        'profiles' : function(){
            return _profiles_arr;
        }
    }

}();

APP.nostr.gui.event_detail = function(){
    let _nv_template = [
            '{{#fields}}',
                '<div style="font-weight:bold;">{{name}}</div>',
                '<div id="{{uid}}-{{name}}" style="color:gray;{{clickable}}" >{{{value}}}</div>',
            '{{/fields}}',
            '<div style="font-weight:bold;">tags</div>',
            '{{^tags}}',
                '<div style="color:gray" >[]</div>',
            '{{/tags}}',
            '{{#tags}}',
                '<div style="font-weight:bold;">{{name}}</div>',
                '<div id="{{uid}}-{{name}}" style="color:gray;" >{{.}}</div>',
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
                'tabs' : [
                    {
                        'title' : 'fields',
                    },
                    {
                        'title' : 'raw'
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

//        function draw(){
//            if(_render_obj===undefined){
//                create_render_obj();
//            }
//            _con.html(Mustache.render(_nv_template, _render_obj))
//
//            // add click events
//            $(_con).on('click', function(e){
//                let id = APP.nostr.gui.get_clicked_id(e).replace(_uid+'-','');
//
//                if(_clicks.has(id)){
//                    id = id==='event_id' ? 'id' : id;
//
//                    APP.nostr.util.copy_clipboard(_event[id], _event[id]+' - copied to clipboard');
//                }
//
//            });
//
//        }
        function render_fields(){
            _my_tabs.get_tab(0)['content-con'].html(Mustache.render(_nv_template, _render_obj));
        }

        function render_raw(){
            _my_tabs.get_tab(1)['content-con'].html('<div style="color:gray">' + APP.nostr.util.html_escape(JSON.stringify(_event))+ '</div>');
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
