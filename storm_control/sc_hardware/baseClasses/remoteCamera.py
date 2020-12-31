#!/usr/bin/env python
"""
The core functionality for controlling remote camera.

Hazen 03/20
"""
import importlib
import os
import signal
import sys
import argparse

from PyQt5 import QtCore, QtWidgets

import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.imagewriters as imagewriters

import storm_control.hal4000.camera.cameraFunctionality as cameraFunctionality

import storm_control.sc_hardware.baseClasses.remoteHardware as remoteHardware


class SignalCounter(QtCore.QObject):
    """
    This keeps track of how many unique slots are connected to this signal.
    
    We're using a dictionary here because some objects will call 
    disconnect() even when they are not currently connected.
    """
    connected = QtCore.pyqtSignal(bool)
    
    def __init__(self, signal, **kwds):
        super().__init__(**kwds)

        self.connections = {}
        self.signal = signal

    def connect(self, slot):
        notify = (len(self.connections) == 0)
        
        # We want the ID of the object, not the bound method (or slot).
        self.connections[id(slot.__self__)] = True
        self.signal.connect(slot)

        # Only send 'connected' signal if the slot was previously not
        # connected to anything.
        #
        if notify:
            self.connected.emit(True)
            
    def disconnect(self, slot):
        notify = (len(self.connections) > 0)
        
        self.connections.pop(id(slot.__self__), None)
        self.signal.disconnect(slot)

        # Need both checks as slot.__self__ may not have been in our
        # dictionary of connections in the first place.
        #
        if notify and (len(self.connections) == 0):
            self.connected.emit(False)

    def emit(self, *vals):
        self.signal.emit(*vals)


