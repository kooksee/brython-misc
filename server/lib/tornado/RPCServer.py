import json, inspect
from tornado.websocket import WebSocketHandler
from tornado import gen

def export(f):
    @gen.coroutine
    def async_f(*args, **kwargs):
        raise gen.Return(f(*args,**kwargs))
    async_f.__expose_to_remote = True
    async_f._original_f = f
    return async_f

class RPCService:
    SERVICE_NAME = 'RPCService'

    def __init__(self,server):
        self._server = server
        
    
    def client_disconnected(self):
        pass
    
    def client_connected(self):
        pass

    
class RPCException(Exception):
    def __init__(self,message):
        super(RPCException,self).__init__(message)

class RPCSvcApi:
    TO_ALL = None

    def __init__(self, server, svc):
        self.svc = svc
        self.server = server
    
    def emit(self, event, data):
        self.server._emit(self.svc, event, data)

    def broadcast(self, event, data, target=None):
        self.server._broadcast(self.svc, target, event, data)

    @property
    def client_id(self):
        return self.server._client_id
        
class RPCServer(WebSocketHandler):
    REGISTERED_SERVICES = {}
    ACTIVE_CLIENTS = set()
    LAST_CLIENT_ID = 0
    BROADCAST_GROUPS = {}
    
    @classmethod
    def _generate_client_id(cls):
        ret = cls.LAST_CLIENT_ID
        cls.LAST_CLIENT_ID += 1

    @classmethod
    def _create_broadcast_group(cls,group_id):
        if group_id not in cls.BROADCAST_GROUPS:
            cls.BROADCAST_GROUPS[group_id] = set()

    @classmethod
    def register_service(cls, service_class):
        if not issubclass(service_class,RPCService):
            raise Exception("plugin("+plugin_name+")[service:"+service_class.SERVICE_NAME+"] Services must derive from lib.tornado.RPCService")
        cls.REGISTERED_SERVICES[service_class.SERVICE_NAME] = service_class

    def _subscribe_to_broadcast_group(self,group_id):
        RPCServer.BROADCAST_GROUPS[group_id].add(self)
    
    def __init__(self,*args,**kwargs):
        super(RPCServer,self).__init__(*args,**kwargs)
        self._client_id = RPCServer._generate_client_id()
        self._services = {
            '__system__':self
        }
        self._call_id = 0

    def client_connected(self):
        pass

    def client_disconnected(self):
        pass

    def open(self):
        print("Opening")
        RPCServer.ACTIVE_CLIENTS.add(self)
        
    def _get_service(self,name):
        if name in self._services:
            return self._services[name]
        if name in RPCServer.REGISTERED_SERVICES:
            print("Creating service", name)
            self._services[name] = RPCServer.REGISTERED_SERVICES[name](RPCSvcApi(self,name))
            print("Done Creating service", name)
            return self._services[name]
        else:
            raise RPCException('No such service: ' + str(name))

    @export
    def list_services(self):
        return [ svc.SERVICE_NAME for svc in RPCServer.REGISTERED_SERVICES ]

    @export
    def query_service(self,svc_name):
        print("Starting querying service", svc_name)
        svc = self._get_service(svc_name)
        ret = {}
        for attr in dir(svc):
            try:
                m = getattr(svc,attr)
                if inspect.ismethod(m) and hasattr(m,'__expose_to_remote'):
                    if hasattr(m,'_original_f'):
                        sig = inspect.signature(m._original_f)
                    else:
                        print("No original method???", dir(m))
                        sig = inspect.signature(m)
                    param_list = [ (arg,not param.default == inspect._empty,param.default) for (arg,param) in sig.parameters.items()  ]
                    ret[attr] = []
                    for arg,has_default,default in param_list:
                        if has_default:
                            ret[attr].append((arg,True,default))
                        else:
                            ret[attr].append((arg,False,None))
            except Exception as ex:
                print("Error testing attribute", attr, "Exception:", ex)
        print("Finished querying service", svc_name,"result:",ret)
        return ret

    @gen.coroutine
    def on_message(self, message):
        try:
            print("Received websocket message", message)
            msg = json.loads(message)
            svc_name = msg['service']
            method = msg['method']
            args = msg['args']
            kwargs = msg['kwargs']
            call_id = msg['call_id']
            client_id = msg['client_id']
            svc = self._get_service(svc_name)
            method = getattr(svc,method)
            if hasattr(method,'__expose_to_remote'):
                print("Calling method",msg['method'],"args:",args,"kwargs:",kwargs)
                result = yield method(*args,**kwargs)
            else:
                print("Method",method,"not available")
                raise RPCException("Method not available")
            self.write_message(json.dumps({
                'service':svc_name,
                'type':'return',
                'call_id':call_id,
                'client_id':client_id,
                'result':result
            }))
        except Exception as ex:
            print("Exception:", ex)
            self.write_message(json.dumps({
                    'service':svc_name,
                    'type':'exception',
                    'call_id':call_id,
                    'client_id':client_id,
                    'exception':str(ex)
            }))

    def on_close(self):
        RPCServer.ACTIVE_CLIENTS.remove(self)
        for svc in self._services.values():
            svc.client_disconnected()

    def _emit(self, service, event, event_data):
        self.write_message( {
            'service':service,
            'type':'event',
            'event':event,
            'client_id':None,
            'data':event_data
        })

    def _broadcast(self, service, event, event_data, to=RPCSvcApi.TO_ALL):
        if to == RPCSvcApi.TO_ALL:
            rcpts = RPCServer.ACTIVE_CLIENTS
        else:
            rcpts = RPCServer.BROADCAST_GROUPS[to]

        for client in rcpts:
            client._emit(service,event,event_data)