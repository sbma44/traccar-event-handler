from http.server import BaseHTTPRequestHandler
import os, os.path
import time
import json
from urllib.parse import unquote, urlparse, parse_qs
from math import radians, cos, sin, asin, sqrt, floor

import requests
from pushover import Client
import boto3
from botocore.exceptions import ClientError
import paho.mqtt.client as mqtt

try:
    from local_settings import *
except:
    pass

def fetch_static_map(lon, lat):
    try:
        url = 'https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/pin-l-car+aa0000({},{})/{},{},16,0/300x300@2x?access_token={}'.format(lon, lat, lon, lat, MAPBOX_ACCESS_TOKEN)
        r = requests.get(url, allow_redirects=True)
        if r.status_code == requests.codes.ok:
            return r.content
        else:
            return False

    except Exception as e:
        print('ERROR: {}'.format(str(e)))
        return False

def haversine(e1, e2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    lon1 = float(e1.get('longitude'))
    lat1 = float(e1.get('latitude'))
    lon2 = float(e2.get('longitude'))
    lat2 = float(e2.get('latitude'))

    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return c * r

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

pushover_client = None
s3_client = None
mqtt_client = None

class GetHandler(BaseHTTPRequestHandler):
    traccar_events = []
    traccar_state = 'STOPPED'
    traccar_last_start = None

    # @staticmethod
    # def mqtt_on_connect:
    #     pass

    # @staticmethod
    # def mqtt_on_message:
    #     pass

    # mqtt_client.on_connect = GetHandler.mqtt_on_connect
    # mqtt_client.on_message = GetHandler.mqtt_on_message

    def do_GET(self):
        msg = decode_GET(self.path)
        msg['time'] = time.time()
        GetHandler.traccar_events.append(msg)
        if len(GetHandler.traccar_events) > 24 * 60 * 2:
            GetHandler.traccar_events.pop(0)

        if msg.get('speed_mph', 0) > 3 or ((len(GetHandler.traccar_events) > 1) and (haversine(msg, GetHandler.traccar_events[-2]) > 0.02)):
            print('speed > 3 mph or moved > 20m, checking if car was stopped')
            if GetHandler.traccar_state == 'STOPPED':
                sent_map = False
                if 'latitude' in msg and 'longitude' in msg:
                    fn = fetch_static_map(msg['longitude'], msg['latitude'])
                    if fn:
                        pushover_client.send_message('car is moving', attachment=fn)
                        sent_map = True

                if not sent_map:
                    pushover_client.send_message('car is moving')

                GetHandler.mqtt_client.publish(MQTT_TOPIC + 'moving', 0, retain=True)

                GetHandler.traccar_last_start = time.time()
                GetHandler.traccar_state = 'MOVING'
        else:
            # get events from last 3m
            eligible_events = [e for e in GetHandler.traccar_events if (time.time() - float(e.get('deviceTime', 0))/1000) < 180]

            # find max distance traveled during this period
            max_distance = 0
            if len(eligible_events) > 0:
                last_event = eligible_events[-1]
                for e in eligible_events:
                    max_distance = max(max_distance, haversine(last_event, e))

            print('speed < 3 mph, checking if car has been still -- looks like it moved {} km over {} events'.format(max_distance, len(eligible_events)))
            if len(eligible_events) > 0 and max_distance <= 0.005: # 5 meters
                if GetHandler.traccar_state == 'MOVING':
                    geocode = False
                    geocode_req = requests.get('https://api.mapbox.com/geocoding/v5/mapbox.places/{},{}.json?access_token={}&types=address'.format(msg['longitude'], msg['latitude'], MAPBOX_ACCESS_TOKEN), allow_redirects=True)
                    if geocode_req.status_code == requests.codes.ok:
                        geocode = 'at {}'.format(json.loads(geocode_req.text)['features'][0]['place_name'].replace(', Washington, District of Columbia 20002, United States', '').replace(', United States', '').replace('District of Columbia', 'DC'))

                    duration = False
                    if GetHandler.traccar_last_start is not None:
                        feat = {'type': 'Feature', 'properties': {'stroke': 'blue', 'stroke-width': 5, 'time': []}, 'geometry': {'type': 'LineString', 'coordinates': []}}
                        duration = floor((time.time() - GetHandler.traccar_last_start) / 60)
                        if duration > 60:
                            duration = '(driving {}h{}m)'.format(floor(duration / 60), duration % 60)
                        else:
                            duration = '(driving {}m)'.format(duration)

                        events = [e for e in GetHandler.traccar_events if e['time'] > GetHandler.traccar_last_start and e['time'] < time.time()]
                        for e in events:
                            feat['geometry']['coordinates'].append((float(e['longitude']), float(e['latitude'])))
                            feat['properties']['time'].append(int(e['time']))
                        fn = '/tmp/trip-{}.geojson'.format(int(GetHandler.traccar_last_start))
                        with open(fn, 'w') as f:
                            json.dump(feat, f)
                        upload_success = True
                        try:
                            with open(fn, 'rb') as f:
                                s3_client.upload_fileobj(f, S3_BUCKET, '{}{}'.format(S3_PATH, os.path.basename(fn)))
                        except Exception as e:
                            upload_success = False
                            print('ERROR: {}'.format(str(e)))
                        if upload_success:
                            os.unlink(fn)

                    pushover_msg = ['stopped', geocode, duration]
                    pushover_msg = ' '.join([x for x in pushover_msg if x])

                    sent_map = False
                    if 'latitude' in msg and 'longitude' in msg:
                        fn = fetch_static_map(msg['longitude'], msg['latitude'])
                        if fn:
                            pushover_client.send_message(pushover_msg, attachment=fn)
                            sent_map = True

                    if not sent_map:
                        pushover_client.send_message(pushover_msg)

                    GetHandler.mqtt_client.publish(MQTT_TOPIC + 'moving', 1, retain=True)

                    GetHandler.traccar_last_start = None
                    GetHandler.traccar_state = 'STOPPED'

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
            #with open('POST_{}_'.format(event_type) + str(time.time()) + '.txt', 'w') as f:
            #    f.write(body.decode('utf-8'))

        self.send_response(200)
        self.send_header("Content-Type", "text/ascii")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write("OK".encode("utf-8"))

if __name__ == '__main__':
    pushover_client = Client(PUSHOVER_USER, api_token=PUSHOVER_TOKEN)
    s3_client = boto3.client('s3', region_name=AWS_DEFAULT_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    mqtt_client = mqtt.Client()
    mqtt_client.connect(MQTT_SERVER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    fn = fetch_static_map(-77.0366, 38.8976)
    if fn:
        pushover_client.send_message('traccar event handler started', attachment=fn)
    else:
        pushover_client.send_message('traccar event handler started (maps not working)')

    from http.server import HTTPServer
    server = HTTPServer(('0.0.0.0', 3080), GetHandler)
    print('Starting server, use <Ctrl-C> to stop')
    server.serve_forever()
