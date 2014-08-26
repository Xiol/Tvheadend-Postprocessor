#!/usr/bin/env python
import os
import beanstalkc
import re
import smtplib
import subprocess
import shutil
import textwrap
import json
import uuid
import argparse
import yaml
from syslog import syslog
from email.mime.text import MIMEText


class EmailNotifier:
    def __init__(self, notify_list, default, email_from):
        """
        :param notify_list: dict of [str, list]
        """
        self.notify_list = notify_list
        self.email_from = email_from
        self.default = default

    def send_notification(self, video, tc_done):
        """
        :param video: Media
        :param tc_done: bool
        :return: bool
        """
        matched = False
        for email, ntflist in self.notify_list.items():
            for title in ntflist:
                if re.search(title, video.title, re.I):
                    matched = True
                    self._notify(email, video, tc_done)

        if not matched:
            self._notify(self.default, video, tc_done)

    def _notify(self, email, video, tc_done):
        """
        :param email: str
        :param video: Media
        :param tc_done: bool
        :return: bool
        """
        msg = ""
        subject = ""
        if video.status.upper() == "OK":
            if tc_done:
                msg = textwrap.dedent("""A new recording is available:

                Title: {}
                Channel: {}
                Filename: {}
                Full Path: {}
                """.format(video.title, video.channel, video.fname, video.tc_path))
                subject = "New Recording: {}".format(video.title)
            else:
                msg = textwrap.dedent("""A failure occurred trying to transcode the video. See system logs.

                Title: {}
                Channel: {}
                Path: {}
                """.format(video.title, video.channel, video.path))
                subject = "Transcode Failure: {}".format(video.title)
        else:
            msg = textwrap.dedent("""Error recording program:

            Title: {}
            Channel: {}
            Error: {}
            """.format(video.title, video.channel, video.status))
            subject = "Recording Error: {}".format(video.title)

        message = MIMEText(msg)
        message['Subject'] = subject
        message['To'] = email
        message['From'] = self.email_from

        s = smtplib.SMTP('localhost')
        s.sendmail(self.email_from, email, message.as_string())
        s.quit()
        syslog("Email sent to '{}' for programme '{}'".format(email, video.title))
        return True


class Media:
    def __init__(self, path, fname, channel, title, status,
                 notifier, transcode_settings=None, video_types=None,
                 audio_types=None, keep=False):
        """
        :param path: str
        :param fname: str
        :param channel: str
        :param title: str
        :param status: str
        :param notifier: EmailNotifier
        :param transcode_settings: dict of [str, dict]
        :return:
        """
        self.path = path
        self.fname = fname
        self.fname_base = os.path.splitext(fname)[0]
        self.channel = channel
        self.title = title
        self.status = status
        self.keep = keep
        self.tc_fname = None
        self.tc_path = None
        self.tc_success = False
        self.is_rename = False
        self.type = None
        self.notifier = notifier
        # self.probe_results = None
        # input types
        self.video_types = video_types
        if self.video_types is None:
            self.video_types = ['.mkv', '.ts']
        self.audio_types = audio_types
        if self.audio_types is None:
            self.audio_types = ['.mka']
        self.transcode_settings = transcode_settings
        if self.transcode_settings is None:
            self.transcode_settings = {
                'audio': "-c:a libmp3lame -q:a 3",
                'video': "-c:v libx264 -preset veryfast -crf 21 -c:a ac3 -b:a 192 -sn"
            }

    def determine_type(self):
        if self.type is None:
            if os.path.splitext(self.fname)[1] in self.audio_types:
                self.type = 'audio'
            elif os.path.splitext(self.fname)[1] in self.video_types:
                self.type = 'video'
            else:
                raise ValueError("Input type not supported.")
        return self.type

        # def probe(self):

    #        try:
    #            out = subprocess.check_output(['ffprobe','-v','quiet','-print_format','json','-show_streams',self.path], stderr=subprocess.STDOUT)
    #            self.probe_results = json.loads(out)
    #        except subprocess.CalledProcessError as e:
    #            syslog('ffprobe error, aborting. Exit code {}'.format(e.returncode))
    #            sys.exit(1)
    #        except ValueError as e:
    #            syslog('ffprobe error, unable to load JSON results')
    #            sys.exit(1)
    #        except (KeyError, IndexError) as e:
    #            syslog('ffprobe error, JSON output missing expected fields')
    #            sys.exit(1)

    def do_rename(self):
        if self.is_rename and not self.keep:
            try:
                shutil.move(self.tc_path, self.path)
            except OSError as e:
                syslog("Unable to move converted file, error: {}".format(e.message))

    def do_cleanup(self):
        if not self.is_rename and self.type == 'audio' and not self.keep:
            try:
                os.unlink(self.path)
            except OSError as e:
                syslog("Unable to remove original file, error: {}".format(e.message))

    def set_tc_fname(self):
        if self.tc_fname is None:
            if self.determine_type() == 'video':
                self.tc_fname = '{}.mkv'.format(uuid.uuid4())
                self.is_rename = True
            else:
                self.tc_fname = '{}.mp3'.format(self.fname_base)
            self.tc_path = os.path.join(os.path.split(self.path)[0], self.tc_fname)

        return self.tc_fname

    def transcode(self):
        if not self.status == 'OK':
            self.notify()
            return

        self.determine_type()
        self.set_tc_fname()

        syslog("Starting transcode for {}".format(self.path))

        args = ['ffmpeg', '-i', self.path]
        args.extend(self.transcode_settings[self.type].split())
        args.append('-y')
        args.append(self.tc_path)

        try:
            out = subprocess.check_output(args, stderr=subprocess.STDOUT)
            self.tc_success = True
        except subprocess.CalledProcessError as e:
            with open(self.fname_base + '.tc_err', 'w') as fh:
                fh.write("Return code: {}\n\n".format(e.returncode))
                fh.write(e.output)
            try:
                os.unlink(self.tc_path)
            except OSError:
                syslog("Unable to remove failed converted file {}".format(self.tc_path))

        if self.tc_success:
            self.do_rename()
            self.do_cleanup()

        self.notify()

    def notify(self):
        self.notifier.send_notification(self, self.tc_success)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Tvheadend Transcode Script")
    parser.add_argument('--config', '-c', help="Path to configuration file, default /etc/tvhpp.conf",
                        default="/etc/tvhpp.conf")
    parser.add_argument('--keep', '-k', help="Do not remove original files after transcoding", action='store_true',
                        default=False)

    options = parser.parse_args()

    with open(options.config, 'r') as fh:
        config = yaml.load(fh.read())

    notifier = EmailNotifier(config['notify_list'], config['default_notify'], config['from_addr'])

    beanstalk = beanstalkc.Connection()
    beanstalk.watch('transcoding')
    beanstalk.ignore('default')

    while True:
        job = beanstalk.reserve()
        media_info = json.loads(job.body)
        job.delete()
        media = Media(notifier=notifier, keep=options.keep, transcode_settings=config['transcode_settings'],
                      **media_info)
        media.transcode()
