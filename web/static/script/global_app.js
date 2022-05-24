'use strict';

// TODO: nostr stuff will be moved out to be share
APP.nostr = {
    'gui' : {},
    'util' : {
        'short_key': function (pub_k){
            return pub_k.substring(0, 3) + '...' + pub_k.substring(pub_k.length-4)
        }
    }
};

APP.nostr.gui.event_view = function(){
    let _con,
        // notes as given to us (as they come from the load)
        _notes_arr,
        // data render to be used to render
        _render_arr,
        // profiles as given (from load) in arr format, at the moment we assume we can get all in memory
        // TODO: add/chaneg as profile METAs are seen
        _profiles_arr,
        // key'd pubk for access
        _profiles_lookup,
        // attempt to render external media in note text.. could be more fine grained to type
        // note also this doesn't cover profile img
        _enable_media = true,
        // have we drawn once already? incase profiles arrive after notes
        _draw_done = false,
        // template for individual event in the view, styleing should move to css and classes
        _row_tmpl = [
            '{{#notes}}',
                '<div style="padding-top:2px;">',
                '<span style="height:60px;width:120px; word-break: break-all; display:table-cell; background-color:#111111;padding-right:10px;" >',
                    // TODO: do something if unable to load pic
                    '{{#picture}}',
                        '<img src="{{picture}}" width="64" height="64" style="object-fit: cover;border-radius: 50%;" />',
                    '{{/picture}}',
                    // if no picture, again do something here
                    '{{^picture}}',
                        '<div style="height:60px;width:64px">no pic</div>',
                    '{{/picture}}',
                '</span>',
                '<span style="height:60px;width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                    '<div>',
                        '{{#name}}',
                            '<span style="font-weight:bold">{{name}}</span>@<span style="color:cyan">{{short_key}}</span>',
                        '{{/name}}',
                        '{{^name}}',
                            '<span style="font-weight:bold">{{short_key}}</span>',
                        '{{/name}}',
                    '</div>',
                    '{{{content}}}',
                '</span>',
                '</div>',
            '{{/notes}}'
        ].join('');

    function _create_contents(){
        _render_arr = []
        _notes_arr.forEach(function(c_note){
            _render_arr.push(_note_content(c_note));
        });
    };

    function _note_content(the_note){
        let name = the_note['pubkey'],
            p,
            attrs,
            pub_k = the_note['pubkey'],
            to_add = {
                'content' : get_note_html(the_note),
                'short_key' : APP.nostr.util.short_key(pub_k)
            };

        if(_profiles_lookup!==undefined){
            p = _profiles_lookup[name];
            if(p!==undefined){
                attrs = p['attrs'];
                if(attrs!==undefined){
                    if(attrs['name']!==undefined){
                        to_add['name'] = attrs['name'];
                    }
                    if(attrs['picture']!==undefined){
                        to_add['picture'] = attrs['picture'];
                    }

                }
            }
        };
        return to_add;
    }


    /*
        where we found link text what type of media is it so we can inline it...
        if _enable_media this will always return external_link, i.e. don't render just insert
        a tag.
        Note profile pics are external media and we still render those..
        possible there should be an option not to render those too
    */
    function media_lookup(ref_str){
        let media_types = {
            'jpg': 'image',
            'png': 'image',
            'mp4': 'video'
            },
            parts = ref_str.split('.'),
            ext = parts[parts.length-1],
            ret = 'external_link';

        if(ext in media_types && _enable_media){
            ret = media_types[ext];
        }
        return ret;
    }

    /*
        returns the_note.content str as we'd like to render it
        i.e. make http::// into <a hrefs>, if inline media and allowed insert <img> etc
    */
    function get_note_html(the_note){
        let http_regex = /(https?\:\/\/[\w\.\/\-\%\?\=]*)/g,
            http_matches,
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

        // html escape
        function _escapeHtmlChars(in_str){
            return in_str.replaceAll('&', '&amp;').
            replaceAll('<', '&lt;').
            replaceAll('>', '&gt;').
            replaceAll('"', '&quot;').
            replaceAll("'", '&#39;');

        };

        // make str safe for browser render as we're going to insert html tags
        ret = _escapeHtmlChars(ret);

        // add line breaks
        ret = ret.replace(/\n/g,'<br>');
        // look for link like strs
        http_matches = ret.match(http_regex);
        // do inline media and or link replacement
        if(http_matches!==null){
            http_matches.forEach(function(c_match){
                let media_type = media_lookup(c_match);
                ret = ret.replace(c_match,Mustache.render(tmpl_lookup[media_type],{
                    'url' : c_match
                }));
            });
        }
        return ret;
    };

    function create(args){
        _con = args.con;
        _enable_media = args.external_media!==undefined ? args.external_media : true;

        function set_notes(the_notes){
            _notes_arr = the_notes;
            // makes [] that'll be used render display
            _create_contents();
            // now draw
            redraw();
            _draw_done = true;
        };

        function set_profiles(profiles_arr){
            _profiles_arr = profiles_arr;
            _profiles_lookup = {};
            _profiles_arr.forEach(function(p){
                _profiles_lookup[p['pub_k']] = p;
            });

            if(_draw_done){
                _create_contents();
                redraw();
            }
        }

        function add_note(evt){
            if(evt['kind']===1){
                // just insert the new event
                _notes_arr.unshift(evt);
                _render_arr.unshift(_note_content(evt));
                _con.prepend(Mustache.render(_row_tmpl,{
                    'notes' : [_render_arr[0]]
                }));
            }

//            redraw();
        }

        function redraw(){
            _con.html(Mustache.render(_row_tmpl, {
                'notes' : _render_arr
            }));
        };


        // methods for event_view obj
        return {
            'set_notes' : set_notes,
            'set_profiles' : set_profiles,
            'add' : add_note
        };
    };

    return {
        'create' : create
    };
}();


/*
    show all texts type events as they come in
*/
!function(){
    // websocket to recieve event updates
    let _client,
    // gui objs
        // main container where we'll draw out the events
        _text_con = $('#feed-pane'),
    // data
        _my_event_view = APP.nostr.gui.event_view.create({
            'con' : _text_con
        }),
    // inline media where we can, where false just the link is inserted
        _enable_media = true;

    function start_client(){
        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
            _client = client;
        },
        function(data){
            _my_event_view.add(data);
        });
    }

    function load_notes(){

        APP.remote.load_events({
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    _my_event_view.set_notes(data['events']);
                }
            }
        });
    }

    function load_profiles(){
        APP.remote.load_profiles(function(data){
            _my_event_view.set_profiles(data['profiles']);
        });
    }

    // start when everything is ready
    $(document).ready(function() {
        // start client for future notes....
        load_notes();
        // obvs this way of doing profile lookups isn't going to scale...
        load_profiles();
        // to see events as they happen
        start_client();
    });
}();