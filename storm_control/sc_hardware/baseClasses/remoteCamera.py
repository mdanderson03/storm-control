#!/usr/bin/env python
"""
The core functionality for controlling remote camera.

Hazen 03/20
"""
import importlib
import signal
import sys

from PyQt5 import QtCore, QtWidgets

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.hal4000.camera.cameraFunctionality as cameraFunctionality

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware


class RemoteTimingFunctionality(object):
    """
    A remote version of timing functionality that only provides what
    the camera needs.
    """
    def __init__(self, timing_fn = None, **kwds):
        super().__init__(**kwds)
        
        self.time_base = timing_fn.getTimeBase()

    def getTimeBase(self):
        return self.time_base

    
class RemoteCamera(remoteHardware.RemoteHardwareModule):
    """
    The HAL side of a remote camera.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        kwds["module_params"] = module_params
        super().__init__(**kwds)

        self.camera_functionality = None

        # Send camera parameters to remote
        cam_dict = {"camera_params" : module_params.get("camera"),
                    "camera_name" : self.module_name}
        self.socket_remote.send_zipped_pickle(["init", cam_dict])

    def createRemoteMessage(self, message):
        
        r_message = super().createRemoteMessage(message)
        
        # Special handling of timing functionalities.
        if message.isType("configuration"):
            if message.sourceIs("timing"):
                timing_fn = message.getData()["properties"]["functionality"]
                r_timing_fn = RemoteTimingFunctionality(timing_fn = timing_fn)
                r_message.getData()["properties"]["functionality"] = r_timing_fn

        return r_message

    def processMessage(self, message):
        
        # Pick off camera functionality request and return local version.
        #
        if message.isType("get functionality"):
            # This message comes from display.cameraDisplay among others.
            if (message.getData()["name"] == self.module_name):
                message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                  data = {"functionality" : self.camera_functionality}))

        # Remote handles other messages.
        super().processMessage(message)
        
    def remoteMessage(self, r_message):

        # Default handling first.
        super().remoteMessage(r_message)

        # Look for updated parameters in the camera responses.
        if isinstance(r_message, remoteHardware.RemoteHALMessage) and r_message.isType("new parameters"):
            for elt in r_message.getResponses():
                data = elt.getData()
                if ('new parameters' in data):
                    self.camera_functionality.parameters = data['new parameters']

        # Additional handling of 'other' messages.
        elif isinstance(r_message, list):

            # Camera functionality information.
            if (r_message[0] == "camera_functionality"):
                self.camera_functionality = cameraFunctionality.CameraFunctionality(**r_message[1])

            # These are signals from the remote camera functionality.
            elif (r_message[0] == "emccdGain"):
                self.camera_functionality.emccdGain.emit(r_message[1])

            elif (r_message[0] == "newFrame"):
                self.camera_functionality.newFrame.emit(r_message[1])

            elif (r_message[0] == "parametersChanged"):
                print("parameters changed")
                self.camera_functionality.parametersChanged.emit()

            elif (r_message[0] == "shutter"):
                self.camera_functionality.shutter.emit(r_message[1])

            elif (r_message[0] == "started"):
                self.camera_functionality.started.emit()

            elif (r_message[0] == "stopped"):
                self.camera_functionality.stopped.emit()

            elif (r_message[0] == "temperature"):
                self.camera_functionality.temperature.emit(r_message[1])

        
class RemoteCameraServer(remoteHardware.RemoteHardwareServerModule):
    """
    The remote side of a remote camera.
    """    
    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.camera_control = None
        self.film_settings = None
        self.is_master = None
        self.module_name = None

    def cleanUp(self):
        print("closing camera")
        self.camera_control.cleanUp()

    def handleEMCCDGain(self, gain):
        self.sendMessage.emit(["emccdGain", gain])

    def handleNewFrame(self, frame):
        self.sendMessage.emit(["newFrame", frame])

    def handleParametersChanged(self):
        self.sendMessage.emit(["parametersChanged", None])

    def handleShutter(self, shutter):
        self.sendMessage.emit(["emccdGain", shutter])

    def handleStarted(self):
        self.sendMessage.emit(["started", None])

    def handleStopped(self):
        self.sendMessage.emit(["stopped", None])

    def handleTemperature(self, temperature):
        self.sendMessage.emit(["temperature", temperature])

    def processMessage(self, r_message):
        
        if r_message.isType("configuration"):
            if r_message.sourceIs("timing"):
                timing_fn = r_message.getData()["properties"]["functionality"]
                is_time_base = (timing_fn.getTimeBase() == self.module_name)
                self.holdMessage(r_message)
                self.startFilm(is_time_base)
            else:
                self.sendResponse.emit(r_message)

        elif r_message.isType("configure1"):

            # Hold message and the release so that the above two messages get
            # sent by the HAL client module *before* it finishes processing
            # this message.
            #
            self.holdMessage(r_message)
            
            # Broadcast initial parameters.
            msg = halMessage.HalMessage(m_type = "initial parameters",
                                        source = self,
                                        data = {"parameters" : self.camera_control.getParameters()})
            r_msg = remoteHardware.RemoteHALMessage(hal_message = msg)
            self.sendMessage.emit(["sendMessage", r_msg])

            # Send 'configuration' message with information about this camera.
            p_dict = {"module name" : self.module_name,
                      "is camera" : True,
                      "is master" : self.is_master}
            msg = halMessage.HalMessage(m_type = "configuration",
                                        source = self,
                                        data = {"properties" : p_dict})
            r_msg = remoteHardware.RemoteHALMessage(hal_message = msg)
            self.sendMessage.emit(["sendMessage", r_msg])

            self.releaseMessageHold()

        elif r_message.isType("current parameters"):
            r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                data = {"parameters" : self.camera_control.getParameters().copy()}))
            self.sendResponse.emit(r_message)
            
        elif r_message.isType("new parameters"):
            self.holdMessage(r_message)
            self.updateParameters(r_message)

        elif r_message.isType("shutter clicked"):
            self.holdMessage(r_message)
            self.toggleShutter()

        elif r_message.isType("start camera"):
            # This message comes from film.film. It is sent once for slaved
            # cameras and once for master cameras.
            if (r_message.getData()["master"] == self.is_master):
                self.holdMessage(r_message)
                self.startCamera()
            else:
                self.sendResponse.emit(r_message)

        elif r_message.isType("start film"):
            # This message comes from film.film, we save the film settings
            # but don't actually do anything until we get a 'configuration'
            # message from timing.timing.
            self.film_settings = r_message.getData()["film settings"]
            self.sendResponse.emit(r_message)

        elif r_message.isType("stop camera"):
            # This message comes from film.film. It is sent once for slaved
            # cameras and once for master cameras.
            if (r_message.getData()["master"] == self.is_master):
                self.holdMessage(r_message)
                self.stopCamera()
            else:
                self.sendResponse.emit(r_message)

        elif r_message.isType("stop film"):
            # This message comes from film.film, it goes to all camera at once.
            r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                data = {"parameters" : self.camera_control.getParameters()}))
            self.holdMessage(r_message)
            self.stopFilm()

        else:
            self.sendResponse.emit(r_message)
        
    def processMessageOther(self, r_message):
        [m_type, m_dict] = r_message

        # Create a camera bases on the XML passed from the client.
        if (m_type == "init"):
            self.module_name = m_dict["camera_name"]

            print("creating camera")
            camera_params = m_dict["camera_params"]
            a_module = importlib.import_module(camera_params.get("module_name"))
            a_class = getattr(a_module, camera_params.get("class_name"))
            self.camera_control = a_class(camera_name = m_dict["camera_name"],
                                          config = camera_params.get("parameters"),
                                          is_master = camera_params.get("master"))
            self.is_master = self.camera_control.getCameraFunctionality().isMaster()

            # Send some information back to the client which it can use to create
            # a local version of the remote camera functionality.
            cam_fn = self.camera_control.getCameraFunctionality()
            cam_fn_dict = {"camera_name" : cam_fn.getCameraName(),
                           "have_emccd" : cam_fn.hasEMCCD(),
                           "have_preamp" : cam_fn.hasPreamp(),
                           "have_shutter" : cam_fn.hasShutter(),
                           "have_temperature" : cam_fn.hasTemperature(),
                           "is_master" : cam_fn.isMaster(),
                           "parameters" : self.camera_control.getParameters().copy()}
            self.sendMessage.emit(["camera_functionality", cam_fn_dict])

            # Connect signal to TCP/IP messages.
            cam_fn.emccdGain.connect(self.handleEMCCDGain)
            cam_fn.newFrame.connect(self.handleNewFrame)
            cam_fn.parametersChanged.connect(self.handleParametersChanged)
            cam_fn.shutter.connect(self.handleShutter)
            cam_fn.started.connect(self.handleStarted)
            cam_fn.stopped.connect(self.handleStopped)
            cam_fn.temperature.connect(self.handleTemperature)

    def startCamera(self):
        self.camera_control.startCamera()
        self.releaseMessageHold()

    def startFilm(self, is_time_base):
        self.camera_control.startFilm(self.film_settings, is_time_base)
        self.releaseMessageHold()
        
    def stopCamera(self):
        self.camera_control.stopCamera()
        self.releaseMessageHold()

    def stopFilm(self):
        self.camera_control.stopFilm()
        self.releaseMessageHold()

    def toggleShutter(self):
        self.camera_control.toggleShutter()
        self.releaseMessageHold()
        
    def updateParameters(self, r_message):
        r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                            data = {"old parameters" : self.camera_control.getParameters().copy()}))
        p = r_message.getData()["parameters"].get(self.module_name)
        self.camera_control.newParameters(p)
        r_message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                            data = {"new parameters" : self.camera_control.getParameters()}))
        self.releaseMessageHold()


if (__name__ == "__main__"):

    app = QtWidgets.QApplication(sys.argv)

    rcs = RemoteCameraServer()
    rhs = remoteHardware.RemoteHardwareServer(ip_address_hal = "tcp://localhost:5557",
                                              ip_address_remote = "tcp://*:5556",
                                              module = rcs)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
