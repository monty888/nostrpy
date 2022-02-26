'use strict';

!function(){
    // max matching contacts we'll show
    const MAX_CONTACTS = 50;

    // data
    let _profiles,
        _profiles_lookup = {},
        _c_profile,
        // profiles that match current search critera
        _profile_matches = [],
    // gui parts
        // all profiles listed here
        _list_con = $('#list-con'),
        // after clicking on profile, display more info here
        _profile_con = $('#profile-con'),
        // follower/following or notes for current profile dependent on what user selects
        _feed_con = $('#feed-con'),
        // filter to search contacts list
        _contact_search_in = $('#contact_search_in');

    function redraw_contacts(){
        let tmpl_str = [
            '{{#profiles}}',
                // if we have a name use that
                '<div id={{pub_k}} style="cursor:pointer" >',
                    '{{#attrs.name}}',
                        '{{attrs.name}}',
                    '{{/attrs.name}}',
                    // else just the pub_k
                    '{{^attrs.name}}',
                        '{{pub_k}}',
                    '{{/attrs.name}}',
                '</div>',
            '{{/profiles}}'
            ].join('');

        get_profile_matches();

        _list_con.html(Mustache.render(tmpl_str, {
            'profiles' : _profile_matches
        }));
    }

    function get_profile_matches(){
        _profile_matches = [];
        // get current filter matches
        let filter_val = _contact_search_in.val().trimStart().trimEnd(),
            match_count = 0,
            to_test_str,
            c_profile;

        if(filter_val===''){
            _profile_matches = _profiles.slice(0, MAX_CONTACTS);
        }else{
            for(var i=0;i<_profiles.length;i++){
                c_profile = _profiles[i];
                to_test_str = c_profile['pub_k'];

                if(c_profile.attrs.name!==undefined){
                    to_test_str += c_profile.attrs.name;
                }

                // got a match
                if(to_test_str.indexOf(filter_val)>=0){
                    _profile_matches.push(c_profile);
                    // found enough matches
                    if(_profile_matches.length>=MAX_CONTACTS){
                        break;
                    }
                }
            }
        }

    }


    function draw_selected_profile(){
        let tmpl_str = [
            '{{#attrs.picture}}',
                '<span style="display: table-cell;">',
                     '<img src="{{attrs.picture}}" width="128" height="128" />',
                '</span>',
            '{{/attrs.picture}}',
            '<span style="display: table-cell;word-break: break-all;vertical-align:top;">',
                '<b>pub_key : </b>{{pub_k}}<br>',
                '{{#attrs.name}}',
                    '<b>name :</b> {{attrs.name}}<br>',
                '{{/attrs.name}}',
                '{{#attrs.about}}',
                    '<b>about :</b> {{attrs.about}}<br>',
                '{{/attrs.about}}',
            '</span>'
        ].join('');
        _profile_con.html(Mustache.render(tmpl_str, _c_profile));
//        draw_profile_followers();
        draw_profile_notes();
    }

    function draw_profile_followers(){
        /*
            draws the follower of _cprofile in _feed_con
            followers must be loaded at this point, we use _profiles_lookup to lookup the keys we have
            and replace with the actual profile info - this assumes we have all profiles.
            if this were ever not possible change to set flag include_profile true and the backend will do
            and include in query
        */
        let following = [],
            tmpl_str = [
            '{{#follows}}',
                '<div id="follows-{{pub_k}}" style="border: 1px dashed white;cursor:pointer;">',
                '{{#attrs.picture}}',
                    '<span style="display: table-cell;">',
                         '<img src="{{attrs.picture}}" width="32" height="32" />',
                    '</span>',
                '{{/attrs.picture}}',
                '<span style="display: table-cell;word-break: break-all;vertical-align:top;">',
                    '<b>pub_key : </b>{{pub_k}}<br>',
                    '{{#attrs.name}}',
                        '<b>name :</b> {{attrs.name}}<br>',
                    '{{/attrs.name}}',
                    '{{#attrs.about}}',
                        '<b>about :</b> {{attrs.about}}<br>',
                    '{{/attrs.about}}',
                '</span>',
                '</div>',
            '{{/follows}}'
        ].join('');


        _c_profile.contacts.forEach(function(c_link){
            let profile = _profiles_lookup[c_link['pub_k_contact']];
            if(profile!==undefined){
                following.push(profile);
            }else{
                console.log('unlinked profile..'+ c_link['pub_k_contact'] +'. this shouldn\'t happen')
            }
        });
        if(following.length===0){
            _feed_con.html('follows no-one');
        }else{
            _feed_con.html(Mustache.render(tmpl_str, {
                'follows' : following
            }));
        }

    }

    function draw_profile_notes(){
        /*
        */
        let tmpl_str = [
            '{{#notes}}',
                '<div style="border: 1px dashed white;cursor:pointer;">',
                '{{content}}',
                '</div>',
            '{{/notes}}'
        ].join('');

        console.log(_c_profile);
        if(_c_profile.notes.length===0){
            _feed_con.html('hasn\'t commented yet');
        }else{
            _feed_con.html(Mustache.render(tmpl_str, {
                'notes' : _c_profile.notes
            }));
        }
    }


    function add_events(){
        function get_id(e){
            let el = e.target,
                ret = el.id;
            while(ret===''){

                el = el.parentNode;
                if(el===document){
                    break;
                }
                ret = el.id;
            }
            return ret
        }

        $(document).on('click', function(e){
            let id = get_id(e),
                profile;

            if(id){
                // so if from followers also pk
                id = id.replace('follows-','');
                profile = _profiles_lookup[id];
            }

            if(profile!==undefined){
                _c_profile = profile;
                // contacts yet to be loaded
                _profile_con.html('loading');
                _feed_con.html('loading');
                if(_c_profile.contacts===undefined){
                    APP.remote.load_profile_contacts(_c_profile['pub_k'], function(data){
                        let pub_k = data['pub_k_owner'];
                        // update the lookup
                        _profiles_lookup[pub_k]['contacts'] = data['contacts'];
                        // I think this should protect us from the profile being changed and loading before we get
                        // back with old data...
                        if(pub_k===_c_profile['pub_k']){
                            draw_selected_profile();
                        }
                    });

                    APP.remote.load_profile_notes(_c_profile['pub_k'], function(data){
                        let pub_k = data['pub_k_owner'];
                        // update the lookup
                        _profiles_lookup[pub_k]['notes'] = data['notes'];
                        // I think this should protect us from the profile being changed and loading before we get
                        // back with old data...
                        if(pub_k===_c_profile['pub_k']){
                            draw_selected_profile();
                        }
                    });

                }else{
                    draw_selected_profile();
                }

            }
        });

        _contact_search_in.on('keyup', function(){
            redraw_contacts();
        });

    }

    $(document).ready(function() {
        add_events();
        APP.remote.load_profiles(function(data){
            _profiles = data['profiles'];
            // create a lookup keyed on pub_k
            _profiles.forEach(function(p){
                _profiles_lookup[p['pub_k']] = p;
            });

            redraw_contacts();
        });
    });
}();