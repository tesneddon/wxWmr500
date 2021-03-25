#!/usr/bin/python
#
# weewx driver that reads data from MQTT subscription for Python 3 and Weewx 4.x
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.
#
# See http://www.gnu.org/licenses/

#
# The units must be weewx.US:
#   degree_F, inHg, inch, inch_per_hour, mile_per_hour
#
# To use this driver, put this file in the weewx user directory, then make
# the following changes to weewx.conf:
#
# [Station]
#     station_type = wxWmr500
#
# [wxWmr500]
#     host = <mqtt-broker> (default to mqtt.idtlive.com)
#     devid = <device-id>
#     appid = <app-id>
#     driver = user.wxWmr500
#
from __future__ import with_statement
from decimal import *
import json
import platform
import queue
import syslog
import time
import paho.mqtt.client as mqtt
import weewx.drivers

DRIVER_VERSION = "0.1"

def logmsg(dst, msg):
    syslog.syslog(dst, 'wxWmr500: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)

def _get_as_float(d, s):
    v = None
    if s in d:
        try:
            v = float(d[s])
        except ValueError as e:
            logerr("cannot read value for '%s': %s" % (s, e))
    return v

def f2c(f):
    return (f - 32) * (5 / 9)

def loader(config_dict, engine):
    return wxWmr500(**config_dict['wxWmr500'])

class wxWmr500(weewx.drivers.AbstractDevice):
    """weewx driver that reads MQTT data for Oregon Scientific WMR500"""

    def __init__(self, **stn_dict):
        # where to find the data file
        self.host = stn_dict.get('host', 'localhost')
        self.devid = stn_dict.get('devid', 'no default')
        self.appid = stn_dict.get('appid', 'no default')
        self.client_id = stn_dict.get('client_id', platform.node())

        # how often to poll the weather data file, seconds
        self.poll_interval = float(stn_dict.get('poll_interval', 5.0))

        loginf("MQTT host is %s" % self.host)
        loginf("MQTT data topic is enno/in/json")
        loginf("MQTT command topic is enno/out/json/%s" % self.devid)
        loginf("MQTT client is %s" % self.client_id)
        loginf("polling interval is %s" % self.poll_interval)

        self.rain_mm = Decimal('-1')

        self.payload = queue.Queue()
        self.connected = False

        self.client = mqtt.Client(client_id="wxWmr500", clean_session=True,
                                  userdata=None, protocol=mqtt.MQTTv311, transport="tcp")

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # TODO - need some reconnect on disconnect logic
        #self.client.on_disconnect = self.on_disconnect

        self.client.connect(self.host, 1883, 60)
        self.client.loop_start()

    # The callback for when the client rEceives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        loginf("Connected on mqtt server with result code "+str(rc))
        if rc == 0:
            self.connected = True
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        self.client.subscribe('enno/in/json')


    # The callback for when a PUBLISH message is received from the MQTT server.
    def on_message(self, client, userdata, msg):
        msg.payload = msg.payload.decode('UTF-8')
        self.payload.put(msg.payload, block=True, timeout=None)

        logdbg("Added to queue of %d message %s" % (self.payload.qsize(), msg.payload))

    def closePort(self):
        self.client.disconnect()
        self.client.loop_stop()

    def genLoopPackets(self):
        while True:
            try:
                msg = self.payload.get(block=True, timeout=self.poll_interval)

                logdbg('Queue of %d entries' % (self.payload.qsize() + 1))

                while msg:
                    # Translate the JSON packet to a Python dictionary
                    try:
                        data = json.loads(msg)

                        for i in data['data'].keys():
                            # Message types are:
                            #
                            # 1 == Automatic, periodic getChannel1Status response
                            # 2 == Response to getInfo command
                            # 4 == Response to getSettingStatus command
                            # 5 == Response to setSettings command
                            # 6 == Response to getChannel1Status
                            # 7 == Response to getChannel2Status
                            if (i != '1') and (i != '6'):
                                continue

                            indoor = data['data'][i]['indoor']
                            outdoor = data['data'][i]['outdoor']['channel1']

                            packet = {'dateTime': time.time(),
                                      'usUnits': weewx.METRICWX,

                                      'pressure': outdoor['w5']['c53'],

                                      # Wind direction is a multiple of 18 degrees.  There
                                      # does not appear to be a way to get more accurate a
                                      # reading as it is reported in such a way as the
                                      # display shows wind direction using a circle with
                                      # 18 segments,
                                      'windSpeed': outdoor['w2']['c21'],
                                      'windDir': outdoor['w2']['c23'] * 18,
                                      'windGust': outdoor['w2']['c29'],
                                      'windGustDir': outdoor['w2']['c24'] * 18,

                                      'rain': 0,

                                      'dewpoint': f2c(outdoor['w3']['c313']),
                                      'inTemp': f2c(indoor['w9']['c93']),
                                      'outTemp': f2c(outdoor['w3']['c31']),

                                      'inHumidity': indoor['w9']['c96'],
                                      'outHumidity': outdoor['w3']['c35']
                                    }

                            rain_mm = Decimal(outdoor['w4']['c41'])

                            if self.rain_mm != Decimal('-1') and rain_mm > self.rain_mm:
                                #logmsg('rain_mm = ' + str(rain_mm) + ';self.rain_mm = ' + str(self.rain_mm))
                                packet['rain'] = float(rain_mm - self.rain_mm)

                            self.rain_mm = rain_mm

                            yield packet
                    except JSONDecodeError as e:
                        print("Error decoding MQTT packet: ", err)
                        pass

                    if self.payload.empty():
                        msg = None
                    else:
                        msg = self.payload.get_nowait()

            except queue.Empty:
                # No idea exactly how often the weather station will report all
                # by itself.  For now though, we just submit a getChannel1Status
                # command to prompt a response if we haven't heard anything
                # before polling_interval.
                logdbg('No packet received, polling')

                req_status_msg = { 'command': 'getChannel1Status',
                                   'id': self.appid }
                self.client.publish('enno/out/json/'+self.devid, json.dumps(req_status_msg))

        self.client.disconnect()
        self.client.loop_stop()

    @property
    def hardware_name(self):
        return "wxWmr500"
