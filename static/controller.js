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
                .addClass("btn btn-primary")
                .click(function () {
                    writeNFC(f.hash);
                })
                .html('<span class="glyphicon glyphicon-save" aria-hidden="true"></span> Write')
                .appendTo(li);
        });

        $("#musicFiles").html(ul);
    });
}


function writeNFC(data) {
    $.getJSON('actions/writenfc?data=' + data, function (ret) {
        setStatus(ret.message);
    });
}


function setStatus(status) {
    var statusBox = $('#statusBox');

    statusBox.empty();

    $('<p/>')
        .text('Status: ' + status)
        .appendTo(statusBox);
}


function pollNFC() {
    $.getJSON('json/readnfc', function (data) {

        var nfcStatus = $('#nfcStatusBox');

        nfcStatus.empty();

        $('<p/>')
            .text('NFC Tag Status: ' + data['description'] + ' (UID: ' + data['uid'] + ', data: ' + data['data'] + ')')
            .appendTo(nfcStatus);

        // poll again in 1 sec
        setTimeout(pollNFC, 1000);
    });
}

function initialize() {
    refreshMusicFiles();
    setStatus("Ready!");
    pollNFC();
}
