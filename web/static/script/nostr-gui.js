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
            _profile_but.css('background-image','');
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
        // grab buttons
        _profile_but = $('#profile-but');
        _home_but = $('#home-but');
        _event_search_but = $('#event-search-but');
        _profile_search_but = $('#profile-search-but');



        _current_profile = APP.nostr.data.user.get_profile();
        set_profile_button();
        watch_profile();

        // add events
        _profile_but.on('click', function(){
            APP.nostr.gui.profile_select_modal.show();
        });

        _home_but.on('click', function(){
            if(window.location.pathname!=='/'){
                window.location='/';
            }
        });

        _event_search_but.on('click', function(){
            location.href = '/html/event_search.html';
        });

        _profile_search_but.on('click', function(){
            location.href = '/html/profile_search.html';
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
            check_show(APP.nostr.data.user.get_profile());

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
        args = args||{};
        let title = args.title || '?no title?';
            content = args.content || '',
            ok_text = args.ok_text || '?no_text?',
            on_ok = args.on_ok,
            on_show = args.on_show;

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

            _my_modal.on('shown.bs.modal', function () {
                if(typeof(on_show)==='function'){
                    on_show();
                }
            })

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

    function show(on_show){

        // create must have been called before calling show
        _my_modal.modal();
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

APP.nostr.gui.post_modal = function(){

    // TODO as https://github.com/nostr-protocol/nips/blob/master/10.md
    // add reply and root markers, we need a preferred relay first though
    // as it's not optional
    function add_reply_tags(o_event){
        let ret = [],
            to_pub_key = o_event.pubkey;
            to_evt_id = o_event.id,
            add_pub = true;
            add_evt = true;
        // copy all tags, don't thinnk it matters much but also check that
        // we're not going to dupl the p or e tags that we are going to add
        o_event.tags.forEach(function(c_tag,i){
            // tags from the original event that are kept
            const keep = new Set(['p','e']);

            // if it has a val and is a tag that we keep then add
            if(keep.has(c_tag[0]) && c_tag[1]!==undefined && c_tag[1]!==null && c_tag[1]!==''){
                ret.push(c_tag);
                // don't think its a problem but won't duplicate anyhow
                if((c_tag[0]==='p' && c_tag[1]===to_pub_key)){
                    add_pub = false;
                }
                if((c_tag[0]==='e' && c_tag[1]===to_evt_id)){
                    add_evt = false;
                }
            }
        });

        if(add_pub){
            ret.push(['p', to_pub_key]);
        }
        if(add_evt){
            ret.push(['e', to_evt_id]);
        }

        return ret;
    }

    function show(args){
        args =args || {};
        let gui = APP.nostr.gui,
            user = APP.nostr.data.user,
            type = args.type!==undefined ? args.type : 'post',
            event = args.event !==undefined ? args.event : {
                'id' : '?',
                'content' : 'something has gone wrong!!',
                'tags' :[]
            },
            title = 'make post',
            post_text_area,
            render_obj= {},
            uid = gui.uid();

            if(type==='reply'){
                title = 'reply to event <span class="pubkey-text" >'+APP.nostr.util.short_key(event.id)+'<span/>';
                // because we're going to give another id just so we don't get mutiple els with same id in dom
                render_obj['event'] = jQuery.extend({}, event);
                render_obj['event'].uid = uid;
                render_obj['picture'] = gui.get_profile_picture(event.pubkey);
                render_obj['content'] = gui.get_note_content_for_render(event);

            }

            APP.nostr.gui.modal.create({
                'title' : title,
                'content' : Mustache.render(gui.templates.get('modal-note-post'),render_obj, {
                    'event' : gui.templates.get('event'),
                    'profile' : gui.templates.get('event-profile'),
                    'content' : gui.templates.get('event-content'),
                }),
                'ok_text' : 'send',
                'on_ok' : function(){
                    let n_tags = type==='reply' ? add_reply_tags(event) : [],
                        content = post_text_area.val()
                        hash_tags = content.match(/\#\w*/g);

                    // add hashtags
                    if(hash_tags!==null){
                        hash_tags.forEach(function(c_tag){
                            n_tags.push(['hashtag',c_tag.replace('#','')]);
                        });
                    }

                    if(user.is_add_client_tag()===true){
                        n_tags.push(['client', user.get_client()]);
                    }

                    APP.remote.post_event({


                        'event' : {
                            'pub_k' : user.get_profile().pub_k,
                            'content': content,
                            'tags' : n_tags
                        }
                    });
                },
                'on_show' : function(){
                    post_text_area.focus();
                }
            });

        post_text_area = $('#nostr-post-text');
        // nothing is clickable!
        if(type==='reply'){
            $('#'+uid+'-'+render_obj.event.event_id+'-pp').css('cursor','default');
            $('#'+uid+'-'+render_obj.event.event_id-'content').css('cursor','default !important');
        }


        APP.nostr.gui.modal.show();

    }

    return {
        'show': show
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

APP.nostr.gui.list = function(){
    const CHUNK_SIZE = 50,
        CHUNK_DELAY = 200;

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
            _empty_message = args.empty_message || 'nothing to show!';

        // draw the entire list
        // TODO: chunk draw, max draw amount
        // future
        function draw(){
            clearInterval(_draw_timer);
            _con.html('');
            if(_data.length===0){
                _con.html(_empty_message);
            }else if(_render_chunk && _data.length> _chunk_size){
                let c_start=0,
                    c_end=_chunk_size,
                    last_block = false;

                function _prog_draw(){
                    c_start = draw_chunk(c_start, c_end);
                    if(!last_block){
                        c_end+=_chunk_size;
                        if(c_end>=_data.length){
                            c_end = _data.length;
                            last_block = true
                        }
                        _draw_timer = setTimeout(_prog_draw,CHUNK_DELAY);
                    }


                }

                _prog_draw();
//                _draw_timer = setTimeout(_prog_draw,CHUNK_DELAY);


            }else{
                draw_chunk(0, _data.length);
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
        // global profiles obj
        _profiles = APP.nostr.data.profiles;

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
            _my_list,
            // interval timer for updating times
            _time_interval;


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
            to_add = {
                'is_parent' : the_note.is_parent,
                'missing_parent' : the_note.missing_parent,
                'is_child' : the_note.is_child,
                'uid' : _uid,
                'evt': the_note,
                'event_id' : the_note.id,
                'short_event_id' : APP.nostr.util.short_key(the_note.id),
                'content' : _gui.get_note_content_for_render(the_note),
                'short_key' : APP.nostr.util.short_key(pub_k),
                'pub_k' : pub_k,
                'picture' : _gui.get_profile_picture(pub_k),
                'at_time': dayjs.unix(the_note.created_at).fromNow()
            };


            if(_profiles.is_loaded()){
                p = _profiles.lookup(name);
                if(p!==undefined){
                    attrs = p['attrs'];
                    if(attrs!==undefined){
                        if(attrs['name']!==undefined){
                            to_add['name'] = attrs['name'];
                        }
                        to_add.picture = _gui.get_profile_picture(pub_k);

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

        function _row_render(r_obj, i){
            return Mustache.render(_gui.templates.get('event'), r_obj,{
                'profile' : _gui.templates.get('event-profile'),
                'path' : _gui.templates.get('event-path'),
                'content' : _gui.templates.get('event-content'),
                'actions' : _gui.templates.get('event-actions')
            })
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

            // makes [] that'll be used render display
            _create_contents();
        };

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
//                let add_content = _note_content(evt);
                // just insert the new event
                _notes_arr.unshift(evt);
                // this results in a full recheck of order and redraw
                // probably we could do more efficent but this is simplest and will do for now
                _create_contents();

//                _render_arr.unshift(add_content);
//
//                // we won't redraw the whole list just insert at top
//                // which should be safe (end might be ok, but anywhere else would be tricky...)
////                _con.prepend(Mustache.render(_row_tmpl,_render_arr[0]));
//                _con.prepend(_row_render(_render_arr[0], 0));
//                _event_map[evt.id] = {
//                    'event' : evt,
//                    'render_event': add_content
//                };

            }
        }

        // update the since every 30s
        _time_update = setInterval(_time_update, 1000*30);

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

APP.nostr.gui.profile_select_modal = function(){
    let _uid = APP.nostr.gui.uid(),
        // short cut ot profiles helper
        _profiles = APP.nostr.data.profiles;

    function draw_profiles(profiles){
        // just incase it didn't get inted yet
        _profiles.init();

        let row_tmpl = APP.nostr.gui.templates.get('profile-list'),
            list,
            render_obj = [{
                // the no profile profile.. just browse
                'uid' : _uid,
                'profile_name' : 'lurker',
                'about' : 'browse without using a profile'
            }],
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
                let pub_k = id.replace(_uid+'-', ''),
                    p = _profiles.lookup(pub_k);

                // should be the lurker profile
                if(p===undefined){
                    p = {}
                };

                APP.nostr.data.user.set_profile(p);
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