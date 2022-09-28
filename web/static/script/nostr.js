'use strict';
// TODO: nostr stuff will be moved out to be share

var _ = (id) => {
    let ret = typeof(id)==='string' ?
        document.querySelectorAll(id) :
        id,
        internal;

    if(ret!==null && ret.html===undefined){
        // so we can always use forEach
        internal = ret.length===undefined ? [ret] : ret;

        ret.html = (html) => {
            internal.forEach(function(el,i){
                el.innerHTML = html;
            });
        };

        ret.on = (type, func) => {
            let args = {};
            internal.forEach(function(el,i){
                if(type==='scroll'){
                    args.passive = true;
                }
                el.addEventListener(type, func, args);
            });
        };

        ret.scrollBottom = (func) => {
            internal.forEach(function(el,i){
                el.addEventListener('scroll', function(e){
                    let el = e.target,
                        max_y = el.scrollHeight,
                        // ceil fix for brave on mobile..
                        c_y = Math.ceil(el.scrollTop+el.offsetHeight);

                    if(max_y <= c_y){
                        func(e);
                    }
                });
            });
        }

        ret.scrollTop = (func) => {
            internal.forEach(function(el,i){
                el.addEventListener('scroll', function(e){
                    if(el.scrollTop===0){
                        func(e);
                    }
                });
            });
        }


        ret.css = (property, val) => {
            internal.forEach(function(el,i){
                el.style[property] = val;
            });
        };

        // stop recursion if called via given object e.g. document.body
        // that has insertAdjacentHTML method
        if(ret.insertAdjacentHTML===undefined){
            ret.insertAdjacentHTML = (where, value) => {
                internal.forEach(function(el,i){
                    el.insertAdjacentHTML(where, value);
                });
            }
        }

        // as insertAdjacentHTML
        if(ret.focus===undefined){
            ret.focus = () => {
                internal[0].focus();
            };
        }

        // and again
        if(ret.remove===undefined){
            ret.remove = () => {
                internal.forEach(function(el,i){
                    el.remove();
                });
            };
        }

        ret.val = (val) => {
            if(val===undefined){
                return internal[0].value;
            }
            internal.forEach(function(el,i){
                el.value = val;
            });
            return val;
        };

        ret.fadeIn = (callback, ms) => {
            internal.forEach(function(el,i){
                let my_callback = (el) => {
                    callback && callback(el);
                };
                _.fadeIn(el, my_callback, ms);
            });
        }

        ret.fadeOut = (callback, ms) => {
            internal.forEach(function(el,i){
                let my_callback = (el) => {
                    callback && callback(el);
                };
                _.fadeOut(el, my_callback, ms);
            });
        }

    };
    return ret;
};

//see https://stackoverflow.com/questions/11197247/javascript-equivalent-of-jquerys-extend-method
_.extend = (...args) => {
    for(var i=1; i<args.length; i++){
        for(var key in args[i]){
            if(args[i].hasOwnProperty(key)){
                args[0][key] = args[i][key];
            };
        };
    };
    return args[0];
};

// https://stackoverflow.com/questions/57173723/fade-in-without-jquery-fadein-css-transition-opacity-and-display
// fadeIn, fadeOut
// easy replace for jquery fades .. eventually use bootstrap anims?
_.fadeIn = (el, callback, ms) => {
  ms = ms || 400;
  const finishFadeIn = () => {
    el.removeEventListener('transitionend', finishFadeIn);
    callback && callback();
  };
  el.style.transition = 'opacity 0s';
  el.style.display = '';
  el.style.opacity = 0;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      el.addEventListener('transitionend', finishFadeIn);
      el.style.transition = `opacity ${ms/1000}s`;
      el.style.opacity = 1
    });
  });
};

_.fadeOut = (el, callback, ms) => {
  ms = ms || 400;
  const finishFadeOut = () => {
    el.style.display = 'none';
    el.removeEventListener('transitionend', finishFadeOut);
    callback && callback();
  };
  el.style.transition = 'opacity 0s';
  el.style.opacity = 1;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      el.style.transition = `opacity ${ms/1000}s`;
      el.addEventListener('transitionend', finishFadeOut);
      el.style.opacity = 0;
    });
  });
};


APP.nostr = {
    'data' : {},
    'util' : {
        'short_key': function (key){
            return key.substring(0, 3) + '...' + key.substring(key.length-4)
        },
        'html_escape': function (in_str, ignore){
            let _replacements = [
                [/\<script\>/g,'&ltscript&gt'],
                [/\<\/script>/g,'&lt/script&gt'],

            ];
            _replacements.forEach(function(c_rep,i){
                let val = c_rep[0],
                    rep = c_rep[1];
                if(ignore===undefined || ignore[val]===undefined){
                    in_str = in_str.replace(val, rep);
                }
            });
            return in_str;
        },


        // copied from https://stackoverflow.com/questions/17678694/replace-html-entities-e-g-8217-with-character-equivalents-when-parsing-an
        // for text that is going to be rendered into page as html
        // {{{}}} in Mustache templates
        'html_unescape' : function (str, escapeChars) {//modified from underscore.string and string.js
            escapeChars = escapeChars || { lt: '<', gt: '>', quot: '"', apos: "'", amp: '&' };

            return str.replace(/\&([^;]+);/g, function(entity, entityCode) {
                var match;if ( entityCode in escapeChars) {
                    return escapeChars[entityCode];
                } else if ( match = entityCode.match(/^#x([\da-fA-F]+)$/)) {
                    return String.fromCharCode(parseInt(match[1], 16));
                } else if ( match = entityCode.match(/^#(\d+)$/)) {
                    return String.fromCharCode(~~match[1]);
                } else {
                    return entity;
                }
            });
        },
        'http_matches' : function(txt){
            const http_regex = /(https?\:\/\/[\w\.\/\-\%\?\=\~\+\@\&\;\#\:,]*)(?=\s|$)|(\s|^)(\w+\.{1}){1,3}[a-zA-Z]{2,3}(?=\s|$)/g
            return txt.match(http_regex);
        },
        'copy_clipboard' : function copy_clipboard(value, success_text, fail_text){
            if(navigator.clipboard===undefined){
                // do some shit here to try and get access,
                // think that it won't be possible unless https
                navigator.permissions.query({name:'clipboard-write'}).then(function(r){
                    console.log(r)
                });

            }else{
                navigator.clipboard.writeText(value);
                if(success_text!==undefined){
                    APP.nostr.gui.notification({
                        'text' : success_text
                    });
                }

            }
        }
    }
};

// for relative times of notes from now
dayjs.extend(window.dayjs_plugin_relativeTime);
// so we can shorten the time formats
dayjs.extend(window.dayjs_plugin_updateLocale);

dayjs.updateLocale('en', {
  relativeTime: {
    // relative time format strings, keep %s %d as the same
    future: 'in %s', // e.g. in 2 hours, %s been replaced with 2hours
    past: '%s',
    s: 'now',
    m: '1m',
    mm: '%dm',
    h: '1h',
    hh: '%dh', // e.g. 2 hours, %d been replaced with 2
    d: '1d',
    dd: '%dd',
    M: '1mth',
    MM: '%dmth',
    y: '1y',
    yy: '%dy'
  }
});
