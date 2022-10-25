'use strict';
/*
    view channel messages, this is done in opposite direction of general posts which on done more twitter like with
    newest at top. Here we do telegram like, the newest message will be at the bottom and there should be a text area
    for us to post, replies should quote rather than thread and clicking that reply should focus back to that msg
*/
!function(){
    const _user = APP.nostr.data.user,
        _util = APP.nostr.util,
        _filter = APP.nostr.data.filter,
        _gui = APP.nostr.gui,
        _templates = _gui.templates,
        _remote = APP.remote,
        _profiles = APP.nostr.data.profiles;
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        // channel to view
        _channel_id = _params.get('channel_id'),
        // con for al screen specfic content
        _main_con,
        // channel info head
        _header_con,
        // msgs
        _msg_con,
        _footer_con,
        // reply info con, txt area and cancle but
        _reply_info_con,
        _reply_info_txt,
        _reply_cancel_but,
        _reply_evt = null,
        // txt are and post button
        _post_but,
        _post_txt,
        _chunk_size = 100,
        _loading,
        _maybe_more,
        _until = null,
        _current_profile = _user.profile(),
        _events = [],
        _my_list,
        _my_filter = _filter.create({
            'kinds': [42],
            '#e': [_channel_id]
        });

    function draw_channel_head(){
        // getting local but eventually we'll check a check a local cache first
        _remote.load_channel({
            'id': _channel_id,
            success(data){
                if(data.error!==undefined){
                    _header_con.insertAdjacentHTML('beforeend', 'Error getting channel data: '+data.error);
                }else{
                    data.short_key = data.id;
                    data.short_owner_pub_k = data.create_pub_k;
                    _profiles.fetch({
                        'pub_k': data.create_pub_k,
                        on_load(){
                            let owner_p = _profiles.lookup(data.create_pub_k);
                            if(owner_p!==null){
                                data.owner_picture = owner_p.attrs.picture;
                                data.owner_name = owner_p.attrs.name;
                            }
                            _header_con.insertAdjacentHTML('beforeend',Mustache.render(_templates.get('channel-info-head'),data,{
                                'owner_info': _templates.get('channel-owner-info')
                            }));
                            _gui.pack();
                        }
                    });
                }

            }
        });

    }

    function load_messages(callback){
        _loading = true;
        let c_filter = _my_filter;

        if(_until!==null){
            c_filter = _my_filter.as_object();
            c_filter[0].until = _until;
            _my_filter = _filter.create(c_filter);
        }

        _remote.load_events({
            'filter' : _my_filter,
            'limit': _chunk_size,
            'embed_replies': true,
            'pub_k' : _current_profile.pub_k,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    let sorted_data = data.events;
                    sorted_data.sort((a,b) => {
                        return a.created_at - b.created_at;
                    });
                    if(_my_list===undefined){
                        draw_channel_head();
                        _my_list = APP.nostr.gui.channel_view_list.create({
                            'con': _main_con,
                            'data': sorted_data,
                            'filter': _my_filter,
                            'focus_el': _post_txt,
                            'need_event': need_event,
                            'on_reply': do_reply
                        });
                    }else{
                        _my_list.prepend_data(sorted_data);
                    }

                    if(_events.length===0){
                        _events = sorted_data;
                    }else{
                        _events = sorted_data.concat(_events);
                    }
                }
                _maybe_more = data.events.length === _chunk_size;
                _loading = false;
                if(typeof(callback)==='function'){
                    callback();
                }
            }
        });
    }

    function need_event(loaded){
        if(_maybe_more){
            _until = _events[0].created_at-1;
            load_messages(loaded);
        }else{
            _gui.notification({
                'text' : 'unable to find the replied to event'
            });
        }
    }

    function do_reply(evt){
        _reply_evt = evt;
        _reply_info_con.css('display','');
        _reply_info_txt[0].textContent = evt.content;
        _gui.pack();
        _post_txt.focus();
    }

    function cancel_reply(){
        _reply_evt = null;
        _reply_info_con.css('display','none');
        _gui.pack();
    }

    function do_post(){
       let evt = {
                'pub_k' : _current_profile.pub_k,
                'content': _post_txt.val(),
                'tags' : [['e',_channel_id]],
                'kind' : 42
            };
        _post_txt.val('');
        _post_txt[0].focus();

        if(_reply_evt!==null){
            evt.tags.push(
                ['e', _reply_evt.id, '', 'reply'],
                ['p', evt.pub_k]
            );
            cancel_reply();
        }

        APP.remote.post_event({
            'event' : evt,
            'pub_k' : _current_profile.pub_k,
            'success' : function(data){
                console.log(data);
            }
        });

    }


    // make main screen scafold
    function construct_scr(){
        _('#main_container').html(_templates.get('screen'));
        APP.nostr.gui.header.create();
//        // main container where we'll draw out the events
        _main_con = _('#main-con');
        _main_con.css('overflowY','auto');
//        // grab render areas
//        _header_con = _('#channel-info');
        _header_con = _('#header-con');

//        _msg_con.css('overflowY','auto');
//
        _footer_con = _('#footer-con');
        if(_current_profile.pub_k!==undefined){
            _footer_con.html(_templates.get('channel-view-post-area'));
        }

        // grab post gui els
        _post_but = _('#post-but');
        _post_txt = _('#post-text');
        // and reply info els
        _reply_info_con = _('#reply-info');
        _reply_info_txt = _('#reply-info-txt');
        _reply_cancel_but = _('#reply-cancel-but');
    }

    // start when everything is ready
    document.addEventListener('DOMContentLoaded', ()=> {
        if(_channel_id===null){
            alert('channel_id is required!!!');
            return;
        }

        construct_scr();
        _post_but.on('click', do_post);
        _reply_cancel_but.on('click', cancel_reply)
        _post_txt.on('input', ()=>{
            _post_but[0].disabled = _post_txt.val()==='';
        });

        _main_con.scrolledTop(function(){
            if(_maybe_more){
                _until = _events[0].created_at-1;
                load_messages();
            }
        });

        load_messages();
        // focus into the msg txt which exists if we have a profile selected
        _post_txt[0] && _post_txt[0].focus();
        _(document).on('keydown', function(e){
            if(e.key==='Escape'){
                cancel_reply();
            }
        });

        APP.nostr_client.create();

    });
}();