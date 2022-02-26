'use strict';

!function(){
    // websocket to recieve event updates
    let _client,
    // gui objs
        _feed_con = $('#feed-pane'),
    // data
        _notes_arr,
        _profiles_arr,
        _profiles_lookup,
        _profile_draw_required = true;

    function draw_notes(){
        let tmpl = [
            '{{#notes}}',
                '<span style="height:60px;width:240px; display:table-cell;word-break: break-all;vertical-align:top;" >',
                    '{{name}}<br>',
                    '{{#picture}}',
                        '<img src="{{picture}}" width="64" height="64" />',
                    '{{/picture}}',
                '</span>',
                '<span style="height:60px; display:table-cell;display:table-cell;word-break: break-all;" >',
                    '{{content}}',
                '</span><br>',
            '{{/notes}}'
        ].join('');

        let to_show = [];

        if(_profiles_lookup!==undefined){
            _profile_draw_required = false;
        };

        _notes_arr.forEach(function(c_note){
            let name = c_note['pubkey'],
                p,
                attrs,
                pub_k = c_note['pubkey'],
                to_add = {
                    'content' : c_note['content'],
                    'name' : pub_k.substring(0, 5) + '...' + pub_k.substring(pub_k.length-5)
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
            }

            to_show.push(to_add);
        });

        _feed_con.html(Mustache.render(tmpl, {
            'notes' : to_show,
        }));
    }

    // start when everything is ready
    $(document).ready(function() {
        APP.nostr_client.create('ws://localhost:8080/websocket', function(client){
            _client = client;
//            _client.post();
        },
        function(data){
            _notes_arr.unshift(data);
            // just draw everything again...
            draw_notes();
        });

        APP.remote.load_notes(function(data){
            _notes_arr = data['notes'];
            draw_notes();
        });
        APP.remote.load_profiles(function(data){
            _profiles_arr = data['profiles'];
            _profiles_lookup = {};
            _profiles_arr.forEach(function(p){
                _profiles_lookup[p['pub_k']] = p;
            });
            if(_profile_draw_required){
                draw_notes();
            }
        });


    });
}();