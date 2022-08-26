/*
    Mustache.js templates used to render parts of the screen
*/
APP.nostr.gui.templates = function(){
    let _lookup = {
        // basic template for screen we use
        'screen' : [
            '<div class="row header-row" >',
                '<div class="col-sm-12" style="height:100%;">',
                    '<div id="header-con" style="height:100%">',
                    '</div>',
                '</div>',
            '</div>',
            '<div class="row main-row" >',
                '<div class="col-sm-12" style="height:100%;">',
                    '<div style="height:100%;">',
                        '<div id="main-con" style="height:100%;" >',
                        '</div>',
                    '</div>',
                '</div>',
            '</div>'
        ],
        'screen-profiles-search' : [
            //the input
            '<div style="width:100%;overflow:hidden; height:40px;">',
                '<input placeholder="search" type="text" class="form-control" id="search-in" />',
            '</div>',
            //profiles listed here
            '<div id="list-con" style="overflow-y:auto;height: calc(100% - 40px);"></div>'
        ],
        'screen-profile-view' : [
            '<div class="profile-view-about-pane" id="about-pane">',
                'loading...',
            '</div>',
            '<div class="profile-view-tab-pane" id="tab-pane"  >',
            '</div>'
        ],
        // same as above, maybe will end up different or myabe this will be the template for basic search page
        'screen-events-search' : [
            '<div style="width:100%;overflow:hidden; height:40px;">',
                '<input placeholder="search" type="text" class="form-control" id="search-in" />',
            '</div>',
            '<div id="list-con" style="overflow-y:auto;height: calc(100% - 40px);"></div>'
        ],
        'screen-contact-view' : [
            '<div id="about-con" style="height:64px;"></div>',
            '<div id="contact-tabs" style="height:calc(100% - 64px);min-height:400px;" ></div>'
        ],
        'screen-profile-struct' : [
            '<div style="background-color:#221124;height:100%; min-height:400px;" >',
                '<span class="pubkey-text">{{mode}} {{pub_k}}</span>',
                // different text dependent on mode
                '{{#link_existing}}',
                    '<button style="margin-left:16px" id="private_key" type="button" class="btn btn-default" >link existing account</button>',
                '{{/link_existing}}',
                '{{#link_suggest}}',
                    '<button style="margin-left:16px" id="private_key" type="button" class="btn btn-default" >link this account</button>',
                '{{/link_suggest}}',
                '{{#view_priv}}',
                    '<button style="margin-left:16px" id="private_key" type="button" class="btn btn-default" >export profile</button>',
                '{{/view_priv}}',
                '<div id="picture-con">',
                    'loading...',
                '</div>',
                '<div id="edit-con" >',
                    'loading...',
                '</div>',
                '<div style="float:right;margin-top:50px;" id="action-con">',
                    '<button style="display:none" id="save-button" type="button" class="btn btn-default" >save</button>',
                    '<button id="publish-button" type="button" class="btn btn-default" >publish</button>',
                '</div>',
            '<div>'
        ],
        'screen-relay-edit-struct' : [
            '<div id="relay-select-con"></div>',
            '<div id="current-con"></div>'
        ],
        'head' : [
            '<div >',
                '<div id="profile-but" class="header-button"></div>',
                '<div id="event-search-but" class="header-button">',
                    '<svg class="bi-post" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#search"/>',
                    '</svg>',
                '</div>',
                '<div id="profile-search-but" class="header-button">',
                    '<svg class="bi-post" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-plus-fill"/>',
                    '</svg>',
                '</div>',
                '<div id="home-but" class="header-button" >',
                    '<svg class="bi-post" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#app"/>',
                    '</svg>',
                '</div>',
                '<div id="message-but" class="header-button" {{{message_style}}}>',
                    '<svg class="bi-post" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#envelope-fill"/>',
                    '</svg>',
                '</div>',
                '<div id="relay-but" class="header-button" style="float:right;{{relay_style}}">',
                    '<svg class="bi-post" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#diagram-3"/>',
                    '</svg>',
                '</div>',
            '</div>'
        ],
        // templates for modals
        'modal-note-post' : [
            '<div>',
                // event.id is to stop render of the div when not replying
                '{{#event.id}}',
                    '{{{#event}}}',
                        '{{> event}}',
                    '{{{/event}}}',
                '{{/event.id}}',
            '</div>',
            '<div>',
                '<textarea id="nostr-post-text" class="form-control" rows="10" placeholder="whats going down?"></textarea>',
            '</div>'
        ],
        // just view of relays at moment
        'relay-list' : [
            '<div style="height:100%; overflow-y:auto" >',
                '<div id="{{uid}}-header" style="background-color:#221124;" >',
                    '{{>status}}',
                '</div>',
                '<div id="{{uid}}-list" style="min-width:100%;width:100%" >loading</div>',
            '</div>'
        ],
        'relay_list-status' :[
            '<span>&nbsp;</span>',
            '<span style="float:right" >{{status}} {{connect-count}} of {{relay-count}}</span>'
        ],
        'modal-relay-list-row' : [
            '<div style="width:100%;padding-top:2px;border:1px solid #222222;background-color:#221124;" >',
                '<span style="display:inline-block:min-width:100%" >',
                    '{{url}}',
                '</span>',
                '<span style="display:inline-block;width:100%; padding-left:10px;color:gray;" >',
                    '<span id="{{relay_uid}}-con-status" >',
                        '{{> con-status}}',
                    '</span>',
                    '<span style="float:right">',
                        '{{^is_mode_edit}}',
                            '{{mode_text}}',
                        '{{/is_mode_edit}}',
                        '{{#is_mode_edit}}',
                            'dropdown',
                            '<svg id="{{relay_uid}}-remove" class="bi" style="color:red;">',
                                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#x-circle-fill"/>',
                            '</svg>',
                        '{{/is_mode_edit}}',
                    '</span>',
                '</span>',
            '</div>'
        ],
        'relay-con-status' : [
            '{{#connected}}',
                'connected',
            '{{/connected}}',
            '{{^connected}}',
                '<span style="display:inline-block;height:16px;width:16px;" >',
                    '<svg class="bi" style="height:100%;width:100%;color:red;">',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#exclamation-triangle-fill"/>',
                    '</svg>',
                '</span>',
                '<span>',
                    'not connected',
                    '{{#last_err}}',
                        '- {{last_err}}',
                    '{{/last_err}}',
                '</span>',
                '<span >',
                    '{{#last_connect}}',
                        ' last connected {{last_connect}}',
                    '{{/last_connect}}',
                '</span>',
            '{{/connected}}',
        ],
        // the render for when we don't have a profile (user hasn't selected one)
        'no_user_profile_button' : [
            '<svg class="bi" style="height:100%;width:100%;">',
                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-circle"/>',
            '</svg>'
        ],
        // container area for notifications, top of screen
        'notification-container' : '<div id="notifications" style="position:absolute;opacity:0.9;z-index:100;width:100%"></div>',
        // notification content
        'notification' : ['<div id="{{id}}" class="alert alert-{{type}} fade show" role="alert" style="margin-bottom:2px;overflow-wrap:anywhere;" >',
                            '{{text}}',
                        '</div>'],
        // used on contacts page, searching profiles and selected profile to use
        'profile-list' : ['<div id="{{uid}}-{{pub_k}}" style="padding-top:2px;cursor:pointer;" >',
                            '<span class="profile-picture-area {{picture-selected}}" >',
                                // TODO: do something if unable to load pic
                                '{{#picture}}',
                                    '<img src="{{picture}}" loading="lazy" class="profile-pic-small""/>',
                                '{{/picture}}',
                                '{{^picture}}',
                                    '<div class="header-button">',
                                        '<svg class="bi" style="height:100%;width:100%;">',
                                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-circle"/>',
                                        '</svg>',
                                    '</div>',
                                '{{/picture}}',
                            '</span>',
                            '<span class="profile-detail-area {{detail-selected}}" >',
                                '{{#profile_name}}',
                                    '[{{profile_name}}]<br>',
                                '{{/profile_name}}',
                                '{{#name}}',
                                    '{{name}}@',
                                '{{/name}}',
                                '{{#short_pub_k}}',
                                    '<span class="pubkey-text">{{short_pub_k}}</span>',
                                '{{/short_pub_k}}',
                                '{{#about}}',
                                    '<div>',
                                        '{{{about}}}',
                                    '</div>',
                                '{{/about}}',
                                // action buttons that are shown to the right dependent on context
                                '<span style="float:right;margin-right:8px;">',
                                    '{{#can_dm}}',
                                        '<svg id="{{uid}}-{{pub_k}}-profile-dm" class="bi" >',
                                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#envelope-fill"/>',
                                        '</svg>',
                                    '{{/can_dm}}',
                                    // follow or not only if not our profile
                                    '{{#other_profile}}',
                                        '{{#follows}}',
                                            '<svg id="{{uid}}-{{pub_k}}-profile-fol" class="bi" >',
                                                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star-fill"/>',
                                            '</svg>',
                                        '{{/follows}}',
                                        '{{^follows}}',
                                            '<svg id="{{uid}}-{{pub_k}}-profile-fol" class="bi" >',
                                                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#star"/>',
                                            '</svg>',
                                        '{{/follows}}',
                                    '{{/other_profile}}',
                                    '{{#can_view}}',
                                        '<svg id="{{uid}}-{{pub_k}}-profile-view" class="bi" >',
                                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#eye-fill"/>',
                                        '</svg>',
                                    '{{/can_view}}',
                                    '{{#can_edit}}',
                                        '<svg id="{{uid}}-{{pub_k}}-profile-edit" class="bi" >',
                                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#pencil-square"/>',
                                        '</svg>',
                                    '{{/can_edit}}',
                                    '{{#can_switch}}',
                                        '<svg id="{{uid}}-{{pub_k}}-profile-switch" class="bi" >',
                                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#box-arrow-right"/>',
                                        '</svg>',
                                    '{{/can_switch}}',
                                '</span>',
                            '</span>',
                        '</div>'
                        ],
        // event templates
        'event-profile' : [
            // publishers profile pic
            '<span style="display:table-cell; background-color:#111111;padding-right:10px;" >',
                // TODO: do something if unable to load pic
                '{{#picture}}',
                    '<img id="{{uid}}-{{event_id}}-pp" src="{{picture}}" class="profile-pic-small" />',
                '{{/picture}}',
            '</span>',
        ],
        'event-content' : [
            '<span id="{{uid}}-{{event_id}}-content" class="post-content" >',
                '<div >',
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
                '{{#subject}}',
                    '[{{subject}}]<br>',
                '{{/subject}}',
                '{{{content}}}',
                '{{#external}}',
                    '<div id="{{uid}}-{{event_id}}-preview">',
                        '{{#preview}}',
                            '{{> preview}}',
                        '{{/preview}}',
                        '{{^preview}}',
                            '<button type="button" class="btn btn-block web-preview-btn" >preview</button>',
                        '{{/preview}}',
                    '</div>',
                '{{/external}}',
                '{{> actions}}',
            '</span>'
        ],
        'dm-content' : [
            '<span id="{{uid}}-{{event_id}}-content" class="post-content" >',
                '<div >',
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
                '<div>',
                    '<img id="{{uid}}-{{event_id}}-lastpp" class="profile-pic-verysmall" style="float:left;" src="{{sender_picture}}" />',
                    '<span style="text-align: justify;" >{{{content}}}</span>',
                '</div>',
            '</span>'
        ],
        'event-actions' : [
            '<div style="width:100%">',
                '<span>&nbsp;</span>',
                '<span style="float:right" >',
                    '{{#can_reply}}',
                        '<svg id="{{uid}}-{{event_id}}-reply" class="bi" >',
                            '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#chat-right-fill"/>',
                        '</svg>',
                    '{{/can_reply}}',
                    '<svg id="{{uid}}-{{event_id}}-expand" class="bi" >',
                        '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#three-dots-vertical"/>',
                    '</svg>',
                '</span>',
                '<div',
                        'style="border:1px dashed gray;display:none; cursor:default;" id="{{uid}}-{{event_id}}-expandcon" style="display:none">',
                        'event detail...',
                    '</div>',
            '</div>'
        ],
        // attempts to give some visual info about linkage of this event to others if any...
        'event-path' : [
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
            '{{/missing_parent}}'
        ],
        // main event view
        'event' : [
            '<div id="{{uid}}-{{event_id}}" style="padding-top:2px;border 1px solid #222222">',
                '{{> profile}}',
                '{{> path}}',
                // the note content
                '{{> content}}',
            '</div>',
        ],
        'dm-event' : [
            '<div id="{{uid}}-{{event_id}}" style="padding-top:2px;border 1px solid #222222">',
                '{{> profile}}',
                // the note content
                '{{> content}}',
            '</div>'
        ],
        // preview snippets for events
        'web-preview' : [
            '<div class="web-preview" >',
                '{{#wp_img}}',
                    '<div style="display:table-cell;width:200px" >',
                        '<img src={{wp_img}} style="border-radius:10px;height:150px;width:auto;min-width:200px;object-fit: cover;" >',
                    '</div>',
                '{{/wp_img}}',
                '<div style="display:table-cell;vertical-align:top;padding-left:10px;">',
                    '<b>{{wp_title}}</b><br>',
                    '{{wp_description}}',
                '</div>',
            '</div>'
        ],
        'bs-select': [
            '<select class="form-select" aria-label="{{description}}"',
                '{{#options}}',
                    '<option {{selected}} value="{{value}}" >{{text}}</option>',
                '{{/options}}',
            '</select>'
        ]

    };

    return {
        'get' : function(name){
            let ret = _lookup[name];
            if(ret===undefined){
                ret = '?unknown template '+name+'?';
            }else if(typeof(ret)!=='string'){
                // doubt it makes much difference but only joined once
                // and we do the preparse here too
                ret = _lookup[name] = ret.join('');
                Mustache.parse(ret);
            }
            return ret;
        }
    }
}();
