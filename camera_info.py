#!/usr/bin/env python3
from pprint import pprint

import zwoasi as asi


SDK = '/usr/local/lib/libASICamera2.so'
device_id = 0


if __name__ == '__main__':
    asi.init(SDK)

    cameras_found = asi.list_cameras()
    pprint(cameras_found)

    camera = asi.Camera(device_id)
    camera_info = camera.get_camera_property()

    pprint(camera_info)
