import sys, re, os

re_gprmc = re.compile(r'&gprmc=(.*?)&')
re_location = re.compile(r'latitude=([\-\d\.]+)&longitude=([\-\.\d]+)')
offset = float(os.environ['OFFSET']) # choose some number of EPSG:4326 lon degrees to offset real traces

for line in sys.stdin:
    m_gprmc = re_gprmc.search(line)
    m_location = re_location.search(line)
    if m_gprmc and m_location:
        lon = float(m_location.group(2))
        line = line.replace(m_location.group(0), 'latitude={}&longitude={:0.9f}'.format(m_location.group(1), lon + offset))
        line = line.replace(m_gprmc.group(0), '&gprmc=REDACTED&')
        print(line.strip())