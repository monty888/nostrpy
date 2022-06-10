APP.nostr.data.event = function(){
    let _listener = {};

    return {
        'add_listener' : function(for_type, listener){
            if(_listener[for_type]===undefined){
                _listener[for_type] = [];
            }
            _listener[for_type].push(listener);
        },
        'remove_listener' : function(for_type, listener){
            if(_listener[for_type]!==undefined){
                let lists = _listener[for_type];
                for(let i=0;i<lists.length;i++){
                    if(lists[i]===listener){
                        lists.splice(i,1);
                        break;
                    }
                }

            }
        },
        'fire_event' : function(of_type, data){
            if(_listener[of_type]!==undefined){
                _listener[of_type].forEach(function(c_list){
                    try{
                        c_list(of_type,data);
                    }catch(e){
                        console.log(e)
                    }
                });
            }

        }
    }
}();

APP.nostr.data.user = function(){
    let _current_profile;
    return {
        'get_profile' : function(){
            if(_current_profile===undefined){
                _current_profile = APP.nostr.data.state.current_user;
            }
            return _current_profile;
        },
        'set_profile' : function(key,callback){
            APP.remote.set_profile({
                'key' : key,
                'success' : function(data){
                    _current_profile = data;
                    if(typeof(callback)==='function'){
                        return data;
                    }
                    APP.nostr.data.event.fire_event('profile_set', data);
                }
            });
        }
    };
}();