// TODO: nostr stuff will be moved out to be share
APP.nostr = {
    'data' : {},
    'util' : {
        'short_key': function (key){
            return key.substring(0, 3) + '...' + key.substring(key.length-4)
        },
        // probably we should use a lib
        'html_escape': function (in_str, ignore){
            let _replacements = [
                [/\&/g,'&amp'],
                [/\</g,'&lt;'],
                [/\>/g,'&gt;'],
                [/\\"/g,'&quot;'],
                [/\\'/g,'&#39;']
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
        'html_unescape' : function (str) {//modified from underscore.string and string.js
//            var escapeChars = { lt: '<', gt: '>', quot: '"', apos: "'", amp: '&' };
            // reduced to just &n; style replacements, will need to come back and think about this properly
            var escapeChars = {amp: '&' };
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
            const http_regex = /(https?\:\/\/[\w\.\/\-\%\?\=\~\+\@\&\;\#\:,]*)|(\s|^)(\w*\.){1,3}\w{2,3}(?=\s|$)/g
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
