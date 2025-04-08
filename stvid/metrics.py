from prometheus_client import Counter, Gauge, Histogram


class TLEMetrics:
    def __init__(self):
        # TLE Update Metrics
        self.tle_update_total = Counter(
            'stvid_tle_updates_total',
            'Total number of TLE update attempts'
        )
        self.tle_update_success = Counter(
            'stvid_tle_updates_success',
            'Number of successful TLE updates'
        )
        self.tle_count = Gauge(
            'stvid_tle_count',
            'Number of TLEs in the catalog'
        )
        self.tle_last_update = Gauge(
            'stvid_tle_last_update_timestamp',
            'Timestamp of last successful TLE update'
        )

class AcquisitionMetrics:
    def __init__(self):
        # Acquisition Metrics
        self.acquisition_status = Gauge(
            'stvid_acquisition_status',
            'Current status of acquisition (1=running, 0=stopped)'
        )
        self.frames_captured = Counter(
            'stvid_frames_captured_total',
            'Total number of frames captured'
        )
        self.fits_files_written = Counter(
            'stvid_fits_files_written_total',
            'Total number of FITS files written'
        )
        self.capture_errors = Counter(
            'stvid_capture_errors_total',
            'Total number of capture errors',
            ['error_type']
        )
        self.disk_usage = Gauge(
            'stvid_storage_bytes',
            'Storage space used by FITS files in bytes'
        )
        self.camera_temperature = Gauge(
            'stvid_camera_temperature_celsius',
            'Current camera temperature in Celsius'
        )
        self.shutter_state = Gauge(
            'stvid_shutter_state',
            'Current position of shutter (1=open, 0=closed)'
        )

class ProcessingMetrics:
    def __init__(self):
        # Processing Metrics
        self.processing_status = Gauge(
            'stvid_processing_status',
            'Current status of processing (1=running, 0=stopped)'
        )
        self.files_processed = Counter(
            'stvid_files_processed_total',
            'Total number of files processed'
        )
        self.satellites_detected = Counter(
            'stvid_satellites_detected_total',
            'Total number of satellites detected'
        )
        self.processing_time = Histogram(
            'stvid_processing_duration_seconds',
            'Time taken to process each FITS file',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )
        self.processing_errors = Counter(
            'stvid_processing_errors_total',
            'Total number of processing errors',
            ['error_type']
        )
        self.processing_queue_size = Gauge(
            'stvid_processing_queue_size',
            'Number of files waiting to be processed'
        )
