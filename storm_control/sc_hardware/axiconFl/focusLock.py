#!/usr/bin/env python
"""
Axicon focus lock control.

Hazen 12/23
"""
import importlib
import requests

from PyQt5 import QtCore, QtWidgets, QtWebEngineWidgets

import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halDialog as halDialog
import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halModule as halModule


# UI.
import storm_control.sc_hardware.axiconFl.focuslock_ui as focuslockUi


# TODO:
#  1. Log when we don't get '200' from the lock?
#  2. Lock on film start parameter (if not already locked).
#

def isLocked(status):
    return (status["mode"] == "locked")

    
class FocusLockControl(QtCore.QObject):

    def __init__(self, configuration = None, **kwds):    
        super().__init__(**kwds)

        self.aflIp = configuration.get("url")
        self.current_state = None
        self.hzs_pname = "hardware_z_scan"
        self.hzs_zstring = None
        self.last_lock_target = None
        self.last_status = {}
        self.lock_movie_i = 0
        self.lock_movie_name = None
        self.offset_fp = None
        self.parameters = params.StormXMLObject()
        self.status = {}
        self.recording = configuration.get("record", True)
        self.timing_functionality = None

        # 
        # Add hardware z scan specific parameters.
        #
        # This part was lifted from the "standard" focus lock.
        #
        p = self.parameters.addSubSection(self.hzs_pname)
        p.add(params.ParameterString(description = "Frame z steps (in microns).",
                                     name = "z_offsets",
                                     value = ""))
        
        # Qt timers for checking the focus lock.
        self.check_focus_timer = QtCore.QTimer()
        self.check_focus_timer.setSingleShot(True)
        self.check_focus_timer.timeout.connect(self.handleCheckFocusLock)

        self.scan_for_sum_timer = QtCore.QTimer()
        self.scan_for_sum_timer.setSingleShot(True)
        self.scan_for_sum_timer.timeout.connect(self.handleScanForSum)

    def cleanUp(self):
        self.command("unlock")
        self.command("setLaserPower", {"value" : 0})
        
    def command(self, cmd, params = {}):
        r = requests.get(f"{self.aflIp}/command", params = {"cmd" : cmd} | params)
        if (r.status_code != 200):
            print(f"GET failed with {r.status_code}")
        return [r.json(), r.status_code]

    def getParameters(self):
        return self.parameters
    
    def getStatus(self):
        [json, status_code] = self.command("getStatus")
        if (status_code != 200):
            json = self.last_status
        else:
            self.last_status = json
        return json

    def handleCheckFocusLock(self):
        status = self.getStatus()

        # Return if we have a good lock.
        if (status["lock quality"] != 0):
            self.handleDone(True)

        else:
            self.current_state["num_checks"] -= 1

            # Start a scan if we still don't have a good lock.
            if (self.current_state["num_checks"] == 0):
                tcp_message = self.current_state["tcp_message"]
            
                # Start scanning for sum, if we haven't already done this once.
                if tcp_message.getData("focus_scan") and not self.current_state["already scanned"]:
                    scan_range = tcp_message.getData("scan_range")
                    z_center = status["z position"]
                    if tcp_message.getData("z_center") is not None:
                        z_center = tcp_message.getData("z_center")
                        
                    self.command("scanForSum", {"start" : z_center - scan_range, "stop" : z_center + scan_range})
                    self.scan_for_sum_timer.start(100)

                # Otherwise just return that we were not successful.
                else:
                    self.handleDone(False)

            else:
                self.check_focus_timer.start(100)
                
    def handleDone(self, success):
        
        # Add the TCP message response.
        tcp_message = self.current_state["tcp_message"]
            
        if tcp_message.isType("Check Focus Lock"):
            tcp_message.addResponse("focus_status", success)

        elif tcp_message.isType("Find Sum"):
            tcp_message.addResponse("focus_status", success)
            if success:
                status = self.getStatus()
                tcp_message.addResponse("found_sum", status["signal quality"])

        else:
            raise Exception("No response handling for " + tcp_message.getType())

        # Relock if we were locked.
        if self.current_state["locked"]:
            self.command("lock", {"target" : self.current_state["lock_target"]})

        # This lets HAL know we have handled this message.
        self.current_state["message"].decRefCount()

        self.current_state = None

    def handleJump(self, delta):
        self.command("jump", {"step" : delta, "direction" : 1.0})

    def handleNewFrame(self, frame):

        # Save current status for stopFilm()
        self.status = self.getStatus()
        
        if self.offset_fp is not None:
            self.offset_fp.write("{0:d} {1:.6f} {2:.6f} {3:.6f} {4:0d}\n".format(frame.frame_number + 1,
                                                                                 float(self.status["offset"]),
                                                                                 float(self.status["signal quality"]),
                                                                                 float(self.status["z position"]),
                                                                                 int(self.status["lock quality"])))

    def handleScanForSum(self):
        status = self.getStatus()
        if ("message" in status):
            success = (status["message"] == "ScanForSum succeeded")

            # For 'Check Focus Lock', restart the lock and poll for approximately
            # 5 seconds to give it time to get to the target position.
            if (self.current_state["tcp_message"] == "Check Focus Lock") and success:
                self.command("lock", {"target" : self.current_state["lock_target"]})
                self.current_state["num_checks"] = 50
                self.current_state["already scanned"] = True
                self.handleCheckFocusLock()

            # Otherwise return directly.
            else:
                self.handleDone(success)
        else:
            self.scan_for_sum_timer.start(100)
        
    def handleTCPMessage(self, message):
        """
        Handles TCP messages from tcpControl.TCPControl.
        """
        status = self.getStatus()

        tcp_message = message.getData()["tcp message"]
        if tcp_message.isType("Check Focus Lock"):
            if tcp_message.isTest():
                tcp_message.addResponse("duration", 2)
                
            else:

                # Only makes sense to do this is the lock is on?
                if isLocked(status):
                    # Record current state.
                    assert (self.current_state == None)
                    self.current_state = {"already scanned" : False,
                                          "locked" : isLocked(status),
                                          "lock_target" : status["lock target"],
                                          "num_checks" : tcp_message.getData("num_focus_checks") + 1,
                                          "message" : message,
                                          "tcp_message" : tcp_message}
                    
                    # Start checking the focus lock.
                    self.handleCheckFocusLock()
                    
                    # Increment the message reference count so that HAL
                    # knows that it has not been fully processed.
                    message.incRefCount()
                else:
                    tcp_message.addResponse("focus status", True)

            return True

        elif tcp_message.isType("Find Sum"):
            if tcp_message.isTest():
                tcp_message.addResponse("duration", 10)
                
            else:

                # Check if we already have enough sum signal.
                if (status["signal quality"] != 0):
                    tcp_message.addResponse("focus_status", True)
                    tcp_message.addResponse("found_sum", status["sum"])

                # If not, start scanning.
                else:
                     
                    # Record current state.
                    assert (self.current_state == None)
                    self.current_state = {"locked" : isLocked(status),
                                          "lock_target" : status["lock target"],
                                          "message" : message,
                                          "tcp_message" : tcp_message}
                
                    # Start find sum mode.
                    self.command("scanForSum")
                    self.scan_for_sum_timer.start(100)
                
                    # Increment the message reference count so that HAL
                    # knows that it has not been fully processed.
                    message.incRefCount()

            return True

        elif tcp_message.isType("Set Lock Target"):
            if not tcp_message.isTest() and isLocked(status):
                self.command("lock", {"target" : tcp_message.getData("lock_target")})
            return True
        
        return False
    
    def newParameters(self, parameters):
        p = parameters.get(self.hzs_pname)
        self.hzs_zstring = None
        if (len(p.get("z_offsets")) > 0):
            self.hzs_zstring = p.get("z_offsets")

    def setTimingFunctionality(self, functionality):
        self.timing_functionality = functionality.getCameraFunctionality()
        self.timing_functionality.newFrame.connect(self.handleNewFrame)

    def startFilm(self, film_settings):
        status = self.getStatus()
        
        self.offset_fp = None
        if film_settings.isSaved():
            self.offset_fp = open(film_settings.getBasename() + ".off", "w")
            headers = ["frame", "offset", "power", "stage-z", "good-offset"]
            self.offset_fp.write(" ".join(headers) + "\n")

        self.last_lock_target = None
        if isLocked(status) and (self.hzs_zstring is not None):
            self.last_lock_target = status["lock target"]
            self.command("setWaveform", {"waveform" : self.hzs_zstring})

        if self.recording:
            self.lock_movie_name = "movie_{0:04d}.tif".format(self.lock_movie_i%9000)
            self.command("record", {"filename" : self.lock_movie_name, "frames" : 40})
            self.lock_movie_i += 1

    def stopFilm(self):
        if self.offset_fp is not None:
            self.offset_fp.close()
            self.offset_fp = None

        self.timing_functionality.newFrame.disconnect(self.handleNewFrame)
        self.timing_functionality = None

        lock_status = {"good_lock" : bool(int(self.status["lock quality"])>0),
                       "lock_mode" : self.status["mode"],
                       "lock_movie" : str(self.lock_movie_name),
                       "lock_sum" : float(self.status["signal quality"]),
                       "lock_target" : 0.0}
        
        if (len(str(self.status["lock target"])) > 0):
            lock_status['lock_target'] = float(self.status["lock target"])

        if self.last_lock_target is not None:
            self.command("lock", {"target" : self.last_lock_target})

        return lock_status


