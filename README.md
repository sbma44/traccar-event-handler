# Traccar Event Handler

[![sbma44/traccar-event-handler](https://circleci.com/gh/sbma44/traccar-event-handler.svg?style=svg)](https://app.circleci.com/pipelines/github/sbma44/traccar-event-handler)

[Traccar](https://www.traccar.org/) is a sophisticated open source GPS tracking platform. It is the product of years of development, supports a vast variety of GPS hardware, and is suitable for fleet management.

But I didn't need most of that. I just wanted a replacement for my discontinued Automatic adapter. I want push notifications for when my car stops and starts, plus maybe a little extra fun stuff for my hardware hacking hobby. Traccar proved to be opaque to configure for these purposes. And Traccar is written in Java, a language I haven't touched in two decades.

This project is a simple answer to that problem. It takes advantage of Traccar's forwarding capabilities: Traccar remains responsible for receiving and decoding GPS events from your hardware, but then forwards activity to this script, which runs a modest local webserver to interpret those events and take action.

Note that I have not bothered with some obvious functionality--for instance, an MQTT server is expected; this function can't be disabled. Making it optional would be easy! [Open an issue](https://github.com/sbma44/traccar-event-handler/issues/new/choose) if you need that or something else.

# Features
- Detect start and stop events based on motion (my adapter doesn't recognize ignition events)
- Send pushover notifications with static map images from the Mapbox static image API
- Publish move/stop events to an MQTT server
- Reverse geocode street address (via Mapbox) on stop events
- Upload GeoJSON traces to Amazon S3

# Installation & Use
`traccar.xml` includes the Traccar configuration settings necessary to forward events and location updates to this script. Add them to your own Traccar config and restart the server.

You will need to install the Python 3 dependencies listed in `requirements.txt` with a `pip3 install -r requirements.txt`. It's best to do this in a [venv environment](https://docs.python.org/3/library/venv.html).

To get this script running automatically at boot on a modern Linux system, you will need to configure a systemd service. `traccar-event-handler.service` is an example systemd service file that you can use for this purpose. [Here is a tutorial showing associated systemd basics](https://www.linode.com/docs/quick-answers/linux/start-service-at-boot/).

Note that the service file uses a python executable in a venv tree. Be sure to edit this to reflect your own venv location.

# Configuration
Please have a look at `local_settings.py.example`--remove the `.example` suffix and fill out with your API keys.

# Tests
There are some tests! Specifically, there is a day's worth of logs that is replayed against the script with stubs for the external API calls. The arguments received in calls to these stubs are checked against fixture files.

Please note that I use a Sinotrack ST-902 adapter with default settings (aside from my Traccar server endpoint, of course). I have not tested this code with any others, but expect the HTTP GETs emitted by Traccar to be similar enough to work.

The API calling code is not tested to avoid network requests or the need to include credentials in the test runner.

Finally, note that the GPS coordinates embedded in the test fixtures have been shifted to a different metro area. This is not enough to make me anonymous, but probably enough to make other OSINT sources better options for figuring out where I live.