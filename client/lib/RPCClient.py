import json
from browser import console, websocket
from async import Promise, interruptible
from angular import core as ngcore


class SocketFactory:
    SOCKETS = {}

    @classmethod
    def get_socket(cls, url, new = False):
        if url not in cls.SOCKETS:
            cls.SOCKETS[url] = websocket.WebSocket(url)
            cls.SOCKETS[url].bind('close',cls._on_close)
        return cls.SOCKETS[url]

    @classmethod
    def _on_close(cls,evt):
        pass


class RPCClient:
    _NEXT_CALL_ID = 0
    _NEXT_CLIENT_ID = 0
    STATUS_OPENING_SOCKET = 0
    STATUS_SOCKET_OPEN = 1
    STATUS_QUERYING_SERVICE = 2
    STATUS_READY = 3
    STATUS_CLOSED_SOCKET = 4
    STATUS_ERROR = 5

    @classmethod
    def new_client_id(cls):
        ret = cls._NEXT_CLIENT_ID
        cls._NEXT_CLIENT_ID += 1
        return ret

    @classmethod
    def new_call_id(cls):
        ret = cls._NEXT_CALL_ID
        cls._NEXT_CALL_ID +=1
        return ret

    def _generate_method(self,method_name,svc_name=None):
        if svc_name is None:
            svc_name = self._service_name
        console.log("Generating method ",method_name, " of ", svc_name)

        def remote_call(*args,**kwargs):
            console.log("Calling ",method_name, "self:",self,"*args:",args, "**kwargs",kwargs)

            if not self.status == RPCClient.STATUS_READY:
                if (not self.status == RPCClient.STATUS_QUERYING_SERVICE) or (not svc_name == '__system__'):
                    console.log("STATUS:", self.status, "SVC:", svc_name)
                    raise Exception("Service not in operation:", self.status)

            ret = Promise()
            data = {
                'service':svc_name,
                'method':method_name,
                'args':args,
                'kwargs':kwargs,
                'call_id':RPCClient.new_call_id(),
                'client_id':self._client_id
            }
            self._calls_in_progress[data['call_id']] = ret
            console.log("Sending data:",json.dumps(data))
            self._socket.send(json.dumps(data))
            return ret
        setattr(self,method_name,remote_call)
        return remote_call

    @ngcore.export2js
    def __init__(self, url, service_name):
        console.log("Calling RPCClient init")
        self._url = url
        self._socket = SocketFactory.get_socket(url)
        self._service_name = service_name
        self._calls_in_progress = {}
        self._event_handlers = {}
        self._method_promise = None
        self._client_id = RPCClient.new_client_id()
        self._socket.bind("message", self._on_message)
        self._socket.bind("close",self._on_close)
        if self._socket.readyState == self._socket.OPEN:
            self._status = RPCClient.STATUS_SOCKET_OPEN
            self._on_open()
        elif self._socket.readyState == self._socket.CLOSED or self._socket.readyState == self._socket.CLOSING:
            self._status = RPCClient.STATUS_CLOSED_SOCKET
        else:
            self._status = RPCClient.STATUS_OPENING_SOCKET
            self._socket.bind("open",self._on_open)

        self._generate_method('list_services',svc_name='__system__')
        self._generate_method('query_service',svc_name='__system__')

    def _load_methods(self,methods):
        console.log("Loading methods",methods)
        self._methods = methods
        for m in self._methods.keys():
            self._generate_method(m)
        self._status = RPCClient.STATUS_READY
        handlers = self._event_handlers.get('__on_ready__',[])
        for handler in handlers:
            handler(self)


    @property
    def status(self):
        return self._status

    @property
    def methods(self):
        if self.status == RPCClient.STATUS_READY:
            return list(self._methods.items())
        else:
            return []

    def _on_open(self,evt=None):
        console.log("Web Socket Open, querying service", self._service_name, "STATUS:",self.status)
        self._status = RPCClient.STATUS_QUERYING_SERVICE
        console.log("Transitioning to status:",self.status)
        self._method_promise = self.query_service(self._service_name)
        self._method_promise.then(self._load_methods)


    def _on_close(self,evt):
        self._methods = []
        self._status = RPCClient.STATUS_CLOSED_SOCKET

    def _on_message(self,evt):
        console.log("Web Socket Receiving:", evt)
        msg = json.loads(evt.data)
        if msg['client_id'] is not None:
            if not msg['client_id'] == self._client_id:
                console.log("Not our message:", self._client_id, "!=", msg['client_id'])
                return
        else:
            if not msg['service'] == self._service_name or not msg['service'] == '__system__':
                console.log("Not our message:", self._service_name, "!=", msg['service'])
                return
        console.log("Processing message:", msg)
        if msg['type'] == 'event':
            handlers = self._event_handlers.get(msg['event'],[])
            for handler in handlers:
                handler(msg['data'])
        elif msg['type'] == 'return':
            result_promise = self._calls_in_progress[msg['call_id']]
            del self._calls_in_progress[msg['call_id']]
            console.log("Result:", msg['result'])
            console.log("Finishing call:", result_promise)
            result_promise._finish(msg['result'])
        elif msg['type'] == 'exception':
            result_promise = self._calls_in_progress[msg['call_id']]
            del self._calls_in_progress[msg['call_id']]
            console.log("Finishing call", result_promise)
            result_promise._finish(msg['exception'],status=Promise.STATUS_ERROR)

    def bind(self,event,handler):
        if event in self._event_handlers:
            self._event_handlers[event].append(handler)
        else:
            self._event_handlers[event] = [handler]

    def unbind(self,event,handler):
        if event in self._event_handlers:
            self._event_handlers[event].remove(handler)