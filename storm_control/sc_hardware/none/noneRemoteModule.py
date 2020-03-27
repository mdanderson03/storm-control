#!/usr/bin/env python
"""
A remote HAL module emulator.

Hazen 03/20
"""
import signal
import sys

from PyQt5 import QtCore, QtWidgets

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware


class NoneHardwareServerModule(remoteHardware.RemoteHardwareServerModule):

    def processMessage(self, r_message):
        super().processMessage(r_message)
        print(r_message.getSourceName(), r_message.m_type)


if (__name__ == "__main__"):

    app = QtWidgets.QApplication(sys.argv)

    nhsm = NoneHardwareServerModule()
    rhs = remoteHardware.RemoteHardwareServer(ip_address = "tcp://*:5556",
                                              module = nhsm)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
