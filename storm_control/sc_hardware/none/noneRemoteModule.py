#!/usr/bin/env python
"""
A remote HAL module emulator.

Hazen 03/20
"""
import signal
import sys

from PyQt5 import QtCore, QtWidgets

import storm_control.sc_library.parameters as params

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware

import storm_control.hal4000.halLib.halMessage as halMessage


class NoneHardwareServerModule(remoteHardware.RemoteHardwareServerModule):
    """
    A simple remote parameter manipulation module.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
        
        self.module_name = "remote"
        
        self.parameters = params.StormXMLObject()

        self.parameters.add(params.ParameterSetString(description = "Mode",
                                                      name = "mode",
                                                      value = "mode1",
                                                      allowed = ["mode1", "mode2", "mode3"]))

    def processMessage(self, r_message):
        print(r_message.getSourceName(), r_message.m_type)

        if r_message.isType("current parameters"):
            r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                data = {"parameters" : self.parameters}))

        elif r_message.isType("new parameters"):
            r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                data = {"old parameters" : self.parameters}))
            # Update parameters.
            self.parameters = r_message.getData()["parameters"].get(self.module_name)
            r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                data = {"new parameters" : self.parameters}))
            print("New mode is:", self.parameters.get("mode"))

        self.sendWait.emit(False)
        self.sendResponse.emit(r_message)


if (__name__ == "__main__"):

    app = QtWidgets.QApplication(sys.argv)

    nhsm = NoneHardwareServerModule()
    rhs = remoteHardware.RemoteHardwareServer(ip_address = "tcp://*:5556",
                                              module = nhsm)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
