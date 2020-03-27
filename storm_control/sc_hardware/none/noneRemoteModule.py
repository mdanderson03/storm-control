#!/usr/bin/env python
"""
A remote HAL module emulator.

Hazen 03/20
"""

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware


class NoneHardwareServerModule(remoteHardware.RemoteHardwareServerModule):
    pass


if (__name__ == "__main__"):
    nhsm = NoneHardwareServerModule(ip_address = "tcp://*:5556")
    nhsm.bind()
    
    while True:
        print("waiting for next message")
        message = nhsm.nextMessage()
        print("responding")
        nhsm.sendWait(False)
        print(message)
        nhsm.sendResponse(message)
