import socketio
import json
import aiohttp
from aiohttp import web
import traceback

from appdaemon.appdaemon import AppDaemon


# socketio handler

class DashStream(socketio.AsyncNamespace):

    def __init__(self, ADStream, path, AD):

        super().__init__(path)

        self.AD = AD
        self.ADStream = ADStream

    async def on_connect(self, sid, data):
        await self.ADStream.on_connect()

    async def on_up(self, sid, data):
        await self.ADStream.on_msg(data)


class ADStream:

    def __init__(self, ad: AppDaemon, app, transport, on_connect, on_msg):

        self.AD = ad
        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()
        self.app = app
        self.transport = transport
        self.on_connect = on_connect
        self.on_msg = on_msg

        if self.transport == "ws":
            self.app['websockets'] = {}
            self.app.router.add_get('/stream', self.wshandler)
        else:
            self.dash_stream = DashStream(self, '/stream', self.AD)
            self.sio = socketio.AsyncServer(async_mode='aiohttp')
            self.sio.attach(self.app)
            self.sio.register_namespace(self.dash_stream)

    async def send_update(self, data):
            try:
                jdata = json.dumps(data)

                if self.transport == "ws":
                    if len(self.app['websockets']) > 0:
                        self.logger.debug("Sending data to {} dashes: {}".format(len(self.app['websockets']), jdata))
                    for ws in self.app['websockets']:
                        if "dashboard" in self.app['websockets'][ws]:
                            self.logger.debug("Found dashboard type {}".format(self.app['websockets'][ws]["dashboard"]))
                            await ws.send_str(jdata)

                else:
                    await self.dash_stream.emit('down', jdata)
            except TypeError as e:
                self.logger.debug('-' * 60)
                self.logger.warning("Unexpected error in JSON conversion for admin console")
                self.logger.debug("Data is: %s", data)
                self.logger.debug("Error is: %s",e)
                self.logger.debug('-' * 60)
            except:
                self.logger.debug('-' * 60)
                self.logger.warning("Admin browser disconnected unexpectedly")
                self.logger.debug('-' * 60)
                self.logger.debug(traceback.format_exc())
                self.logger.debug('-' * 60)

    #@securedata
    async def wshandler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        request.app['websockets'][ws] = {}
        # noinspection PyBroadException
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.on_msg(msg.data)
                    request.app['websockets'][ws]["dashboard"] = msg.data
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.access.info("WebSocket connection closed with exception {}", ws.exception())
        except:
            self.access.debug("WebSocket disconnected")
        finally:
            request.app['websockets'].pop(ws, None)

        return ws

    # Websockets Handler

    async def on_shutdown(self, application):
        for ws in application['websockets']:
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY,
                                message='Server shutdown')

