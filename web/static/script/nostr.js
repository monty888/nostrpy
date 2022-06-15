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
            },
            'get_profile_picture' : function(pub_k){
                // default, note returned even if enable_media is false... thats because
                // eventually the robos will be local and won't require going external to get...
                let ret = APP.nostr.gui.robo_images.get_url({
                        'text' : pub_k
                    }),
                    profiles = APP.nostr.data.profiles;

                    if(profiles.is_loaded()){
                        p = profiles.lookup(pub_k);

                        // we found the profile
                        if(p!==undefined){
                            attrs = p['attrs'];
                            if(attrs!==undefined){
                                if(APP.nostr.data.user.enable_media() && attrs['picture']!==undefined){
                                    ret = attrs['picture'];
                                }
                            }
                        }

                    }
                return ret;
            },
            'get_note_content_for_render' : function(evt){
                let enable_media = APP.nostr.data.user.enable_media(),
                    content = evt.content;

                // make safe
                content = APP.nostr.util.html_escape(content);
                // insert media tags to content
                content = APP.nostr.gui.http_media_tags_into_text(content, enable_media);
                // do p tag replacement
                content = APP.nostr.gui.tag_replacement(content, evt.tags)
                // add line breaks
                content = content.replace(/\n/g,'<br>');
                // fix special characters as we're rendering in html el
                content = APP.nostr.util.html_unescape(content);

                return content;
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
                o_success(_profiles_arr)
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