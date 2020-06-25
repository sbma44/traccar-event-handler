from http.server import BaseHTTPRequestHandler
import time
from urllib import parse
from urllib.parse import unquote, urlparse, parse_qs
import json
from pushover import Client

try:
    from local_settings import *
except:
    pass

first_stop = None

pushover_client = Client(PUSHOVER_USER, api_token=PUSHOVER_TOKEN)
pushover_client.send_message('traccar event handler started')

def decode_GET(qs):
    d = parse_qs(qs)
    new_d = {}
    for k in d:
        if k == 'attributes':
            new_d[k] = json.loads(d[k][0])
        elif type(d[k]) is list and len(d[k]) == 1:
            new_d[k] = d[k][0]
    if 'speed' in new_d:
        new_d['speed_kph'] = float(new_d['speed'])
        new_d['speed_mph'] = float(new_d['speed']) * 0.621371
        del new_d['speed']
    return new_d

class GetHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        global first_stop
        msg = decode_GET(self.path)
        if msg.get('speed_mph') > 3:
            # if we've been stopped for >5m, send a push message
            if first_stop is not None and time.time() - first_stop > 300:
                client.send_message('motion detected (DIY)')
            first_stop = None
        elif first_stop is None:
            first_stop = time.time()

        with open('GET.log', 'a') as f:
            f.write(str(time.time()) + ',' + json.dumps(msg) + '\n')

        self.send_response(200)
        self.send_header("Content-Type", "text/ascii")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write("OK".encode("utf-8"))

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))

        msg = json.loads(body)
        event_type = msg.get('event', {}).get('type')
        if not event_type in ('deviceOnline', 'deviceOffline'):
            pushover_client.send_message('traccar event: {}'.format(event_type))
            with open('POST_{}_'.format(event_type) + str(time.time()) + '.txt', 'w') as f:
                f.write(body.decode('utf-8'))

        self.send_response(200)
        self.send_header("Content-Type", "text/ascii")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write("OK".encode("utf-8"))



if __name__ == '__main__':
    from http.server import HTTPServer
    server = HTTPServer(('0.0.0.0', 3080), GetHandler)
    print('Starting server, use <Ctrl-C> to stop')
    server.serve_forever()

