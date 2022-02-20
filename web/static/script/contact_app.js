'using strict';
APP = {}

APP.remote = function(){
    // data
    let _profiles,
    // gui parts
        _profile_con = $('#contacts-con');


    function redraw_profiles(){
        let tmpl_str = [
            '{{#profiles}}',
                // if we have a name use that
                '<div>',
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

        _profile_con.html(Mustache.render(tmpl_str, _profiles));
    }

    return {
        'load_profiles' : function(){
            $.ajax({
                url: '/profiles'
            }).done(function(data) {
                _profiles = data;
                redraw_profiles();
            });
        }
    }
}();

!function(){
    $(document).ready(function() {
        APP.remote.load_profiles();
    });
}();