# installer for the wxWmr500 driver
#
# Based on installer for bootstrap skin
#
# Configured by Bill to install weewxMQTT user driver, 2016.

import os.path
import configobj

import setup
import distutils

def loader():
    return wxWmr500Installer()

class wxWmr500Installer(setup.ExtensionInstaller):
    _driver_conf_files = ['weewx.conf']

    def __init__(self):
        super(wxWmr500Installer, self).__init__(
            version="0.2",
            name='wxWmr500',
            description='A weewx driver which subscribes to MQTT topics providing weewx compatible data',
            author="Tim Sneddon",
            author_email="tim@sneddon.id.au",
            config={
                'wxWmr500': {
                    driver = user.wxMesh
                    host = localhost           # MQTT broker hostname
                    poll_interval = 1
                 }

            files=[('bin/users/wxWmr500'])]
            )

        print ""
        print "The following alternative languages are available:"
        self.language = None

    def merge_config_options(self):

        fn = os.path.join(self.layout['CONFIG_ROOT'], 'weewx.conf')
        config = configobj.ConfigObj(fn)
