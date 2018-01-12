import binascii
import glob
import hashlib
import json
import logging
import os

from flask import Flask, render_template, request, redirect, flash
from werkzeug.utils import secure_filename

import settings

logger = logging.getLogger(__name__)
app = Flask(__name__)

# global dictionary of music file hashes and names
music_files_dict = dict()

# RFID handler instance
rfid_handler = None


def music_file_hash(file_name):
    """
    Get hash of music file name, replace first byte with a control byte for music playing.
    """
    m = hashlib.md5()
    m.update(file_name.encode())
    return settings.CONTROL_BYTES['MUSIC_FILE'] + m.digest()[1:]


@app.route('/json/musicfiles')
def music_files():
    """
    Get a list of music files and file identifier hashes as JSON; also refresh
    internal cache of music files and hashes.
    """
    global music_files_dict

    file_paths = sorted(glob.glob(os.path.join(settings.MUSIC_ROOT, '*')))

    out = []
    music_files_dict = dict()
    for file_path in file_paths:
        file_name = os.path.split(file_path)[1]

        _, file_extension = os.path.splitext(file_name)
        if file_extension in settings.ALLOWED_EXTENSIONS:
            file_hash = music_file_hash(file_name)
            out.append(dict(name=file_name,
                            hash=binascii.b2a_hex(file_hash).decode()))
            music_files_dict[file_hash] = file_name

    # set music files dict in RFID handler
    if rfid_handler:
        rfid_handler.set_music_files_dict(music_files_dict)

    return json.dumps(out)


@app.route('/json/readnfc')
def read_nfc():
    """
    Get current status of NFC tag
    """
    if not rfid_handler:
        return json.dumps(dict(uid=None, data=None, description='No RFID handler'))

    global music_files_dict

    # get current NFC uid and data

    uid = rfid_handler.get_uid()
    if uid is None:
        hex_uid = 'none'
    else:
        hex_uid = binascii.b2a_hex(uid).decode()

    data = rfid_handler.get_data()
    if data is None:
        hex_data = 'none'
        description = 'No tag present'
    else:
        hex_data = binascii.b2a_hex(data).decode()

        description = 'Unknown control byte or tag empty'
        if data[0:1] == settings.CONTROL_BYTES['MUSIC_FILE']:
            if data in music_files_dict:
                description = 'Play music file ' + music_files_dict[data]
            else:
                description = 'Play a music file not currently present on the device'

    # output container
    out = dict(uid=hex_uid, data=hex_data, description=description)

    return json.dumps(out)


@app.route('/json/wlantimeout')
def wlan_timeout():
    """
    Get time left until WLAN is turned off
    """
    return json.dumps(dict(
        timeout=rfid_handler.get_wlan_time_left() if rfid_handler else 0
    ))


@app.route('/actions/writenfc')
def write_nfc():
    """
    Write data to NFC tag

    Data is contained in get argument 'data'.
    """
    if not rfid_handler:
        return json.dumps(dict(
            success=False, message='No RFID handler'
        ))

    # acquire data in hex format
    hex_data = request.args.get('data')
    if hex_data is None:
        return json.dumps(dict(
            success=False, message='No data argument given for writenfc endpoint'
        ))

    # convert from hex to bytes
    data = binascii.a2b_hex(hex_data)

    if data[0:1] != settings.CONTROL_BYTES['MUSIC_FILE']:
        return json.dumps(dict(
            success=False, message='Unknown control byte: ' + binascii.b2a_hex(data[0:1])
        ))

    if data not in music_files_dict:
        return json.dumps(dict(
            success=False, message='Unknown hash value!'
        ))

    # write tag
    if not rfid_handler.write(data):
        return json.dumps(dict(
            success=False, message='Error writing NFC tag data ' + hex_data
        ))

    file_name = music_files_dict[data]
    return json.dumps(dict(
        success=True, message='Successfully wrote NFC tag for file: ' + file_name
    ))


@app.route('/actions/deletefile')
def delete_file():
    """
    Delete file

    Data is contained in get argument 'data'.
    """
    # acquire data in hex format
    hex_data = request.args.get('data')
    if hex_data is None:
        return json.dumps(dict(
            success=False, message='No data argument given for deletefile endpoint'
        ))

    # convert from hex to bytes
    data = binascii.a2b_hex(hex_data)

    if data not in music_files_dict:
        return json.dumps(dict(success=False, message='Unknown hash value!'))

    file_name = music_files_dict[data]

    try:
        os.remove(os.path.join(settings.MUSIC_ROOT, file_name))
    except OSError as e:
        return json.dumps(dict(success=False, message='Could not delete file: %s' % e))

    return json.dumps(dict(success=True, message='The file "%s" was deleted' % file_name))


def handle_file_upload(files):
    if 'file' not in files:
        flash('No file uploaded', 'danger')
        return

    file = files['file']
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return

    _, file_extension = os.path.splitext(file.filename)
    if file_extension in settings.ALLOWED_EXTENSIONS:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File "%s" uploaded' % filename, 'success')
    else:
        flash('Invalid file type', 'danger')


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        handle_file_upload(request.files)
        return redirect(request.url)

    # reset wlan shutdown counter when loading page
    if rfid_handler:
        rfid_handler.reset_startup_timer()

    return render_template('home.html')


def run_server(rfid_handler_param):
    global rfid_handler
    rfid_handler = rfid_handler_param

    # initialize music files dict
    music_files()

    app.secret_key = settings.SERVER_SECRET
    app.config['UPLOAD_FOLDER'] = settings.MUSIC_ROOT
    app.run(host=settings.SERVER_HOST_MASK, threaded=True)


if __name__ == '__main__':
    run_server(None)
