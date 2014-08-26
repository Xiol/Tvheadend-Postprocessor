Tvheadend Postprocess Scripts
=============================

Postprocessor scripts to transcode videos and then send email notifications to interested parties.

Requires ffmpeg, a working beanstalkd server and the Python packages ``beanstalkc`` and ``pyyaml``.

How I installed it:

.. code-block:: bash

    cd /opt
    git clone git@github.com:Xiol/Tvheadend-Postprocessor.git tvhpp
    cd tvhpp/
    virtualenv env
    source env/bin/activate
    pip install beanstalkc pyyaml
    cp tvhpp.conf.example /etc/tvhpp.conf
    vi /etc/tvhpp.conf
    # Edit as desired

    # I'm using supervisord to control this, so copy config and update
    cp supervisord/tvhqp.conf /etc/supervisord/conf.d
    supervisorctl update
    # Alternatively start it up using whatever method you want

    # Set your Tvheadend Postprocessor command to:
    /opt/tvhpp/env/bin/python /opt/tvhpp/tvheadend_postprocessor.py "%f" "%c" "%t" "%e"

License
-------

Public domain.
