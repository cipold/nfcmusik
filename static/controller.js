// reload list of music files and render it
function refreshMusicFiles() {
    $.getJSON('json/musicfiles', function (data) {
        var ul = $('<ul/>')
            .addClass('list-group');

        $.each(data, function (i, f) {
            var li = $('<li/>')
                .attr('id', f.hash)
                .addClass('music-file')
                .addClass('list-group-item clearfix')
                .html('<span class="glyphicon glyphicon-music" aria-hidden="true"></span> ' + f.name + '<br>')
                .appendTo(ul);


            $('<button/>')
                .attr('type', 'button')
                .addClass('btn btn-primary')
                .click(function () {
                    writeNFC(f.hash);
                })
                .html('<span class="glyphicon glyphicon-save" aria-hidden="true"></span> Write')
                .appendTo(li);

            $('<button/>')
                .attr('type', 'button')
                .addClass("btn btn-danger")
                .click(function () {
                    deleteFile(f.name, f.hash);
                })
                .html('<span class="glyphicon glyphicon-remove" aria-hidden="true"></span> Delete')
                .appendTo(li);
        });

        $('#musicFiles').html(ul);
    });
}


function writeNFC(data) {
    $.getJSON('actions/writenfc?data=' + data, function (ret) {
        var icon = $('#' + data + ' > .btn > .glyphicon').first();
        var btn = $('#' + data + ' > .btn').first();

        if (ret.success) {
            // tag successfully written - give simple feedback to user as the music is about to start playing anyway
            icon.removeClass('glyphicon-save');
            icon.addClass('glyphicon-ok');
            btn.removeClass('btn-primary');
            btn.addClass('btn-success');

            setTimeout(function () {
                icon.removeClass('glyphicon-ok');
                icon.addClass('glyphicon-save');
                btn.removeClass('btn-success');
                btn.addClass('btn-primary');
            }, 3000);

            console.info(ret.message);
        } else {
            // there was an issue writing the tag - provide status message to user
            icon.removeClass('glyphicon-save');
            icon.addClass('glyphicon-exclamation-sign');
            btn.removeClass('btn-primary');
            btn.addClass('btn-danger');

            setTimeout(function () {
                icon.removeClass('glyphicon-exclamation-sign');
                icon.addClass('glyphicon-save');
                btn.removeClass('btn-danger');
                btn.addClass('btn-primary');
            }, 3000);

            $('#modal-text').text(ret.message);
            $('#modal-dialog').modal('show');
            console.error(ret.message);
        }
    });
}

function deleteFile(name, data) {
    if (confirm('Do you really want to delete "' + name + '"?')) {
        $.getJSON('actions/deletefile?data=' + data, function (ret) {
            if (ret.success) {
                // the file was successfully deleted - refresh the file list
                refreshMusicFiles();
                console.info(ret.message);
            } else {
                // there was an issue deleting the file - provide status message to user
                var icon = $('#' + data + ' > .btn > .glyphicon').first();
                var btn = $('#' + data + ' > .btn').first();

                icon.removeClass('glyphicon-save');
                icon.addClass('glyphicon-exclamation-sign');
                btn.removeClass('btn-primary');
                btn.addClass('btn-danger');

                setTimeout(function () {
                    icon.removeClass('glyphicon-exclamation-sign');
                    icon.addClass('glyphicon-save');
                    btn.removeClass('btn-danger');
                    btn.addClass('btn-primary');
                }, 3000);

                $('#modal-text').text(ret.message);
                $('#modal-dialog').modal('show');
                console.error(ret.message);
            }
        });
    }
}

function pollNFC() {
    $.getJSON('json/readnfc', function (data) {
        $('#nfcStatusBox').html('<span title="UID: ' + data['uid'] + ', data: ' + data['data'] + '">' + data['description'] + '</span>');
    });
}

function pollWlanTimeout() {
    $.getJSON('json/wlantimeout', function (data) {
        var timeout = data['timeout'];
        $('#wlanTimeout').text(timeout);
        if (timeout > 0) {
            $('#wlanStatusAlert').show();
        }
    });
}

function initialize() {
    // fill music file list
    refreshMusicFiles();

    // start polling nfc
    pollNFC();
    setInterval(pollNFC, 1000);

    // start polling WLAN timeout
    pollWlanTimeout();
    setInterval(pollWlanTimeout, 1000);
}
