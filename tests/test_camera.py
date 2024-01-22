#!/usr/bin/env python3
import pytest
import sys
import configparser
from stvid.camera import ASICamera, NoCameraFoundError, ConfigError
from pprint import pprint


def pprint_cfg(cfg):
    """
    Pretty-print a ConfigParser.SectionProxy object
    """
    cfg_dict = {}
    for section in cfg.sections():
        cfg_dict[section] = {}
        for key, val in cfg.items(section):
            cfg_dict[section][key] = val

    pprint(cfg_dict)

@pytest.fixture
def stvid_cfg():
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    _ = cfg.read("tests/configuration.ini")
    return cfg

def test_ASICamera(stvid_cfg):
    camera = ASICamera(device_id=0, asi_cfg=stvid_cfg['ASI'])
    try:
        print('Initialize camera')
        camera.initialize()
    except (NoCameraFoundError, ConfigError) as err:
        print(f'ERROR: {err}')
        pprint_cfg(asi_cfg)
        sys.exit(1)

    try:
        print('Fix autogain')
        camera.fix_autogain()
        for _ in range(2):
            print('Update gain')
            camera.apply_autogain()

            print('Get Frame')
            z, t = camera.get_frame()
    except KeyboardInterrupt:
        print("Stop capture")
    finally:
        camera.close()

if __name__ == '__main__':
    test_ASICamera()
