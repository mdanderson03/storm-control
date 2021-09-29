#!/usr/bin/env python
"""
HAL module for controlling a zaber z focus leveraging both coarse and fine focusing.

Jeff 09/21
Hazen 05/18
"""
import math
from PyQt5 import QtCore

import storm_control.sc_library.halExceptions as halExceptions

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.baseClasses.stageZModule as stageZModule
import storm_control.sc_hardware.baseClasses.lockModule as lockModule

### IMPORT THE ZABER Z RS232
import storm_control.sc_hardware.zaber.zaberFocus as zaberFocus


class ZaberCoarseFocusBufferedFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    This functionality interfaces with the coarse focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    
    # FROM ZStageFunctionalityBuffered
    zStagePosition = QtCore.pyqtSignal(float)

    def __init__(self, update_interval = None, velocity = None, **kwds):
        super().__init__(**kwds)

        # From lockModule.LoclFunctionalityMixin
        self.parameters = parameters

        # From lockModule.ZStageFunctionalityMixin
        self.z_position = 0.0

        # From ZStageFunctionalityBuffered
        self.z_stage = z_stage

        ### EVERYTHING BELOW IS FROM THE TIGER
        self.maximum = self.getParameter("maximum")
        self.minimum = self.getParameter("minimum")

        # Set initial z velocity.
        self.mustRun(task = self.z_stage.zSetVelocity,
                     args = [velocity])
        
        # This timer to restarts the update timer after a move. It appears
        # that if you query the position during a move the stage will stop
        # moving.
        self.restart_timer = QtCore.QTimer()
        self.restart_timer.setInterval(2000)
        self.restart_timer.timeout.connect(self.handleRestartTimer)
        self.restart_timer.setSingleShot(True)

        # Each time this timer fires we'll query the z stage position. We need
        # to do this as the user might use the controller to directly change
        # the stage z position.
        self.update_timer = QtCore.QTimer()
        self.update_timer.setInterval(update_interval)
        self.update_timer.timeout.connect(self.handleUpdateTimer)
        self.update_timer.start()

    def goAbsolute(self, z_pos):
        ### OVERLOAD FROM TIGER
        # We have to stop the update timer because if it goes off during the
        # move it will stop the move.
        self.update_timer.stop()
        super().goAbsolute(z_pos)
        self.restart_timer.start()

    # From ZStageFunctionalityBuffered
    def goAbsolute(self, z_pos):
        if (z_pos != self.z_position):
            if (z_pos < self.minimum):
                z_pos = self.minimum
            if (z_pos > self.maximum):
                z_pos = self.maximum
            self.maybeRun(task = self.zMoveTo,
                          args = [z_pos],
                          ret_signal = self.zStagePosition)

    # OVERLOAD FROM TIGER
    def goRelative(self, z_delta):
        z_pos = -1.0*self.z_position + z_delta
        self.goAbsolute(z_pos)        

    # OVERLOAD FROM TIGER
    def handleRestartTimer(self):
        self.update_timer.start()
        
    # OVERLOAD FROM TIGER
    def handleUpdateTimer(self):
        self.mustRun(task = self.position,
                     ret_signal = self.zStagePosition)
    # OVERLOAD FROM TIGER
    def position(self):
        self.z_position = self.z_stage.zPosition()["z"]
        return -1.0*self.z_position

    # OVERLOAD FROM TIGER
    def zero(self):
        self.mustRun(task = self.z_stage.zZero)
        self.zStagePosition.emit(0.0)

    # OVERLOAD FROM TIGER
    def zMoveTo(self, z_pos):
        return -1.0*super().zMoveTo(-z_pos)

    # From ZStageFunctionalityBuffered
    def zMoveTo(self, z_pos):
        self.z_stage.zMoveTo(z_pos)
        self.z_position = z_pos
        return z_pos

    # From lockModule.LockFunctionalityMixin
    def getParameter(self, pname):
        return self.parameters.get(pname)

    # From lockModule.LockFunctionalityMixin
    def hasParameter(self, pname):
        return self.parameters.has(pname)

    # From lockModule.ZStageFunctionalityMixin
    def getCenterPosition(self):
        return self.getParameter("center")
    
    # From lockModule.ZStageFunctionalityMixin
    def getCurrentPosition(self):
        return self.z_position

    # From lockModule.ZStageFunctionalityMixin
    def getDaqWaveform(self, waveform):
        """
        Scale the analog waveform (a numpy array) that the daq will use to drive 
        the z-stage in hardware timed mode to the correct voltages.

        Returns a daqModule.DaqWaveform object.
        """
        pass

    # From lockModule.ZStageFunctionalityMixin
    def getMaximum(self):
        return self.getParameter("maximum")

    # From lockModule.ZStageFunctionalityMixin
    def getMinimum(self):
        return self.getParameter("minimum")
    
    # From lockModule.ZStageFunctionalityMixin
    def recenter(self):
        self.goAbsolute(self.getCenterPosition())


