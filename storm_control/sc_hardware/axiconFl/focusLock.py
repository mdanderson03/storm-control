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
#  3. TCP message handling.
#  4. Digital waveforms handling.
#

class FocusLockControl(QtCore.QObject):

    def __init__(self, configuration = None, **kwds):    
        super().__init__(**kwds)

        self.aflIp = configuration.get("url")
        self.last_status = {}
        self.offset_fp = None
        self.parameters = params.StormXMLObject()
        self.status = {}
        self.timing_functionality = None
        
        # Qt timer for checking focus lock
        #self.check_focus_timer = QtCore.QTimer()
        #self.check_focus_timer.setSingleShot(True)
        #self.check_focus_timer.timeout.connect(self.handleCheckFocusLock)

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

    def handleJump(self, delta):
        self.command("jump", {"step" : delta, "direction" : 1.0})

    def handleNewFrame(self, frame):
        self.status = self.getStatus()
        self.offset_fp.write("{0:d} {1:.6f} {2:.6f} {3:.6f} {4:0d}\n".format(frame.frame_number + 1,
                                                                             float(self.status["offset"]),
                                                                             float(self.status["sum"]),
                                                                             float(self.status["z position"]),
                                                                             int(self.status['lock quality'])))
        
    def newParameters(self, parameters):
        pass

    def setTimingFunctionality(self, functionality):
        self.timing_functionality = functionality.getCameraFunctionality()
        self.timing_functionality.newFrame.connect(self.handleNewFrame)

    def startFilm(self, film_settings):
        if film_settings.isSaved():
            self.offset_fp = open(film_settings.getBasename() + ".off", "w")
            headers = ["frame", "offset", "power", "stage-z", "good-offset"]
            self.offset_fp.write(" ".join(headers) + "\n")

            # Pass waveform to focus lock.
            #waveform = self.lock_mode.getWaveform()
            #if waveform is not None:
            #    # Check for a waveform from a hardware timed lock mode that uses the DAQ.
            #    pass

    def stopFilm(self):
        if self.offset_fp is not None:
            self.offset_fp.close()
            self.offset_fp = None

        self.timing_functionality.newFrame.disconnect(self.handleNewFrame)
        self.timing_functionality = None

        lock_status = {"good_lock" : bool(int(self.status["lock quality"])>0),
                       "lock_mode" : self.status["mode"],
                       "lock_sum" : float(self.status["sum"]),
                       "lock_target" : 0.0}
        
        if (len(self.status["lock target"]) > 0):
            lock_status = float(self.status["lock target"])

        return lock_status


class FocusLockView(halDialog.HalDialog):
    """
    """

    def __init__(self, configuration = None, **kwds):
        super().__init__(**kwds)

        self.ui = focuslockUi.Ui_Dialog()
        self.ui.setupUi(self)

        self.lock_display = QtWebEngineWidgets.QWebEngineView()
        layout = QtWidgets.QGridLayout(self.ui.lockDisplayWidget)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.lock_display)

        self.lock_display.load(QtCore.QUrl(configuration.get("url")))
        self.setFixedSize(900, 450)
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
            lock_sum = params.ParameterFloat(name = "lock_sum", value = lock_status["lock_sum"])
            lock_target = params.ParameterFloat(name = "lock_target", value = lock_status["lock_target"])
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"acquisition" : [good_lock,
                                                                                       lock_mode,
                                                                                       lock_sum,
                                                                                       lock_target]}))

        elif message.isType("tcp message"):
            pass

            ## See control handles this message.
            #handled = self.control.handleTCPMessage(message)

            ## If not, check view.
            #if not handled:
            #    handled = self.view.handleTCPMessage(message)

            ## Mark if we handled the message.
            #if handled:
            #    message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
            #                                                      data = {"handled" : True}))

