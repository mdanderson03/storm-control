#!/usr/bin/env python
"""
The core functionality for controlling remote hardware
using HAL. Communication is done using zmq PAIR sockets.

Examples:
1. sc_hardware/none/noneRemoteModule.
2. sc_hardware/baseClasses/remoteCamera.

Note: 
1. This uses pickle so it isn't safe.

Hazen 03/20
"""
import pickle
import zlib
import zmq

from PyQt5 import QtCore

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule


def sanitizeData(new_data, old_data):
    """
    Create new_data from old_data recursively removing QObjects.
    """
    for key in old_data:
        val = old_data[key]
        if isinstance(val, dict):
            new_data[key] = {}
            sanitizeData(new_data[key], old_data[key])
        else:
            if not isinstance(val, QtCore.QObject):
                new_data[key] = val


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


class RemoteHardwareModule(hardwareModule.HardwareModule):
    """
    This is the HAL side of the communication.
    """
    def __init__(self, module_params = None, **kwds):
        super().__init__(**kwds)
        
        self.hal_message = None

        # This socket is used for sending messages from HAL to the remote hardware.
        #
        self.context_remote = SerializingContext()
        self.socket_remote = self.context_remote.socket(zmq.PAIR)
        self.socket_remote.connect(module_params.get("configuration").get("ip_address_remote"))

        # This socket is queried for messages from the remote hardware.
        #
        self.context_hal = SerializingContext()
        self.socket_hal = self.context_hal.socket(zmq.PAIR)
        self.socket_hal.bind(module_params.get("configuration").get("ip_address_hal"))

        # The poller and timer are used to periodically check for messages
        # from the remote hardware. Using QTimer so that we don't consume
        # threads unnecessarily.
        #
        self.poller = zmq.Poller()
        self.poller.register(self.socket_hal, zmq.POLLIN)
        
        self.check_message_timer = QtCore.QTimer(self)
        self.check_message_timer.setInterval(50)
        self.check_message_timer.timeout.connect(self.handleCheckMessageTimer)
        self.check_message_timer.start()

    def cleanUp(self, qt_settings):
        self.socket_remote.send_zipped_pickle("close event")

    def cleanUpRemote(self, r_message):
        """
        Call this if r_message is delayed response to a HAL message. This
        is similar to handleWorkerDone() and cleanUpWorker()
        """
        for elt in r_message.responses:
            self.hal_message.addResponse(elt)
        self.hal_message.decRefCount(name = self.module_name)
        self.hal_message = None
        self.worker = None
            
        # Start the timer if we still have messages left.
        if (len(self.queued_messages) > 0):
            self.queued_messages_timer.start()

    def createRemoteMessage(self, message):
        """
        Use this to change default conversion from HalMessage
        to RemoteHALMessage.
        """
        return RemoteHALMessage(hal_message = message)

    def copyResponses(self, r_message, hal_message):
        """
        This copies the responses from the remote message to the HAL 
        message. It also fixes the source module name, which might
        not be set correctly depending on the remote module.
        """
        for elt in r_message.getResponses():
            elt.source = self.module_name
            hal_message.addResponse(elt)

    def handleCheckMessageTimer(self):
        """
        Check for messages from the remote process. We'll process all of
        them at once in the order that they are received.
        """
        messages = True
        r_messages = []

        while messages:
            socks = dict(self.poller.poll(1))
            if (self.socket_hal in socks) and (socks[self.socket_hal] == zmq.POLLIN):
                r_messages.append(self.socket_hal.recv_zipped_pickle())
            else:
                messages = False

        for r_message in r_messages:
            self.remoteMessage(r_message)
        
    def processMessage(self, message):
        """
        This passes a reduced version of the message from HAL to the 
        remote hardware. You probably don't want to change this. You
        can use createRemoteMessage() to change how (local) HAL messages
        are converted into messages that are TCP/IP compatible.
        """
        # The problem is that we can't pass Qt objects so we have to reduce
        # them to pure Python objects first.
        #
        # Create a remote message from a HAL message.
        #
        r_message = self.createRemoteMessage(message)
        
        # Send the message.
        #
        self.socket_remote.send_zipped_pickle(r_message)

        # Remote worker responds with updated r_message if it can process
        # the message immediately. Otherwise it responds with something
        # else, usually the string "wait".
        #
        resp = self.socket_remote.recv_zipped_pickle()

        if isinstance(resp, RemoteHALMessage):
            self.copyResponses(resp, message)

        else:

            # Increment message reference count and keep a reference to
            # the message.
            message.incRefCount()
            self.hal_message = message
        
            # Pretend we are doing something.
            assert (self.worker is None)
            self.worker = True

    def remoteMessage(self, r_message):
        """
        These come from the remote process.
        """
        # Check if this is a delayed response to a HAL message.
        #
        if isinstance(r_message, RemoteHALMessage):
            self.copyResponses(r_message, self.hal_message)

            self.hal_message.decRefCount()
            self.hal_message = None
            self.worker = None
            
            # Start the timer if we still have messages left.
            if (len(self.queued_messages) > 0):
                self.queued_messages_timer.start()

        # All other messages are ["name", data]
        elif isinstance(r_message, list):

            # Handle 'sendMessage' from remote hardware.
            if (r_message[0] == 'sendMessage'):
                msg = halMessage.HalMessage(m_type = r_message[1].m_type,
                                            data = r_message[1].data)
                self.sendMessage(msg)


