#!/usr/bin/env python
"""
HAL module for polling a Arduino Environment Monitor

Jeff 07/22
"""

from PyQt5 import QtCore

import storm_control.hal4000.halLib.halMessage as halMessage
import traceback

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.serial.RS232 as RS232
import storm_control.sc_library.hdebug as hdebug
import storm_control.sc_library.parameters as params

import json

class EnvironmentMonitorModule(hardwareModule.HardwareModule):
    """
    This Module controls an Environment Monitor (any device that respond via serial with a simple dictionary reporting on the environment).
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        ## Get the configuratio
        self.configuration = module_params.get("configuration")

        ## Create the environment monitor serial port
        self.env_monitor = EnvironmentMonitorRS232(baudrate = self.configuration.get("baudrate"), port = self.configuration.get("port"), 
                                                  timeout = self.configuration.get("timeout", 1), end_of_line = "\n")
                                                            
    def cleanUp(self, qt_settings):
        if self.env_monitor is not None:
            self.env_monitor.shutDown()
        
    def processMessage(self, message):
        if self.env_monitor is None:
            return

        if message.isType("stop film"):
            self.stopFilm(message)

    def stopFilm(self, message):
        ## The monitor currently pings the temperature only when a movie is complete
        environment_state = self.env_monitor.getEnvironmentState()

        environment_value_list = []
        for element in environment_state.keys():
            environment_value_list.append(params.ParameterCustom(name = element,
                                            value = str(environment_state[element])))
        if len(environment_value_list) > 0:
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                            data = {"acquisition" : environment_value_list}))

class EnvironmentMonitorRS232(RS232.RS232):
    """
    Environment Monitor RS232 interface class.
    """
    def __init__(self, **kwds):
        """
        Connect to the RS232 at the specified port.
        """
        self.live = True
        self.environment_dict = {} ## The dictionary containing the environmental parameters

        # RS232 stuff
        try:
            super().__init__(**kwds)
            test = self.commWithResp("read")
            print(test)
            if not test:
                self.live = False

        except (AttributeError, AssertionError):
            print(traceback.format_exc())
            self.live = False
            print("The environment monitor is not properly connected!")

    def getEnvironmentState(self):
        """
        Read out the environment state from the monitor and convert xml to a dictionary
        """

        # Handle an inactive environment monitor
        if not self.live:
            return {}
        
        ## Read the environment monitor, it will return an xml string that can be parsed to a dictionary
        try:
            environment_status_xml = self.commWithResp("read")
        except:
            print("Encountered a problem accessing the environment monitor")
            return {}
                
        # Convert the xml to a dictionary
        self.environment_dict = json.loads(environment_status_xml)
        return self.environment_dict
