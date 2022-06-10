/*
    Mustache.js templates used to render parts of the screen
*/
APP.nostr.gui.templates = function(){
    let _lookup = {
        // basic template for screen we use
        'screen' : [
            '<div class="row" style="height: {{head-size}}px;">',
                '<div class="col-sm-12" style="height:100%">',
                    '<div id="header-con" style="height:100%;">',
                    '</div>',
                '</div>',
            '</div>',
            '<div class="row" style="height: calc(100% - {{head-size}}px);">',
                '<div class="col-sm-12" style="height:100%">',
                    '<div style="height:100%;">',
                        '<div id="main-con" class="event-feed">',
                        '</div>',
                    '</div>',
                '</div>',
            '</div>'
        ],
        'head' : [
            '<div id="profile_button" class="header-button"></div>'
        ],
        // the render for when we don't have a profile (user hasn't selected one)
        'no_user_profile_button' : [
            '<svg class="bi" style="height:100%;width:100%;">',
                '<use xlink:href="/bootstrap_icons/bootstrap-icons.svg#person-circle"/>',
            '</svg>',
        ],
        // container area for notifications, top of screen
        'notification-container' : '<div id="notifications" style="position:absolute;opacity:0.9;z-index:100;width:100%"></div>',
        // notification content
        'notification' : ['<div id="{{id}}" class="alert alert-{{type}}" role="alert" style="margin-bottom:2px;overflow-wrap:anywhere;" >',
                            '{{text}}',
                        '</div>'],
        // used on contacts page, searching profiles and selected profile to use
        'profile-list' : ['<div id="{{uid}}-{{pub_k}}" style="padding-top:2px;cursor:pointer">',
                            '<span style="display:table-cell;width:128px; background-color:#111111;padding-right:10px;" >',
                                // TODO: do something if unable to load pic
                                '{{#picture}}',
                                    '<img src="{{picture}}" loading="lazy" class="profile-pic-small"/>',
                                '{{/picture}}',
                            '</span>',
                            '<span style="width:100%; display:table-cell;word-break: break-all;vertical-align:top; background-color:#221124" >',
                            '{{#profile_name}}',
                                '[{{profile_name}}]<br>',
                            '{{/profile_name}}',
                            '{{#name}}',
                                '{{name}}@',
                            '{{/name}}',
                            '<span class="pubkey-text">{{short_pub_k}}</span><br>',
                                '{{#about}}',
                                    '<div>',
                                        '{{{about}}}',
                                    '</div>',
                                '{{/about}}',
                            '</span>',
                        '</div>'
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