class RemoteHardwareServer(QtCore.QObject):
    """
    QObject for the remote side of the communication.
    """
    def __init__(self, ip_address_hal = None, ip_address_remote = None, module = None, **kwds):
        super().__init__(**kwds)

        # This socket is used to send messages to HAL.
        #
        self.context_hal = SerializingContext()
        self.socket_hal = self.context_hal.socket(zmq.PAIR)
        self.socket_hal.connect(ip_address_hal)

        # This socket is used to receive messages from HAL.
        #
        self.context_remote = SerializingContext()
        self.socket_remote = self.context_remote.socket(zmq.PAIR)
        self.socket_remote.bind(ip_address_remote)

        # The poller and timer are used to periodically check for messages
        # from HAL.
        #
        self.poller = zmq.Poller()
        self.poller.register(self.socket_remote, zmq.POLLIN)
        
        self.check_message_timer = QtCore.QTimer(self)
        self.check_message_timer.setInterval(10)
        self.check_message_timer.timeout.connect(self.handleCheckMessageTimer)
        self.check_message_timer.start()

        self.module = module
        self.module.sendMessage.connect(self.handleSendMessage)
        self.module.sendResponse.connect(self.handleSendResponse)
        
    def handleCheckMessageTimer(self):
        """
        Check for messages from HAL. These will only come in one at a time.
        """
        socks = dict(self.poller.poll(1))
        if (self.socket_remote in socks) and (socks[self.socket_remote] == zmq.POLLIN):
            r_message = self.socket_remote.recv_zipped_pickle()
            self.module.newMessage(r_message)

    def handleSendMessage(self, message):
        """
        Out of cycle messages to HAL, these should not be RemoteHALMessage objects.
        """
        self.socket_hal.send_zipped_pickle(message)

    def handleSendResponse(self, r_message):
        """
        Response to HAL message, r_message is either 'wait' or a RemoteHALMessage.
        """
        self.socket_remote.send_zipped_pickle(r_message)

    
class RemoteHardwareServerModule(QtCore.QObject):
    """
    HALModule like object for remote hardware.
    """
    sendMessage = QtCore.pyqtSignal(object)
    sendResponse = QtCore.pyqtSignal(object)
    
    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.r_message = None

    def cleanUp(self):
        print("close event")
        
    def holdMessage(self, r_message):
        """
        Hold a HAL message for processing, pair calls to this
        with calls to releaseMessageHold()
        """
        assert (self.r_message is None)
        
        self.r_message = r_message
        self.sendResponse.emit("wait")

    def newMessage(self, r_message):
        if isinstance(r_message, str):
            if (r_message == "close event"):
                self.cleanUp()
        elif isinstance(r_message, RemoteHALMessage):
            self.processMessage(r_message)
        else:
            self.processMessageOther(r_message)

    def processMessage(self, r_message):
        """
        Override this to process HAL messages.
        """
        self.sendResponse.emit(r_message)

    def processMessageOther(self, r_message):
        """
        Override this to other kinds of messages from the client.
        """
        pass

    def releaseMessageHold(self):
        """
        Release (remote) HAL message. Use sendMessage signal because
        this is now technically 'out of cycle'.
        """
        self.sendMessage.emit(self.r_message)
        self.r_message = None


class RemoteHALMessage(object):
    """
    This is a HalMessage stripped down to the point where it can be 
    passed through a TCP/IP socket. Basically this means no Qt
    objects.
    """
    def __init__(self, hal_message = None, **kwds):

        self.data = {}
        if hal_message.data is not None:
            sanitizeData(self.data, hal_message.data)

        self.m_id = hal_message.m_id
        self.m_type = hal_message.m_type
        self.responses = []
        self.source_name = hal_message.source.module_name

    def addResponse(self, hal_message_response):
        self.responses.append(hal_message_response)
                    
    def getData(self):
        return self.data

    def getResponses(self):
        return self.responses

    def getSourceName(self):
        return self.source_name

    def isType(self, m_type):
        return (self.m_type == m_type)

    def sourceIs(self, source_name):
        return (source_name == self.source_name)
