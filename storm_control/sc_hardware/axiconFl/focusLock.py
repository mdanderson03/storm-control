#!/usr/bin/env python
"""
Axicon focus lock control.

Hazen 12/23
"""
import importlib

from PyQt5 import QtCore, QtWidgets, QtWebEngineWidgets

import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halDialog as halDialog
import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halModule as halModule


# UI.
import storm_control.sc_hardware.axiconFl.focuslock_ui as focuslockUi


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

        #self.control = lockControl.LockControl(configuration = module_params.get("configuration"))
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

#            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
#                                                   data = {"parameters" : self.view.getParameters()}))

        elif message.isType("lock jump"):
            pass
            #self.control.handleJump(message.getData()["delta"])
            
        elif message.isType("new parameters"):
            pass
            #p = message.getData()["parameters"]
            #message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
            #                                                  data = {"old parameters" : self.view.getParameters().copy()}))
            #self.view.newParameters(p.get(self.module_name))
            #message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
            #                                                  data = {"new parameters" : self.view.getParameters()}))

        elif message.isType("show"):
            if (message.getData()["show"] == "focus lock"):
                self.view.show()

        elif message.isType("start"):
            #self.view.start()
            #self.control.start()
            if message.getData()["show_gui"]:
                self.view.showIfVisible()

        elif message.isType("start film"):
            pass
            #self.control.startFilm(message.getData()["film settings"])

        elif message.isType("stop film"):
            pass
            #self.control.stopFilm()
            #message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
            #                                                  data = {"parameters" : self.view.getParameters().copy()}))
            #lock_good = params.ParameterSetBoolean(name = "good_lock",
            #                                       value = self.control.isGoodLock())
            #lock_mode = params.ParameterString(name = "lock_mode",
            #                                   value = self.control.getLockModeName())
            #lock_sum = params.ParameterFloat(name = "lock_sum",
            #                                    value = self.control.getQPDSumSignal())
            #lock_target = params.ParameterFloat(name = "lock_target",
            #                                    value = self.control.getLockTarget())
            #message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
            #                                                  data = {"acquisition" : [lock_good,
            #                                                                           lock_mode,
            #                                                                           lock_sum,
            #                                                                           lock_target]}))

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

