#!/usr/bin/env python

import getopt
import os
import string
import struct
import sys
import time

class Decoder:
    def __init__(self, files, debug=False):
        self.debug = debug
        self.header = b"\0\0\x80\0freeGPS X\0\0\0" + 32 * b"\0"
        self.files = files
        self.fd = None

    def decode_init(self, fname):
        fd = os.open(fname, os.O_RDONLY)
        self.fd = fd
        st = os.fstat(fd)
        buf = os.read(fd, 0x2000)
        i = buf.index(b"mdat")
        os.lseek(fd, i + struct.unpack_from(">I", buf, i - 4)[0], os.SEEK_SET)
        buf = os.read(fd, 0x100)
        creation_time, = struct.unpack_from(">I", buf, buf.index(b"mvhd") + 8)
        creation_time -= 24 * 60 * 60 * (66 * 365 + 17) # offset from epoch
        self.tm = time.gmtime(creation_time)

        # read GPS tag locations
        os.lseek(fd, st.st_size - 0x8000, os.SEEK_SET)
        buf = os.read(fd, 0x8000)
        i = buf.index(b"pgps")
        bbuf = buf[i + 5:] # len("pgps ")
        foo, count = struct.unpack_from(">II", bbuf)
        self.offsets = []
        for o in range(8, len(bbuf), 8):
            offs, sz = struct.unpack_from(">II", bbuf, o)
            if sz != 0x8000:
                raise ValueError(sz)
            self.offsets.append(offs)

    def decode_data(self):
        for f in self.files:
            try:
                self.decode_init(f)
            except Exception as e:
                if self.debug:
                    raise(e)
                print(repr(e), file=sys.stderr)
                continue
                
            for o in self.offsets:
                os.lseek(self.fd, o, os.SEEK_SET)
                buf = os.read(self.fd, 0x80)
                if buf[0:0x30] != self.header:
                    raise ValueError("header incorrect: %s" % repr(buf))
                # 0 0 0 0 hour min
                hh, mm, ss, yy, mon, day = struct.unpack_from("<IIIIII", buf, 0x30)

                # lat lon speed dir
                v = struct.unpack_from("<ffff5i", buf, 0x4c)
            
                yield ((yy + 2000, mon, day, hh, mm, ss, 0, 0, 0), *v, buf[0x48:0x4b].decode('ascii'), buf[0x5c:])

            os.close(self.fd)

    def decode(self):
        print("# " + time.strftime("%Y-%m-%dT%H:%M:%SZ", self.tm))
        for d in self.decode_data():
            # XXX
            vc = list(struct.unpack_from("28B", d[-1]))
            while len(vc) and vc[-1] == 0:
                del vc[-1]
            print(time.strftime("%Y-%m-%d %H:%M:%S ", d[0]) + "%f %f %f %f %d %d %d %d %d %s\t#" % d[1:-1] + " ".join(["%02x" % d for d in vc]))
        
    def output_gpx(self):
        # header
        print("""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>

<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <trk>""")

        in_trkseg = False
        for tp in self.decode_data():
            if not in_trkseg:
                if tp[-2] != 'A00':
                    in_trkseg = True
                    print("    <trkseg>")
                else:
                    continue
            else:
                if tp[-2] == 'A00':
                    in_trkseg = False
                    print("    </trkseg>")
                    continue
            lat = int(tp[1] / 100)
            lat += (tp[1] - lat * 100) / 60
            lon = int(tp[2] / 100)
            lon += (tp[2] - lon * 100) / 60
            print('      <trkpt lat="%f" lon="%f">\n        <time>%s</time>\n      </trkpt>' %
                  (lat, lon, time.strftime("%Y-%m-%dT%H:%M:%SZ", tp[0])))
        if in_trkseg:
            print("    </trkseg>")
        print("  </trk>\n</gpx>")
        
        
if __name__ == '__main__':
    optlist, args = getopt.getopt(sys.argv[1:], 'dx')
    debug = False
    use_gpx = False
    for o, a in optlist:
        if o == '-d':
            debug = True
        elif o == '-x':
            use_gpx = True

    try:
        d = Decoder(args)
        if use_gpx:
            d.output_gpx()
        else:
            d.decode()
    except Exception as e:
        print(e)

