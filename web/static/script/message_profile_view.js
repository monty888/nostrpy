'use strict';

/*
    show all texts type events as they come in
*/
!function(){
    const _gui = APP.nostr.gui,
        _templates = _gui.templates;
        // websocket to recieve event updates
    let _client,
        // url params
        _params = new URLSearchParams(window.location.search),
        //
        _pub_k = _params.get('pub_k'),
        _events = [],
        _chunk_size = 100,
        _maybe_more,
        _until = null,
        _loading,
        // main container areas
        _main_con,
        _header_con,
        _footer_con,
        // reply info con, txt area and cancel but
        _reply_info_con,
        _reply_info_txt,
        _reply_cancel_but,
        _reply_evt = null,
        // txt are and post button
        _post_but,
        _post_txt,
        // for now we're using a standard event view, maybe in future
        // compress down into unique users
        _my_list,
        _current_profile = APP.nostr.data.user.profile(),
        _my_filter;

    function draw_profile_head(){
//        _header_con.html('profile info here!!');
        _gui.pack();
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
                'tags' : [['p', _pub_k]],
                'kind' : 4
            };
        _post_txt.val('');
        _post_txt[0].focus();

        if(_reply_evt!==null){
            evt.tags.push(
                ['e', _reply_evt.id, '', 'reply']
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

    function load_notes(){
        APP.remote.load_events({
            'pub_k' : APP.nostr.data.user.profile().pub_k,
            'filter' : _my_filter,
            'embed_replies': true,
            'success': function(data){
                if(data['error']!==undefined){
                    alert(data['error']);
                }else{
                    let sorted_data = data.events;
                    sorted_data.sort((a,b) => {
                        return a.created_at - b.created_at;
                    });
                    if(_my_list===undefined){
                        draw_profile_head();
                        _my_list = APP.nostr.gui.channel_view_list.create({
                            'con': _main_con,
                            'data': sorted_data,
                            'filter': _my_filter,
                            'focus_el': _post_txt,
//                            'need_event': need_event,
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

        // make main screen scafold
    function construct_scr(){
        _('#main_container').html(_templates.get('screen'));
        APP.nostr.gui.header.create();
        _main_con = _('#main-con');
        _main_con.css('overflowY','auto');
        _main_con.css('max-height', '200px;')
        // info on profile we're dming will be here
        _header_con = _('#header-con');

        // controls for posting here
        _footer_con = _('#footer-con');
        _footer_con.html(_templates.get('channel-view-post-area'));

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
        if(_pub_k===null){
            alert('pub_k is required');
            return;
        }

        // main page struc
        construct_scr();
        _my_filter = APP.nostr.data.filter.create([
            {
                'kinds' :[4],
                'authors' : [_current_profile.pub_k],
                '#p': [_pub_k]
            },
            {
                'kinds': [4],
                'authors' : [_pub_k],
                '#p' : [_current_profile.pub_k]
            }
        ]);

        load_notes();

        _post_but.on('click', do_post);
        _reply_cancel_but.on('click', cancel_reply);
        _post_txt.on('input', ()=>{
            _post_but[0].disabled = _post_txt.val()==='';
        });

        _(document).on('keydown', function(e){
            if(e.key==='Escape'){
                cancel_reply();
            }
        });


        // start client for future notes....
        APP.nostr_client.create();
        _post_txt[0].focus();

    });
}();