#!/usr/bin/env python
import beanstalkc
import json
import os
import sys
from syslog import syslog

if len(sys.argv) != 5:
    print "Missing arguments."
    print "Usage: tvheadend_postprocess.py {path} {channel} {title} {status}"
    print 'Your postprocessor command in tvheadend should be: /path/to/tvheadend_postprocess.py "%f" "%c" "%t" "%e"'
    sys.exit(1)

videoinfo = dict(path=sys.argv[1], fname=os.path.basename(sys.argv[1]), channel=sys.argv[2],
                 title=sys.argv[3], status=sys.argv[4])

try:
    bs = beanstalkc.Connection()
    bs.use('transcoding')
except (beanstalkc.BeanstalkcException, beanstalkc.SocketError) as e:
    syslog("Error connecting to beanstalkd: {}".format(e.message))
except:
    syslog("Unknown error with beanstalkd")

bs.put(json.dumps(videoinfo), ttr=14400)

if videoinfo['status'] == 'OK':
    syslog("Queued postprocess for file: {}".format(videoinfo['fname']))
else:
    syslog("Error '{}' for recording: {}. Queuing notification.".format(videoinfo['status'], videoinfo['fname']))
