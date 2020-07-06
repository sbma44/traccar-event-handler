import sys
import server
from local_settings import *
from io import BytesIO as IO
import json
import gzip
import re
import os

def iterable(obj):
    try:
        iter(obj)
    except Exception:
        return False
    else:
        return True

def assert_iterables_equal(a, b):
    assert len(a) == len(b)
    for i, x in enumerate(a):
        assert a[i] == b[i]

re_GET = re.compile(r'"(GET .*?) HTTP/[\d\.]+"')
re_time = re.compile(r'deviceTime=(\d+)&')

class FixtureChecker(object):
    def _blank(*args, **kwargs):
        return None

    def __init__(self, name, methodname, returnfunc=None):
        self.name = name
        if methodname is not None:
            setattr(self, methodname, self.call)
        self.returnfunc = returnfunc or self._blank
        self.iteration = 0
        self.UPDATE = not not os.environ.get('UPDATE', False)
        if self.UPDATE:
            self.fixture = []
        else:
            with open('test/fixture-{}.json'.format(self.name), 'r') as f:
                self.fixture = json.load(f)

    def call(self, *args, **kwargs):
        # don't store stuff that can't be serialized
        new_args = []
        for i, a in enumerate(args):
            new_args.append(a)
            try:
                json.dumps(a)
            except:
                new_args[i] = str(type(a))
        for k in kwargs.keys():
            try:
                json.dumps(kwargs[k])
            except:
                kwargs[k] = str(type(kwargs[k]))

        args = new_args

        if self.UPDATE:
            self.fixture.append([args, kwargs])
        else:
            assert self.iteration < len(self.fixture), "got stub call not in recorded fixture"
            if iterable(args) and iterable(self.fixture[self.iteration][0]):
                assert_iterables_equal(args, self.fixture[self.iteration][0])
            else:
                assert args == self.fixture[self.iteration][0]

            assert kwargs == self.fixture[self.iteration][1]

        self.iteration += 1
        return self.returnfunc(*args, **kwargs)

    def finish(self):
        with open('test/fixture-{}.json'.format(self.name), 'w') as f:
            json.dump(self.fixture, f, indent=2)



class MockRequest(object):
        def __init__(self, path, *args, **kwargs):
            self.path = path

        def makefile(self, *args, **kwargs):
            return IO(bytes(self.path, 'utf-8'))

        def sendall(self, *args, **kwargs):
            pass

def test_get_handler():
    server.pushover_client = FixtureChecker('pushover', 'send_message')
    server.mqtt_client = FixtureChecker('mqtt', 'publish')
    server.s3_client = FixtureChecker('s3', 'upload_fileobj')

    static_checker = FixtureChecker('mapbox_static', None, lambda lon, lat: open('test/traccar-map-1593808896.1329181.png', 'rb'))
    server.fetch_static_map = static_checker.call

    geocode_checker = FixtureChecker('mapbox_geocode', None, lambda lon, lat: 'at 100 Fake Street')
    server.fetch_geocode = geocode_checker.call

    class TimeStub:
        t = 0
        @staticmethod
        def time():
            return TimeStub.t
    server.time = TimeStub

    with gzip.open('test/traccar-logs.txt.gz') as f:
        for line in f:
            m_time = re_time.search(line.decode('utf-8'))
            m = re_GET.search(line.decode('utf-8'))
            if m and m_time:
                TimeStub.t = float(m_time.group(1)) / 1000
                gh = server.GetHandler(MockRequest(m.group(1)), '0.0.0.0', None)

    if not not os.environ.get('UPDATE', False):
        server.pushover_client.finish()
        server.mqtt_client.finish()
        server.s3_client.finish()
        static_checker.finish()
        geocode_checker.finish()