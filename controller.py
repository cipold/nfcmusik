import argparse
import datetime
import logging
import subprocess
import time
from multiprocessing import Process, Lock, Manager
from os import path

import pygame

import RFID
import settings
import util
import web

"""

Main controller, runs in an infinite loop. 

Reads and acts on NFC codes, supplies web interface for tag management.
Web interface is at http://<raspi IP or host name>:5000

Autostart: 'crontab -e', then add line
@reboot cd <project directory> && python3 -u controller.py 2>&1 >> /home/pi/tmp/nfcmusik.log.txt &

"""

logger = logging.getLogger(__name__)


class RFIDHandler(object):
    """
    RFID handler
    """

    def __init__(self):
        # flag to stop polling
        self.do_stop = False

        # mutex for RFID access
        self.mutex = Lock()

        # manager for interprocess data sharing (polling process writes uid/data)
        self.manager = Manager()

        # current tag uid
        self.uid = self.manager.list(range(5))

        # current tag data - 16 bytes
        self.data = self.manager.list(range(16))

        # music files dictionary
        self.music_files_dict = self.manager.dict()

        # startup time or last server interaction
        self.startup = datetime.datetime.now()

        # flag for inter-process communication: reset the startup time
        self.reset_startup = self.manager.Value('c', 0)
        self.reset_startup.value = 0

        # have we shut off WiFi already?
        self.is_wlan_off = False

        # NFC memory page to use for reading/writing
        self.page = 10

        # polling cycle time (seconds)
        self.sleep = 0.5

        # music playing status
        self.current_music = None

        # last played music file
        self.previous_music = None

        # must have seen stop signal N times to stop music - avoid
        # stopping if signal drops out briefly
        self.stop_music_on_stop_count = 3

        # to replay same music file, must have seen at least N periods
        # of no token - avoid replaying if token is left on device
        # but signal drops out briefly
        self.replay_on_stop_count = 3

        # stop signal counter
        self.stop_count = 0

    def poll_loop(self):
        """
        Poll for presence of tag, read data, until stop() is called.
        """

        # initialize music mixer
        pygame.mixer.init()

        # set default volume
        util.set_volume(settings.DEFAULT_VOLUME)

        while not self.do_stop:
            with self.mutex:

                # initialize tag state
                self.uid[0] = None
                self.data[0] = None

                # always create a new RFID interface instance, to clear any errors from
                # previous operations
                rdr = RFID.RFID()

                # check for presence of tag
                err, _ = rdr.request()

                if not err:
                    logger.debug("RFIDHandler poll_loop: Tag is present")

                    # tag is present, get UID
                    err, uid = rdr.anticoll()

                    if not err:
                        logger.debug("RFIDHandler poll_loop: Read UID: " + str(uid))

                        # read data
                        err, data = rdr.read(self.page)

                        if not err:
                            logger.debug("RFIDHandler poll_loop: Read tag data: " + str(data))

                            # all good, store data to shared mem
                            for i in range(5):
                                self.uid[i] = uid[i]
                            for i in range(16):
                                self.data[i] = data[i]

                        else:
                            logger.error("RFIDHandler poll_loop: Error returned from read()")

                    else:
                        logger.error("RFIDHandler poll_loop: Error returned from anticoll()")

                # clean up
                rdr.cleanup()

                # act on data
                self.action()

            # wait a bit (this is in while loop, NOT in mutex env)
            time.sleep(self.sleep)

    def write(self, data):
        """
        Write a 16-byte string of data to the tag
        """

        if len(data) != 16:
            logger.warning("Illegal data length, expected 16, got " + str(len(data)))
            return False

        with self.mutex:

            rdr = RFID.RFID()

            success = False

            # check for presence of tag
            err, _ = rdr.request()

            if not err:
                logger.debug("RFIDHandler write: Tag is present")

                # tag is present, get UID
                err, uid = rdr.anticoll()

                if not err:
                    logger.debug("RFIDHandler write: Read UID: " + str(uid))

                    # write data: RFID lib writes 16 bytes at a time, but for NTAG213
                    # only the first four are actually written
                    err = False
                    for i in range(4):
                        page = self.page + i
                        page_data = [c for c in data[4 * i: 4 * i + 4]] + [0] * 12

                        # read data once (necessary for successful writing?)
                        err_read, _ = rdr.read(page)

                        if err:
                            logger.error("Error signaled on reading page {:d} before writing".format(page))

                        # write data
                        err |= rdr.write(page, page_data)

                        if err:
                            logger.error(
                                "Error signaled on writing page {:d} with data {:s}".format(page, str(page_data)))

                    if not err:
                        logger.info("RFIDHandler write: successfully wrote tag data")

                        success = True

                    else:
                        logger.error("RFIDHandler write: Error returned from write()")

                else:
                    logger.error("RFIDHandler write: Error returned from anticoll()")

            # clean up
            rdr.cleanup()

            return success

    def get_data(self):
        """
        Get current tag data as binary string
        """
        with self.mutex:
            data = list(self.data)
        if data[0] is not None:
            return bytes(data)
        else:
            return None

    def get_uid(self):
        """
        Get current tag UID
        """
        with self.mutex:
            uid = list(self.uid)
        if uid[0] is not None:
            return bytes(uid)
        else:
            return None

    def set_music_files_dict(self, mfd):
        """
        Set dictionary of file hashes and music files
        """
        with self.mutex:
            for k, v in mfd.items():
                self.music_files_dict[k] = v

    def reset_startup_timer(self):
        """
        Set flag to reset the startup timer
        """
        self.reset_startup.value = 1

    def stop_polling(self):
        """
        Stop polling loop
        """
        self.do_stop = True

    def action(self):
        """
        Act on NFC data - call this from within a mutex lock
        """

        # check if we should reset the startup time
        if self.reset_startup.value > 0:
            self.reset_startup.value = 0
            self.startup = datetime.datetime.now()

        # if enough time has elapsed, shut off the WiFi interface
        delta = (datetime.datetime.now() - self.startup).total_seconds()
        if delta > settings.WLAN_OFF_DELAY and not self.is_wlan_off:
            logger.info("Shutting down WiFi")
            self.is_wlan_off = True
            subprocess.call(['sudo', 'ifdown', 'wlan0'])

        if int(delta) % 10 == 0 and not self.is_wlan_off:
            logger.debug("Shutting down WiFi in (seconds): %.1f" % (settings.WLAN_OFF_DELAY - delta))

        # check if we have valid data
        if self.data[0] is not None:
            bin_data = bytes(self.data)

            if bin_data[0:1] == settings.CONTROL_BYTES['MUSIC_FILE']:

                if bin_data in self.music_files_dict:
                    file_name = self.music_files_dict[bin_data]
                    file_path = path.join(settings.MUSIC_ROOT, file_name)

                    if file_name != self.current_music:

                        # only replay same music file if we saw at least N periods
                        # of no token
                        if path.exists(file_path) and (
                                file_name != self.previous_music or self.stop_count >= self.replay_on_stop_count):
                            logger.info("RFIDHandler action: Playing music file " + file_path)

                            # play music file
                            self.current_music = file_name
                            self.previous_music = file_name
                            pygame.mixer.music.load(file_path)
                            pygame.mixer.music.play()

                        else:
                            if not path.exists(file_path):
                                logger.error("RFIDHandler action: File not found " + file_path)

                    # token seen - reset stop counter
                    self.stop_count = 0

                else:
                    logger.warning("RFIDHandler: got music file control byte but unknown file hash")
            else:
                logger.warning("RFIDHandler action: Unknown control byte")
        else:
            self.stop_count += 1

            logger.debug("Resetting action status, stop count " + str(self.stop_count))

            # only stop after token absence for at least N times
            if self.stop_count >= self.stop_music_on_stop_count:
                self.current_music = None

                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()


def main(args):
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    # RFID handler instance
    rfid_handler = RFIDHandler()

    # start RFID handling process
    rfid_polling_process = Process(target=rfid_handler.poll_loop)
    rfid_polling_process.start()

    web.run_server(rfid_handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='NFC Music Box Controller')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose logging')

    main(parser.parse_args())