# I might be able to inherit much of what I need here.... 
class ZaberFineFocusBufferedFunctionality(hardwareModule.BufferedFunctionality, lockModule.ZStageFunctionalityMixin):
    """
    This functionality interfaces with the fine focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    # FROM ZStageFunctionalityBuffered
    zStagePosition = QtCore.pyqtSignal(float)

    def __init__(self, parameters = None, **kwds):
        super().__init__(**kwds)

		# From LockFunctionalityMixin
        self.parameters = parameters

		# From ZStageFunctionalityMixin        
		self.z_position = 0.0

		# From here
        self.z_stage = z_stage

	# From lockModule.ZStageFunctionalityMixin
    def getCenterPosition(self):
        return self.getParameter("center")

	# From lockModule.ZStageFunctionalityMixin
    def getCurrentPosition(self):
        return self.z_position
	
	# From lockModule.ZStageFunctionalityMixin
    def getMaximum(self):
        return self.getParameter("maximum")
	
	# From lockModule.ZStageFunctionalityMixin
    def getMinimum(self):
        return self.getParameter("minimum")

	# From here:  This probably needs to be updated so as to allow 
    def goAbsolute(self, z_pos):
        if (z_pos < self.minimum):
            z_pos = self.minimum
        if (z_pos > self.maximum):
            z_pos = self.maximum
        self.z_position = z_pos
        self.z_stage.zMoveTo(self.z_position)
        self.zStagePosition.emit(self.z_position)

	# From here
    def goRelative(self, z_delta):
        z_pos = self.z_position + z_delta
        self.goAbsolute(z_pos)

	# From LockFunctionalityMixin
    def getParameter(self, pname):
        return self.parameters.get(pname)
	
	# From LockFunctionalityMixin
    def hasParameter(self, pname):
        return self.parameters.has(pname)

	# From lockModule.ZStageFunctionalityMixin
    def recenter(self):
        self.goAbsolute(self.getCenterPosition())


class TigerVoltageZFunctionality(voltageZModule.VoltageZFunctionality):
    """
    External voltage control of piezo Z stage.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
    
class TigerZStageFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    The z sign convention of this stage is the opposite from the expected
    so we have to adjust.
    """
    def __init__(self, update_interval = None, velocity = None, **kwds):
        super().__init__(**kwds)

        self.maximum = self.getParameter("maximum")
        self.minimum = self.getParameter("minimum")

        # Set initial z velocity.
        self.mustRun(task = self.z_stage.zSetVelocity,
                     args = [velocity])
        
        # This timer to restarts the update timer after a move. It appears
        # that if you query the position during a move the stage will stop
        # moving.
        self.restart_timer = QtCore.QTimer()
        self.restart_timer.setInterval(2000)
        self.restart_timer.timeout.connect(self.handleRestartTimer)
        self.restart_timer.setSingleShot(True)

        # Each time this timer fires we'll query the z stage position. We need
        # to do this as the user might use the controller to directly change
        # the stage z position.
        self.update_timer = QtCore.QTimer()
        self.update_timer.setInterval(update_interval)
        self.update_timer.timeout.connect(self.handleUpdateTimer)
        self.update_timer.start()
        
    def goAbsolute(self, z_pos):
        # We have to stop the update timer because if it goes off during the
        # move it will stop the move.
        self.update_timer.stop()
        super().goAbsolute(z_pos)
        self.restart_timer.start()

    def goRelative(self, z_delta):
        z_pos = -1.0*self.z_position + z_delta
        self.goAbsolute(z_pos)        

    def handleRestartTimer(self):
        self.update_timer.start()
        
    def handleUpdateTimer(self):
        self.mustRun(task = self.position,
                     ret_signal = self.zStagePosition)

    def position(self):
        self.z_position = self.z_stage.zPosition()["z"]
        return -1.0*self.z_position

    def zero(self):
        self.mustRun(task = self.z_stage.zZero)
        self.zStagePosition.emit(0.0)
    
    def zMoveTo(self, z_pos):
        return -1.0*super().zMoveTo(-z_pos)
    
        
#
# Inherit from stageModule.StageModule instead of the base class so we don't
# have to duplicate most of the stage stuff, particularly the TCP control.
#
class TigerController(stageModule.StageModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.controller_mutex = QtCore.QMutex()
        self.functionalities = {}

        # These are used for the Z piezo stage.
        self.z_piezo_configuration = None
        self.z_piezo_functionality = None

        configuration = module_params.get("configuration")
        self.controller = tiger.Tiger(baudrate = configuration.get("baudrate"),
                                      port = configuration.get("port"))
        
        if self.controller.getStatus():

            # Note: We are not checking whether the devices that the user requested
            #       are actually available, we're just assuming that they know what
            #       they are doing.
            #
            devices = configuration.get("devices")
            for dev_name in devices.getAttrs():

                # XY stage.
                if (dev_name == "xy_stage"):
                    settings = devices.get(dev_name)

                    # We do this so that the superclass works correctly.
                    self.stage = self.controller

                    self.stage_functionality = TigerStageFunctionality(device_mutex = self.controller_mutex,
                                                                       stage = self.stage,
                                                                       update_interval = 500,
                                                                       velocity = settings.get("velocity", 7.5))
                    self.functionalities[self.module_name + "." + dev_name] = self.stage_functionality

                elif (dev_name == "z_piezo"):
                    self.z_piezo_configuration = devices.get(dev_name)

                elif (dev_name == "z_stage"):
                    settings = devices.get(dev_name)
                    z_stage_fn = TigerZStageFunctionality(device_mutex = self.controller_mutex,
                                                          parameters = settings,
                                                          update_interval = 500,
                                                          velocity = settings.get("velocity", 1.0),
                                                          z_stage = self.controller)
                    self.functionalities[self.module_name + "." + dev_name] = z_stage_fn

                elif (dev_name.startswith("led")):
                    settings = devices.get(dev_name)
                    led_fn = TigerLEDFunctionality(address = settings.get("address"),
                                                   channel = settings.get("channel"),
                                                   device_mutex = self.controller_mutex,
                                                   maximum = 100,
                                                   ttl_mode = configuration.get("ttl_mode", -1),
                                                   led = self.controller)
                    self.functionalities[self.module_name + "." + dev_name] = led_fn

                else:
                    raise halExceptions.HardwareException("Unknown device " + str(dev_name))

        else:
            self.controller = None
    
    def cleanUp(self, qt_settings):
        if self.controller is not None:
            if self.z_piezo_functionality is not None:
                self.z_piezo_functionality.goAbsolute(
                    self.z_piezo_functionality.getMinimum())
            
            for fn in self.functionalities.values():
                if hasattr(fn, "wait"):
                    fn.wait()
            self.controller.shutDown()

    def getFunctionality(self, message):
        if message.getData()["name"] in self.functionalities:
            fn = self.functionalities[message.getData()["name"]]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : fn}))

    def handleResponse(self, message, response):
        if message.isType("get functionality"):
            if (message.getData()["extra data"] == "z_piezo"):
                self.z_piezo_functionality = TigerVoltageZFunctionality(
                    ao_fn = response.getData()["functionality"],
                    parameters = self.z_piezo_configuration.get("parameters"),
                    microns_to_volts = self.z_piezo_configuration.get("microns_to_volts"))
                
                # Configure controller for voltage Z control.
                self.controller_mutex.lock()
                axis = self.z_piezo_configuration.get("axis")
                mode = self.z_piezo_configuration.get("mode")
                self.controller.zConfigurePiezo(axis, mode)
                self.controller_mutex.unlock()
        
                # Add to dictionary of available functionalities.
                self.functionalities[self.module_name + ".z_piezo"] = self.z_piezo_functionality
            
    def processMessage(self, message):
        if message.isType("configure1"):
            if self.z_piezo_configuration is not None:
                self.sendMessage(halMessage.HalMessage(
                    m_type = "get functionality",
                    data = {"name" : self.z_piezo_configuration.get("ao_fn_name"),
                            "extra data" : "z_piezo"}))
            
        elif message.isType("get functionality"):
            self.getFunctionality(message)
            
        #
        # The rest of the message are only relevant if we actually have a XY stage.
        #
        if self.stage_functionality is None:
            return

        if message.isType("configuration"):
            if message.sourceIs("tcp_control"):
                self.tcpConnection(message.getData()["properties"]["connected"])

            elif message.sourceIs("mosaic"):
                self.pixelSize(message.getData()["properties"]["pixel_size"])

        elif message.isType("start film"):
            self.startFilm(message)

        elif message.isType("stop film"):
            self.stopFilm(message)
            
        elif message.isType("tcp message"):
            self.tcpMessage(message)

    def startFilm(self, message):
        super().startFilm(message)
        #
        # Need to use runHardwareTask() here so that we can be sure that the
        # Tiger LED controller will be in the correct state before we start
        # filming.
        #
        if (message.getData()["film settings"].runShutters()):
            hardwareModule.runHardwareTask(self, message, self.startLED)

    def startLED(self):
        #
        # Set TTL mode for one functionality sets the mode for all functionalities,
        # assuming there is only a single LED driver card.
        #
        set_ttl = False
        for fn_name in self.functionalities:
            if ("led" in fn_name):
                if not set_ttl:
                    self.functionalities[fn_name].setFilmTTLMode(True)
                    set_ttl = True
                self.functionalities[fn_name].setFilmPower()
                    
    def stopFilm(self, message):
        super().stopFilm(message)
        hardwareModule.runHardwareTask(self, message, self.stopLED)

    def stopLED(self):
        for fn_name in self.functionalities:
            if ("led" in fn_name):
                self.functionalities[fn_name].setFilmTTLMode(False)
                break
