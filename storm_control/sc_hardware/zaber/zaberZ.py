#!/usr/bin/env python
"""
RS232 interface to a Zaber Z stage.

Hazen 04/17
Jeff 09/21
"""
import traceback

import storm_control.sc_hardware.serial.RS232 as RS232
import storm_control.sc_library.hdebug as hdebug

class ZaberZRS232(RS232.RS232):
    """
    ZaberZ stage RS232 interface class.  This class allows for a coarse and fine z position, with the fine z position relative to the coarse position.
	This approach allows the stage to be used for coarse focusing and for the fine focusing of the autofocus system.
    """
    def __init__(self, **kwds):
        """
        Connect to the Zaber Z stage at the specified port.
        """
        self.live = True
        self.unit_to_um = kwds["unit_to_um"]
        self.um_to_unit = 1.0/self.unit_to_um
        self.stage_id = kwds["stage_id"]
        self.limits = kwds["limits_dict"]
        self.coarse_position = 0.0

        # We need to remove the keywords not needed for the RS232 super class initialization
        del kwds["stage_id"]
        del kwds["unit_to_um"]
        del kwds["limits_dict"]

        # RS232 stuff
        try:
            super().__init__(**kwds)
            test = self.commWithResp("/")
            if not test:
                self.live = False

        except (AttributeError, AssertionError):
            print(traceback.format_exc())
            self.live = False
            print("Zaber Z Stage is not connected? Stage is not on?")
            print("Failed to connect to the Zaber Z stage at ", kwds["port"])

		# Get the current coarse position
        self.coarse_position = self.getPosition()
        print("  Zaber z stage is starting at " + str(self.coarse_position))

	# Coerce the requested position
    def coerceToLimits(self, z):
		# Coerce values to stage limits
        coerced_value = False
        if z<self.limits["z_min"]:
            z=self.limits["z_min"]
            coerced_value = True
        if z>self.limits["z_max"]:
            z=self.limits["z_max"]
            coerced_value = True
        if coerced_value:
            print("Zaber Z Stage Warning: Requested a move outside of programmed limits")
        return z
    
	# Command a coarse position change AND update the coarse position
    def zMoveCoarse(self, z_in_um):
        
		# Coerce to limits
        z_in_um = self.coerceToLimits(z_in_um)
		
        print(str(z_in_um))
        
		# Convert z to units
        z_in_units = int(round(z_in_um * self.um_to_unit))       
		
		# Send a command to move the z to the absolute position
        response = self.commWithResp("/" + str(self.stage_id) + " move abs " + str(z_in_units))
        response_parts = response.split(" ")
		
        # Check to see if successful, and if so, store the requested coarse_position
        if response_parts[2] == "OK":
            self.coarse_position = z_in_units
        else:
            print("Zaber Z Stage Warning: Coarse movement request not successful")
    
	# Command a fine position change
    def zMoveFine(self, z_in_um):
		# Coerce to limits
        z_in_um = self.coerceToLimits(z_in_um + self.coarse_position)
				
        # Convert z to units
        z_in_units = int(round(z_in_um * self.um_to_unit))       
        
		# Send a command to move the z to the absolute position
        response = self.commWithResp("/" + str(self.stage_id) + " move abs " + str(z_in_units))
        response_parts = response.split(" ")

		# Check to see if successful, and if so, store the requested coarse_position
        if response_parts[2] == "OK":
            print("Zaber Z Stage Warning: Fine movement request not successful")
	
	# Return the absolute position
    def getPosition(self):
        response = self.commWithResp("/" + str(self.stage_id) + " get pos")
        
        response = response.strip()
        response_parts = response.split(" ")
        try:
            sz = float(response_parts[5])
        except ValueError:
            return None
        return sz*self.unit_to_um
	
	# Return the coarse position
    def zPositionCoarse(self):
        return self.coarse_position
	
	# Return the fine position
    def zPositionFine(self):
        return self.getPosition() - self.coarse_position

	# Return if the stage is moving
    def isStageMoving(self):
        response = self.commWithResp("/" + str(self.stage_id))
        
        # Parse the response
        response_parts = response.split(" ")

        # Handle an error response, or an empty response
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"        
        # Parse IDLE/BUSY
        if response_parts[3] == "IDLE":
            return "IDLE"
        else: # BUSY Case
            return "MOVING"

#
# The MIT License
#
# Copyright (c) 2021 Moffitt Lab, Boston Children's Hospital, Harvard Medical School
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