class FocusLockView(halDialog.HalDialog):

    def __init__(self, configuration = None, **kwds):
        super().__init__(**kwds)

        self.ui = focuslockUi.Ui_Dialog()
        self.ui.setupUi(self)

        self.lock_display = QtWebEngineWidgets.QWebEngineView()
        layout = QtWidgets.QGridLayout(self.ui.lockDisplayWidget)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.lock_display)

        self.lock_display.load(QtCore.QUrl(configuration.get("url")))
        self.setFixedSize(900, 455)
        self.setEnabled(True)

    def show(self):
        super().show()
        self.lock_display.show()

        
class FocusLock(halModule.HalModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.configuration = module_params.get("configuration")

        self.control = FocusLockControl(configuration = module_params.get("configuration"))
        self.view = FocusLockView(module_name = self.module_name,
                                  configuration = module_params.get("configuration"))
        self.view.halDialogInit(qt_settings,
                                module_params.get("setup_name") + " axicon focus lock")

        # This message is usually used by a USB joystick or Bluetooth control to
        # to request that the piezo stage move.
        halMessage.addMessage("lock jump",
                              validator = {"data" : {"delta" : [True, float]},
                                           "resp" : None})
        
    def cleanUp(self, qt_settings):
        self.control.cleanUp()
        self.view.cleanUp(qt_settings)

    def handleControlMessage(self, message):
        self.sendMessage(message)

    def processMessage(self, message):

        if message.isType("configuration"):
            if message.sourceIs("timing"):
                self.control.setTimingFunctionality(message.getData()["properties"]["functionality"])

        elif message.isType("configure1"):
            self.sendMessage(halMessage.HalMessage(m_type = "add to menu",
                                                   data = {"item name" : "Focus Lock",
                                                           "item data" : "focus lock"}))

            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
                                                   data = {"parameters" : self.control.getParameters()}))

        elif message.isType("lock jump"):
            self.control.handleJump(message.getData()["delta"])
            
        elif message.isType("new parameters"):
            p = message.getData()["parameters"]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"old parameters" : self.control.getParameters().copy()}))
            self.control.newParameters(p.get(self.module_name))
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"new parameters" : self.control.getParameters()}))

        elif message.isType("show"):
            if (message.getData()["show"] == "focus lock"):
                self.view.show()

        elif message.isType("start"):
            if message.getData()["show_gui"]:
                self.view.showIfVisible()

        elif message.isType("start film"):
            self.control.startFilm(message.getData()["film settings"])

        elif message.isType("stop film"):
            lock_status = self.control.stopFilm()
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.control.getParameters().copy()}))

            good_lock = params.ParameterSetBoolean(name = "good_lock", value = lock_status["good_lock"])
            lock_mode = params.ParameterString(name = "lock_mode", value = lock_status["lock_mode"])
            lock_movie = params.ParameterString(name = "lock_movie", value = lock_status["lock_movie"])
            lock_sum = params.ParameterFloat(name = "lock_sum", value = lock_status["lock_sum"])
            lock_target = params.ParameterFloat(name = "lock_target", value = lock_status["lock_target"])
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"acquisition" : [good_lock,
                                                                                       lock_mode,
                                                                                       lock_movie,
                                                                                       lock_sum,
                                                                                       lock_target]}))

        elif message.isType("tcp message"):
            handled = self.control.handleTCPMessage(message)
            if handled:
                message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                  data = {"handled" : True}))

