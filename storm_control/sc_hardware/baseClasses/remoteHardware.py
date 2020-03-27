#!/usr/bin/env python
"""
The core functionality for controlling remote hardware
using HAL. Communication is done using zmq PAIR sockets.

Note: 
1. This uses pickle so it isn't safe.
2. There is no support for remote modules being able to
   send messages to HAL.

Hazen 03/20
"""
import pickle
import zlib
import zmq

from PyQt5 import QtCore

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule


#
# This was copied from pyzmq/examples/serialization.
#
class SerializingSocket(zmq.Socket):
    """A class with some extra serialization methods
    
    send_zipped_pickle is just like send_pyobj, but uses
    zlib to compress the stream before sending.
    
    send_array sends numpy arrays with metadata necessary
    for reconstructing the array on the other side (dtype,shape).
    """    
    def send_zipped_pickle(self, obj, flags=0, protocol=-1):
        """pack and compress an object with pickle and zlib."""
        pobj = pickle.dumps(obj, protocol)
        zobj = zlib.compress(pobj)
        return self.send(zobj, flags=flags)
    
    def recv_zipped_pickle(self, flags=0):
        """reconstruct a Python object sent with zipped_pickle"""
        zobj = self.recv(flags)
        pobj = zlib.decompress(zobj)
        return pickle.loads(pobj)

    def send_array(self, A, flags=0, copy=True, track=False):
        """send a numpy array with metadata"""
        md = dict(
            dtype = str(A.dtype),
            shape = A.shape,
        )
        self.send_json(md, flags|zmq.SNDMORE)
        return self.send(A, flags, copy=copy, track=track)

    def recv_array(self, flags=0, copy=True, track=False):
        """recv a numpy array"""
        md = self.recv_json(flags=flags)
        msg = self.recv(flags=flags, copy=copy, track=track)
        A = numpy.frombuffer(msg, dtype=md['dtype'])
        return A.reshape(md['shape'])


class SerializingContext(zmq.Context):
    _socket_class = SerializingSocket


class RemoteHardwareClientModule(hardwareModule.HardwareModule):
    """
    The base client class, this is the HAL side of the communication. Each
    piece of remote hardware functions as a server.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):

        super().__init__(**kwds)
        
        self.context = SerializingContext()
        self.socket = self.context.socket(zmq.PAIR)
        print(">", module_params.get("configuration").get("ip_address"))
        self.socket.connect(module_params.get("configuration").get("ip_address"))

    def cleanUp(self, qt_settings):
        self.socket.send_zipped_pickle("close event")

    def processMessage(self, message):
        
        r_message = RemoteMessage(hal_message = message)

        # Send message.
        self.socket.send_zipped_pickle(r_message)

        # Remote worker responds with whether or not it can process
        # the message immediately or we need to wait.
        resp = self.socket.recv()

        if (resp == "wait"):
            # TODO, handle waits.
            pass
        
        else:
            # Get message with responses (if any).
            r_message = self.socket.recv_zipped_pickle()

            # Add responses to message. Note that response will be
            # of type RemoteMessage().
            #
            for elt in r_message.responses:
                message.addResponse(elt)


class RemoteHardwareServer(QtCore.QThread):
    """
    QThread for the remote side of the communication.
    """
    def __init__(self, ip_address = None, module = None, **kwds):
        super().__init__(**kwds)

        self.context = SerializingContext()
        self.socket = self.context.socket(zmq.PAIR)
        self.socket.bind(ip_address)

        self.module = module
        self.module.sendResponse.connect(self.handleSendResponse)
        self.module.sendWait.connect(self.handleSendWait)
            
        self.start(QtCore.QThread.NormalPriority)
        
    def handleSendResponse(self, r_message):
        self.socket.send_zipped_pickle(r_message)
        
    def handleSendWait(self, wait):
        if wait:
            self.socket.send_string("wait")
        else:
            self.socket.send_string("done")
        
    def run(self):
        while True:
            r_message = self.socket.recv_zipped_pickle()
            self.module.newMessage(r_message)

    
class RemoteHardwareServerModule(QtCore.QObject):
    """
    The base server class module. 

    Remote hardware should sub-class this and override processMessage().
    """
    sendResponse = QtCore.pyqtSignal(object)
    sendWait = QtCore.pyqtSignal(bool)
    
    def __init__(self, **kwds):
        super().__init__(**kwds)

    def cleanUp(self):
        print("close event")

    def newMessage(self, r_message):
        if isinstance(r_message, str):
            if (r_message == "close event"):
                self.cleanUp()
        else:
            self.processMessage(r_message)
                
    def processMessage(self, r_message):
        self.sendWait.emit(False)
        self.sendResponse.emit(r_message)


class RemoteMessage(object):
    """
    This is a HalMessage stripped down to the point where it can be 
    passed through a TCP/IP socket. Basically this means no Qt
    objects.
    """
    def __init__(self, hal_message = None, **kwds):

        self.data = {}
        if hal_message.data is not None:
            for key in hal_message.data:
                val = hal_message.data[key]
                if not isinstance(val, QtCore.QObject):
                    self.data[key] = val

        self.m_id = hal_message.m_id
        self.m_type = hal_message.m_type
        self.responses = []
        self.source_name = hal_message.source.module_name

    def addResponse(self, hal_message_response):
        self.responses.append(hal_message_response)
                    
    def getData(self):
        return self.data

    def getSourceName(self):
        return self.source_name

    def isType(self, m_type):
        return (self.m_type == m_type)

    def sourceIs(self, source_name):
        return (source_name == self.source.module_name)
