'using strict';
APP = {}

APP.remote = function(){
    let _profiles;


    return {
        'load_profiles' : function(){
            $.ajax({
                url: '/profiles'
            }).done(function(data) {
                alert('wtf')
                console.log(data);
            });


        }
    }
}();

!function(){
    $(document).ready(function() {
        APP.remote.load_profiles();
    });
}();