from prometheus_client import Gauge


class AcquisitionMainMetrics:
    """
    Metrics exported by the stvid-acquire main process
    """
    def __init__(self):
        self.acquisition_status = Gauge(
            'stvid_acquisition_status',
            'Current status of acquisition (1=running, 0=stopped)'
        )
        self.shutter_state = Gauge(
            'stvid_shutter_state',
            'Current position of shutter (1=open, 0=closed)'
        )
