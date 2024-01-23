import time
import logging
import cv2
import numpy as np

from stvid.config import load_config_section

logger = logging.getLogger(__name__)


class CameraLostFrameError(Exception):
    pass


class NoCameraFoundError(Exception):
    pass


class ConfigError(Exception):
    pass


class ASICamera:
    def __init__(self, device_id, asi_cfg):
        """
        Arguments
        - device_id (int):
        - asi_cfg (ConfigParser.SectionProxy): Config Section 'ASI'
        """
        self.device_id = device_id

        # Parse camera-specific configuration
        keys = [
            ("gain", int),
            ("maxgain", int),
            ("exposure", int),
            ("bin", int),
            ("brightness", int),
            ("bandwidth", int),
            ("high_speed", int),
            ("software_bin", int),
            ("hardware_bin", int),
            ("autogain", bool),
            ("sdk", str),
        ]
        self.cfg = load_config_section('ASI', asi_cfg, keys)

    def _apply_camera_config(self):
        asi = self.asi
        cfg = self.cfg

        self.camera.disable_dark_subtract()

        control_values = [
            ("ASI_BANDWIDTHOVERLOAD", cfg["bandwidth"]),
            ("ASI_BRIGHTNESS", cfg["brightness"]),
            ("ASI_AUTO_MAX_GAIN", cfg["maxgain"]),
            ("ASI_AUTO_MAX_BRIGHTNESS", 20),
            ("ASI_WB_B", 99),
            ("ASI_WB_R", 75),
            ("ASI_GAMMA", 50),
            ("ASI_FLIP", 0),
        ]
        for asi_key, value in control_values:
            self.camera.set_control_value(getattr(asi, asi_key), value)

        control_values_with_auto = [
            ("ASI_GAIN", cfg["gain"], cfg["autogain"]),
            ("ASI_EXPOSURE", cfg["exposure"], False),
        ]
        for asi_key, value, auto_value in control_values_with_auto:
            self.camera.set_control_value(getattr(asi, asi_key), value, auto=auto_value)

        control_values_optional = [
            ("ASI_HIGH_SPEED_MODE", cfg["high_speed"]),
            ("ASI_HARDWARE_BIN", cfg["hardware_bin"]),
        ]
        for asi_key, value in control_values_optional:
            try:
                self.camera.set_control_value(getattr(asi, asi_key), value)
            except self.asi.ZWO_IOError:
                pass

        self.camera.set_roi(bins=cfg["bin"])

    def initialize(self):
        """
        Initialize the camera.

        Raises
        NoCameraFoundError
        """
        import zwoasi as asi

        self.asi = asi

        # Initialize device
        self.asi.init(self.cfg["sdk"])

        num_cameras = self.asi.get_num_cameras()
        if num_cameras == 0:
            raise NoCameraFoundError("No ZWOASI cameras found")

        cameras_found = self.asi.list_cameras()  # Models names of the connected cameras

        if num_cameras == 1:
            device_id = 0
            logger.info("Found one camera: %s" % cameras_found[0])
        else:
            logger.info("Found %d ZWOASI cameras" % num_cameras)
            for n in range(num_cameras):
                logger.info("    %d: %s" % (n, cameras_found[n]))
            device_id = self.device_id
            logger.info("Using #%d: %s" % (device_id, cameras_found[device_id]))

        self.camera = self.asi.Camera(device_id)

        # Debug Logging
        camera_info = self.camera.get_camera_property()
        logger.debug("ASI Camera info:")
        for key, value in camera_info.items():
            logger.debug("  %s : %s" % (key, value))

        self._apply_camera_config()
        self.camera.start_video_capture()
        self.camera.set_image_type(asi.ASI_IMG_RAW8)

        if self.cfg["autogain"]:
            self.fix_autogain()

    def fix_autogain(self):
        """
        Capture frames repeatedly until the gain reported by the camera is constant.
        """
        gain = self.cfg["gain"]
        while True:
            # Get frame
            _ = self.camera.capture_video_frame()

            # Break on no change in gain
            new_settings = self.camera.get_control_values()
            if gain == new_settings["Gain"]:
                break

            gain = new_settings["Gain"]
            self.camera.set_control_value(self.asi.ASI_GAIN, gain, auto=True)

        # Update config with new gain
        self.cfg["gain"] = gain

    def apply_autogain(self):
        # Get settings
        settings = self.camera.get_control_values()
        gain = settings["Gain"]
        temp = settings["Temperature"] / 10
        logger.info("Capturing frame with gain %d, temperature %.1f" % (gain, temp))

        # Set gain
        if self.cfg["autogain"]:
            self.camera.set_control_value(self.asi.ASI_GAIN, gain, auto=True)

    def get_frame(self):
        # Store start time
        t0 = float(time.time())

        # Get frame
        z = self.camera.capture_video_frame()

        # Apply software binning
        if self.cfg["software_bin"] != 0:
            my, mx = z.shape
            z = cv2.resize(
                z, (mx // self.cfg["software_bin"], my // self.cfg["software_bin"])
            )

        # Compute mid time
        t = (float(time.time()) + t0) / 2
        return z, t

    def close(self):
        self.camera.stop_video_capture()
        self.camera.close()


class CV2Camera:
    def __init__(self, device_id, cv2_cfg):
        """
        Arguments
        device_id (int):
        cv2_cfg (ConfigParser.SectionProxy): Config Section 'CV2'
        """
        self.device_id = device_id
        keys = [
            ("software_bin", int),
        ]
        self.cfg = load_config_section('CV2', cv2_cfg, keys)

    def initialize(self):
        """
        Initialize the camera.

        Raises
        NoCameraFoundError
        """
        # Initialize cv2 device
        self.device = cv2.VideoCapture(self.device_id)
        # TODO: Support software binning!
        # # Set properties
        # self.device.set(cv2.CAP_PROP_FRAME_WIDTH, self.nx * self.software_bin)
        # self.device.set(cv2.CAP_PROP_FRAME_HEIGHT, self.ny * self.software_bin)

    def get_frame(self):
        # Store start time
        t0 = float(time.time())

        # Get frame
        _, frame = self.device.read()

        # Compute mid time
        t = (float(time.time()) + t0) / 2

        # Convert image to grayscale
        z = np.asarray(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)).astype(np.uint8)

        # Apply software binning
        if self.cfg["software_bin"] != 0:
            my, mx = z.shape
            z = cv2.resize(
                z, (mx // self.cfg["software_bin"], my // self.cfg["software_bin"])
            )

        return z, t

    def close(self):
        self.device.release()

    @staticmethod
    def print_config_hint(device_id):
        device = cv2.VideoCapture(device_id)
        width = device.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = device.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = device.get(cv2.CAP_PROP_FPS)
        device.release()

        logger.error(f'The connected camera has following dimensions: (nx, ny) = (%d, %d)', width, height)
        logger.error(f'For approximately 10 s captures derived from %d FPS, set nz = %d or less', fps, 10_000 / fps)

    def apply_autogain(self):
        pass
