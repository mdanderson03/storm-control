#!/usr/bin/env python
"""
A simple remote HAL module emulator.

Hazen 03/20
"""
import signal
import sys

from PyQt5 import QtCore, QtWidgets

import storm_control.sc_library.parameters as params

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware

import storm_control.hal4000.halLib.halMessage as halMessage


class NoneRemoteHardwareModule(remoteHardware.RemoteHardwareModule):
    
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        kwds["module_params"] = module_params
        super().__init__(**kwds)

    def remoteMessage(self, r_message):
        super().remoteMessage(r_message)
        print(">> Received", r_message)


class NoneHardwareServerModule(remoteHardware.RemoteHardwareServerModule):
    """
    A simple remote parameter manipulation module.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.module_name = "none_remote"
        self.r_message = None

        self.delay_timer = QtCore.QTimer(self)
        self.delay_timer.setInterval(500)
        self.delay_timer.setSingleShot(True)
        self.delay_timer.timeout.connect(self.handleDelayTimer)
        
        self.message_count = 0
        self.message_timer = QtCore.QTimer(self)
        self.message_timer.setInterval(1000)
        self.message_timer.timeout.connect(self.handleMessageTimer)
         
        self.parameters = params.StormXMLObject()
        self.parameters.add(params.ParameterSetString(description = "Mode",
                                                      name = "mode",
                                                      value = "mode1",
                                                      allowed = ["mode1", "mode2", "mode3"]))

    def cleanUp(self):
        super().cleanUp()
        self.message_timer.stop()

    def handleDelayTimer(self):
        assert (self.r_message is not None)
        self.sendMessage.emit(self.r_message)
        self.r_message = None
        
    def handleMessageTimer(self):
        self.message_count += 1
        self.sendMessage.emit("message {0:d}".format(self.message_count))
        
    def processMessage(self, r_message):
        print(r_message.getSourceName(), "'" + r_message.m_type + "'")

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
            
        elif r_message.isType("start"):
            self.r_message = r_message
            self.delay_timer.start()
            
            self.message_count = 0
            self.message_timer.start()

#        elif r_message.isType("start film"):
#            assert False, "Can't start film."

        if self.r_message is None:
            self.sendResponse.emit(r_message)
        else:
            self.sendResponse.emit("wait")


if (__name__ == "__main__"):

    app = QtWidgets.QApplication(sys.argv)

    nhsm = NoneHardwareServerModule()
    rhs = remoteHardware.RemoteHardwareServer(ip_address_hal = "tcp://localhost:5557",
                                              ip_address_remote = "tcp://*:5556",
                                              module = nhsm)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