class RemoteCameraFunctionality(cameraFunctionality.CameraFunctionality):
    """
    A version of CameraFunctionality that keeps track of the number of
    connections to the 'newFrame' signal. Sending frames over the wire
    can be expensive so we don't want to that unless they are being 
    used.

    We also override the isSaved() function so that this will report
    the correct thing depending on if the camera is configured for
    'remote_save'.
    """
    _newFrame = QtCore.pyqtSignal(object)

    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.remote_save = False
        
        self.newFrame = SignalCounter(self._newFrame)

    def isSaved(self):
        if self.remote_save:
            return False
        else:
            return super().isSaved()

    def setRemoteSave(self, remote_save):
        self.remote_save = remote_save
    

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

        self.remote_save = module_params.get("configuration").get("remote_save")
        
        self.camera_functionality = None

        # Send camera parameters to remote
        cam_dict = {"camera_params" : module_params.get("camera"),
                    "camera_name" : self.module_name,
                    "remote_save" : self.remote_save}
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

    def handleConnected(self, connected):
        self.socket_remote.send_zipped_pickle(['connected', {"connected" : connected}])
        
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
                self.camera_functionality = RemoteCameraFunctionality(**r_message[1])
                self.camera_functionality.newFrame.connected.connect(self.handleConnected)
                self.camera_functionality.setRemoteSave(self.remote_save)

            # These are signals from the remote camera functionality.
            elif (r_message[0] == "emccdGain"):
                self.camera_functionality.emccdGain.emit(r_message[1])

            elif (r_message[0] == "newFrame"):
                self.camera_functionality.newFrame.emit(r_message[1])
                self.socket_remote.send_zipped_pickle(['received', {"received" : True}])

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
        self.connected = False
        
        self.film_settings = None
        self.is_master = None
        self.module_name = None
        self.n_lost = 0
        self.n_sent = 0
        self.remote_save = None
        self.writer = None
        
        self.writer_stopped_timer = QtCore.QTimer(self)
        self.writer_stopped_timer.setSingleShot(True)
        self.writer_stopped_timer.setInterval(10)
        self.writer_stopped_timer.timeout.connect(self.handleStopWriter)

    def cleanUp(self):
        self.connected = False
        self.n_sent = 0
        self.remote_save = None
        self.writer = None

        # Disconnect camera.
        cam_fn = self.camera_control.getCameraFunctionality()
        cam_fn.emccdGain.disconnect(self.handleEMCCDGain)
        cam_fn.newFrame.disconnect(self.handleNewFrame)
        cam_fn.parametersChanged.disconnect(self.handleParametersChanged)
        cam_fn.shutter.disconnect(self.handleShutter)
        cam_fn.started.disconnect(self.handleStarted)
        cam_fn.stopped.disconnect(self.handleStopped)
        cam_fn.temperature.disconnect(self.handleTemperature)

        # Clean up camera.
        self.camera_control.cleanUp()
        
        super().cleanUp()

    def handleEMCCDGain(self, gain):
        self.sendMessage.emit(["emccdGain", gain])

    def handleNewFrame(self, frame):
        if self.connected:
            if (self.n_sent == 0):
                self.n_sent += 1
                self.sendMessage.emit(["newFrame", frame])
            else:
                self.n_lost += 1

    def handleParametersChanged(self):
        self.sendMessage.emit(["parametersChanged", None])

    def handleShutter(self, shutter):
        self.sendMessage.emit(["emccdGain", shutter])

    def handleStarted(self):
        self.sendMessage.emit(["started", None])

    def handleStopped(self):
        self.sendMessage.emit(["stopped", None])

    def handleStopWriter(self):
        # Keep checking self.writer until it is stopped, then close and
        # tell HAL that we are done.
        #
        if self.writer.isStopped():
            self.writer.closeWriter()
            self.writer = None
            self.releaseMessageHold()
        else:
            self.writer_stopped_timer.start()

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

            self.remote_save = m_dict["remote_save"]
            
            print("creating camera")
            camera_params = m_dict["camera_params"]
            a_module = importlib.import_module(camera_params.get("module_name"))
            a_class = getattr(a_module, camera_params.get("class_name"))
            self.camera_control = a_class(camera_name = m_dict["camera_name"],
                                          config = camera_params.get("parameters"),
                                          is_master = camera_params.get("master"))
            self.is_master = self.camera_control.getCameraFunctionality().isMaster()

            # Add remote_save_dir parameter in remote_save mode.
            #
            if self.remote_save:
                self.camera_control.parameters.add(params.ParameterString(description = "Remove save directory",
                                                                          name = "remote_save_dir",
                                                                          value = ""))
                self.camera_control.parameters.set("remote_save_dir",
                                                   camera_params.get("parameters").get("remote_save_dir"))
                
            # Send some information back to the client which it can use to create
            # a local version of the remote camera functionality.
            #
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
            #
            cam_fn.emccdGain.connect(self.handleEMCCDGain)
            cam_fn.newFrame.connect(self.handleNewFrame)
            cam_fn.parametersChanged.connect(self.handleParametersChanged)
            cam_fn.shutter.connect(self.handleShutter)
            cam_fn.started.connect(self.handleStarted)
            cam_fn.stopped.connect(self.handleStopped)
            cam_fn.temperature.connect(self.handleTemperature)

        elif (m_type == "connected"):
            self.connected = m_dict["connected"]
            if not self.connected:
                if (self.n_lost > 0):
                    print(">>", self.n_lost, "frames lost")
                    self.n_lost = 0

        elif (m_type == "received"):
            self.n_sent -= 1

    def startCamera(self):
        self.n_lost = 0
        self.camera_control.startCamera()
        self.releaseMessageHold()

    def startFilm(self, is_time_base):
        
        # Change where to save if we're saving remotely and create image writer.
        #
        if self.remote_save:

            # Get movie name from film settings.
            movie_name = os.path.basename(self.film_settings.basename)

            # Combine with local directory setting.
            cam_fn = self.camera_control.getCameraFunctionality()
            basename = os.path.join(cam_fn.getParameter("remote_save_dir"), movie_name)
            print("  recording", basename)

            # Update film settings basename and create file writer.
            self.film_settings.basename = basename
            self.writer = imagewriters.createFileWriter(cam_fn, self.film_settings)

        self.camera_control.startFilm(self.film_settings, is_time_base)
        self.releaseMessageHold()
        
    def stopCamera(self):
        self.camera_control.stopCamera()
        self.releaseMessageHold()

    def stopFilm(self):
        self.camera_control.stopFilm()

        if self.remote_save:
            self.writer_stopped_timer.start()
        else:
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

    # Parse input
    parser = argparse.ArgumentParser(description="Create a remote camera server")
    parser.add_argument("-r", "--remote",
                        metavar="remote",
                        default="tcp://*:5556",                    
                        type=str, 
                        help="remote server IP address")
    parser.add_argument("-l", "--local", 
                        metavar="local",
                        default="tcp://*:5557",
                        type=str, 
                        help="hal IP address")
     

    input = parser.parse_args(sys.argv[1:])

    # Create camera and hardware server
    rcs = RemoteCameraServer()
    rhs = remoteHardware.RemoteHardwareServer(ip_address_hal = input.local,
                                              ip_address_remote = input.remote,
                                              module = rcs)
    print("Creating a local camera server at " + rhs.ip_address_remote)
    print("...communicating with hal at " + rhs.ip_address_hal)

    # Need this so that CTRL-C works.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app.exec_()
