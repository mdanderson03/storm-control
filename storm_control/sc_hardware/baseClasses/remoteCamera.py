#!/usr/bin/env python
"""
The core functionality for controlling remote camera.

Hazen 03/20
"""
import importlib
import signal
import sys

from PyQt5 import QtCore, QtWidgets

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware


class RemoteCamera(remoteHardware.RemoteHardwareModule):
    """
    The HAL side of a remote camera.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        kwds["module_params"] = module_params
        super().__init__(**kwds)

        # Send camera parameters to remote
        cam_dict = {"camera_params" : module_params.get("camera"),
                    "camera_name" : self.module_name}
        self.socket_remote.send_zipped_pickle(["init", cam_dict])


class RemoteCameraServer(remoteHardware.RemoteHardwareServerModule):
    """
    The remote side of a remote camera.
    """    
    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.camera_control = None
        self.film_settings = None
        self.is_master = None

    def cleanUp(self):
        print("closing camera")
        self.camera_control.cleanUp()
        
    def processMessageOther(self, r_message):
        [m_type, m_dict] = r_message
        
        if (m_type == "init"):
            print("creating camera")
            camera_params = m_dict["camera_params"]
            a_module = importlib.import_module(camera_params.get("module_name"))
            a_class = getattr(a_module, camera_params.get("class_name"))
            self.camera_control = a_class(camera_name = m_dict["camera_name"],
                                          config = camera_params.get("parameters"),
                                          is_master = camera_params.get("master"))
            self.is_master = self.camera_control.getCameraFunctionality().isMaster()


if (__name__ == "__main__"):

    app = QtWidgets.QApplication(sys.argv)

    rcs = RemoteCameraServer()
    rhs = remoteHardware.RemoteHardwareServer(ip_address_hal = "tcp://localhost:5557",
                                              ip_address_remote = "tcp://*:5556",
                                              module = rcs)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
