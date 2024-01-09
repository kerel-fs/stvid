#!/usr/bin/env python3
import os

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy import wcs
from scipy import ndimage

import subprocess
import tempfile

from astropy.io import ascii
from astropy.coordinates import SkyCoord

SATPREDICT = get_bin_path("satpredict")
HOUGH3DLINES = get_bin_path("hough3dlines")


class ThreeDLine:
    """3D defined line"""

    def __init__(self, line, nx, ny, nz):
        p = line.split(" ")
        self.ax = float(p[0])
        self.ay = float(p[1])
        self.az = float(p[2])
        self.bx = float(p[3])
        self.by = float(p[4])
        self.bz = float(p[5])
        self.n = int(p[6])
        self.nx = nx
        self.ny = ny
        self.nz = nz

    def extrema(self):
        fzmin, fzmax = -self.az / self.bz, (self.nz - self.az) / self.bz

        xmin, xmax = self.ax + fzmin * self.bx, self.ax + fzmax * self.bx
        ymin, ymax = self.ay + fzmin * self.by, self.ay + fzmax * self.by

        if xmin < 0:
            fzmin = -self.ax / self.bx
        if xmax >= self.nx:
            fzmax = (self.nx - self.ax) / self.bx
        if ymin < 0:
            fzmin = -self.ay / self.by
        if ymax >= self.ny:
            fzmax = (self.ny - self.ay) / self.by

        self.xmin, self.xmax = self.ax + fzmin * self.bx, self.ax + fzmax * self.bx
        self.ymin, self.ymax = self.ay + fzmin * self.by, self.ay + fzmax * self.by
        self.zmin, self.zmax = int(self.az + fzmin * self.bz), int(self.az + fzmax * self.bz)
        if self.zmin < 0:
            self.zmin = 0
        if self.zmax > self.nz:
            self.zmax = self.nz
        self.fmin, self.fmax = fzmin, fzmax

        return self.fmin, self.fmax
        
    def __repr__(self):
        return f"{self.ax} {self.ay} {self.az} {self.bx} {self.by} {self.bz} {self.n}"

        
class Prediction:
    """Prediction class"""

    def __init__(self, satno, mjd, ra, dec, x, y, state, tlefile, age):
        self.satno = satno
        self.age = age
        self.mjd = mjd
        self.t = 86400 * (self.mjd - self.mjd[0])
        self.texp = self.t[-1] - self.t[0]
        self.ra = ra
        self.dec = dec
        self.x = x
        self.y = y
        self.state = state
        self.tlefile = tlefile

        
class Observation:
    """Satellite observation"""

    def __init__(self, ff, mjd, x0, y0):
        """Define an observation"""

        # Store
        self.mjd = mjd
        self.x0 = x0
        self.y0 = y0

        # Get times
        self.nfd = Time(self.mjd, format="mjd", scale="utc").isot

        # Correct for rotation
        tobs = Time(ff.mjd + 0.5 * ff.texp / 86400.0,
                    format="mjd",
                    scale="utc")
        tobs.delta_ut1_utc = 0
        hobs = tobs.sidereal_time("mean", longitude=0.0).degree
        tmid = Time(self.mjd, format="mjd", scale="utc")
        tmid.delta_ut1_utc = 0
        hmid = tmid.sidereal_time("mean", longitude=0.0).degree

        # Compute ra/dec
        world = ff.w.wcs_pix2world(np.array([[self.x0, self.y0]]), 1)
        if ff.tracked:
            self.ra = world[0, 0]
        else:
            self.ra = world[0, 0] + hobs - hmid
        self.de = world[0, 1]


class SatId:
    """Satellite identifications"""

    def __init__(self, line):
        s = line.split()
        self.nfd = s[0]
        self.x0 = float(s[1])
        self.y0 = float(s[2])
        self.t0 = 0.0
        self.x1 = float(s[3])
        self.y1 = float(s[4])
        self.t1 = float(s[5])
        self.norad = int(s[6])
        self.catalog = s[7]
        self.state = s[8]
        self.dxdt = (self.x1 - self.x0) / (self.t1 - self.t0)
        self.dydt = (self.y1 - self.y0) / (self.t1 - self.t0)

    def __repr__(self):
        return "%s %f %f %f -> %f %f %f %d %s %s" % (
            self.nfd, self.x0, self.y0, self.t0, self.x1, self.y1, self.t1,
            self.norad, self.catalog, self.state)


class FourFrame:
    """Four Frame class"""

    def __init__(self, fname=None):
        if fname is None:
            # Initialize empty fourframe
            self.nx = 0
            self.ny = 0
            self.nz = 0
            self.mjd = -1
            self.nfd = None
            self.zavg = None
            self.zstd = None
            self.zmax = None
            self.znum = None
            self.dt = None
            self.site_id = 0
            self.observer = None
            self.texp = 0.0
            self.fname = None
            self.crpix = np.array([0.0, 0.0])
            self.crval = np.array([0.0, 0.0])
            self.cd = np.array([[1.0, 0.0], [0.0, 1.0]])
            self.ctype = ["RA---TAN", "DEC--TAN"]
            self.cunit = np.array(["deg", "deg"])
            self.crres = np.array([0.0, 0.0])
            self.tracked = False
        else:
            # Read FITS file
            hdu = fits.open(fname)

            # Read image planes
            self.zavg, self.zstd, self.zmax, self.znum = hdu[0].data

            # Generate sigma frame
            self.zsig = (self.zmax - self.zavg) / (self.zstd + 1e-9)

            # Frame properties
            self.ny, self.nx = self.zavg.shape
            self.nz = hdu[0].header["NFRAMES"]

            # Read frame time oselfsets
            self.dt = np.array(
                [hdu[0].header["DT%04d" % i] for i in range(self.nz)])

            # Read header
            self.mjd = hdu[0].header["MJD-OBS"]
            self.nfd = hdu[0].header["DATE-OBS"]
            self.site_id = hdu[0].header["COSPAR"]
            self.observer = hdu[0].header["OBSERVER"]
            self.texp = hdu[0].header["EXPTIME"]
            self.fname = fname

            # Astrometry keywords
            self.crpix = np.array(
                [hdu[0].header["CRPIX1"], hdu[0].header["CRPIX2"]])
            self.crval = np.array(
                [hdu[0].header["CRVAL1"], hdu[0].header["CRVAL2"]])
            self.cd = np.array(
                [[hdu[0].header["CD1_1"], hdu[0].header["CD1_2"]],
                 [hdu[0].header["CD2_1"], hdu[0].header["CD2_2"]]])
            self.ctype = [hdu[0].header["CTYPE1"], hdu[0].header["CTYPE2"]]
            self.cunit = [hdu[0].header["CUNIT1"], hdu[0].header["CUNIT2"]]
            self.crres = np.array(
                [hdu[0].header["CRRES1"], hdu[0].header["CRRES2"]])

            # Check for sidereal tracking
            try:
                self.tracked = bool(hdu[0].header["TRACKED"])
            except KeyError:
                self.tracked = False
            
            hdu.close()

        # Compute image properties
        self.sx = np.sqrt(self.cd[0, 0]**2 + self.cd[1, 0]**2)
        self.sy = np.sqrt(self.cd[0, 1]**2 + self.cd[1, 1]**2)
        self.wx = self.nx * self.sx
        self.wy = self.ny * self.sy
        self.zmaxmin = np.mean(self.zmax) - 2.0 * np.std(self.zmax)
        self.zmaxmax = np.mean(self.zmax) + 6.0 * np.std(self.zmax)
        self.zavgmin = np.mean(self.zavg) - 2.0 * np.std(self.zavg)
        self.zavgmax = np.mean(self.zavg) + 6.0 * np.std(self.zavg)
        self.zsigmin = 0
        self.zsigmax = 10
        
        # Setup WCS
        self.w = wcs.WCS(naxis=2)
        self.w.wcs.crpix = self.crpix
        self.w.wcs.crval = self.crval
        self.w.wcs.cd = self.cd
        self.w.wcs.ctype = self.ctype
        self.w.wcs.set_pv([(2, 1, 45.0)])

    def mask(self, xmin, xmax, ymin, ymax):
        x, y = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        c = (x >= xmin) & (x <= self.nx-xmax)\
                        & (y >= ymin)\
                        & (y <= self.ny-ymax)
        self.mask = np.ones_like(self.zavg)
        self.mask[~c] = 0.0
        self.zavg *= self.mask
        self.zstd *= self.mask
        self.zmax *= self.mask
        self.znum *= self.mask
        self.zsig *= self.mask

    def selection_mask(self, sigma, zstd):
        """Create a selection mask"""
        c1 = ndimage.uniform_filter(self.znum, 3, mode="constant")
        c2 = ndimage.uniform_filter(self.znum * self.znum, 3, mode="constant")

        # Add epsilon to keep square root positive
        z = np.sqrt(c2 - c1 * c1 + 1e-9)

        # Standard deviation mask
        c = z < zstd
        m1 = np.zeros_like(self.zavg)
        m1[c] = 1.0

        # Sigma mask
        c = self.zsig < sigma
        m2 = np.zeros_like(self.zavg)
        m2[~c] = 1.0
        self.zsel = m1 * m2

        # Generate points
        c = self.zsel == 1.0
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        inum = np.ravel(self.znum[c]).astype("int")
        sig = np.ravel(self.zsig[c])
        t = np.array([self.dt[i] for i in inum])

        return x, y, inum, t, sig

    def significant_pixels_along_track(self,
                                       sigma,
                                       x0,
                                       y0,
                                       dxdt,
                                       dydt,
                                       rmin=10.0):
        """Extract significant pixels along a track"""

        # Generate sigma frame
        zsig = (self.zmax - self.zavg) / (self.zstd + 1e-9)

        # Select
        c = (zsig > sigma)

        # Positions
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        inum = np.ravel(self.znum[c]).astype("int")
        sig = np.ravel(zsig[c])
        t = np.array([self.dt[i] for i in inum])

        # Predicted positions
        xr = x0 + dxdt * t
        yr = y0 + dydt * t
        r = np.sqrt((x - xr)**2 + (y - yr)**2)
        c = r < rmin

        return x[c], y[c], t[c], sig[c]

    def significant_pixels(self, sigma):
        """Extract significant pixels"""

        # Generate sigma frame
        zsig = (self.zmax - self.zavg) / (self.zstd + 1e-9)

        # Select
        c = (zsig > sigma)

        # Positions
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        inum = np.ravel(self.znum[c]).astype("int")
        sig = np.ravel(zsig[c])
        t = np.array([self.dt[i] for i in inum])

        return x, y, t, sig

    def track(self, dxdt, dydt, tref):
        """Track and stack"""
        # Empty frame
        ztrk = np.zeros_like(self.zavg)

        # Loop over frames
        for i in range(self.nz):
            dx = int(np.round(dxdt * (self.dt[i] - tref)))
            dy = int(np.round(dydt * (self.dt[i] - tref)))

            # Skip if shift larger than image
            if np.abs(dx) >= self.nx:
                continue
            if np.abs(dy) >= self.ny:
                continue

            # Extract range
            if dx >= 0:
                i1min, i1max = dx, self.nx - 1
                i2min, i2max = 0, self.nx - dx - 1
            else:
                i1min, i1max = 0, self.nx + dx - 1
                i2min, i2max = -dx, self.nx - 1
            if dy >= 0:
                j1min, j1max = dy, self.ny - 1
                j2min, j2max = 0, self.ny - dy - 1
            else:
                j1min, j1max = 0, self.ny + dy - 1
                j2min, j2max = -dy, self.ny - 1
            zsel = np.where(self.znum == i, self.zmax, 0.0)
            ztrk[j2min:j2max, i2min:i2max] += zsel[j1min:j1max, i1min:i1max]

        return ztrk

    def in_frame(self, x, y):
        if (x >= 0) & (x <= self.nx) & (y >= 0) & (y <= self.ny):
            return True
        else:
            return False

    def generate_satellite_predictions(self, cfg):
        # Output file name
        outfname = f"{self.fname}.csv"

        # Run predictions
        if not os.path.exists(outfname):
            # Extract parameters
            nfd = self.nfd
            texp = self.texp
            nmjd = int(np.ceil(texp))
            ra0, de0 = self.crval[0], self.crval[1]
            radius = np.sqrt(self.wx * self.wx + self.wy * self.wy)
            lat = cfg.getfloat("Observer", "latitude")
            lon = cfg.getfloat("Observer", "longitude")
            height = cfg.getfloat("Observer", "height")
    
            # Format command
            command = f"{SATPREDICT} -t {nfd} -l {texp} -n {nmjd} -L {lon} -B {lat} -H {height} -o {outfname} -R {ra0} -D {de0} -r {radius}"
            for key, value in cfg.items("Elements"):
                if "tlefile" in key:
                    command += f" -c {value}"

            # Run command
            output = subprocess.check_output(command,
                                             shell=True,
                                             stderr=subprocess.STDOUT)

        # Read results
        d = ascii.read(outfname, format="csv")

        # Compute frame coordinates
        p = SkyCoord(ra=d["ra"], dec=d["dec"], unit="deg", frame="icrs")
        x, y = p.to_pixel(self.w, 0)
    
        # Loop over satnos
        satnos = np.unique(d["satno"])
        predictions = []
        for satno in satnos:
            c = d["satno"] == satno
            tlefile = np.unique(d["tlefile"][c])[0]
            age = np.unique(np.asarray(d["age"])[c])[0]
            p = Prediction(satno, np.asarray(d["mjd"])[c], np.asarray(d["ra"])[c], np.asarray(d["dec"])[c], x[c], y[c], np.array(d["state"])[c], tlefile, age)
            predictions.append(p)
        
        return predictions

    def find_lines(self, cfg):
        # Config settings
        sigma = cfg.getfloat("LineDetection", "trksig")
        trkrmin = cfg.getfloat("LineDetection", "trkrmin")
        ntrkmin = cfg.getfloat("LineDetection", "ntrkmin")
        
        # Find significant pixels (TODO: store in function?)
        c = self.zsig > sigma
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        z = np.ravel(self.znum[c]).astype("int")
        sig = np.ravel(self.zsig[c])
        t = np.array([self.dt[i] for i in z])

        # Skip if not enough points
        if len(t) < ntrkmin:
            return []

        # Save points to temporary file
        (fd, tmpfile_path) = tempfile.mkstemp(prefix="hough_tmp", suffix=".dat")

        try:
            with os.fdopen(fd, "w") as f:
                for i in range(len(t)):
                    f.write(f"{x[i]:f},{y[i]:f},{z[i]:f}\n")

            # Run 3D Hough line-finding algorithm
            command = f"{HOUGH3DLINES} -dx {trkrmin} -minvotes {ntrkmin} -raw {tmpfile_path}"
            
            try:
                output = subprocess.check_output(command,
                                                 shell=True,
                                                 stderr=subprocess.STDOUT)
            except Exception:
                return []
        finally:
            os.remove(tmpfile_path)

        # Decode output
        lines = []
        for line in output.decode("utf-8").splitlines()[2:]:
            lines.append(ThreeDLine(line, self.nx, self.ny, self.nz))

        return lines

    def find_tracks(self, cfg):
        # Config settings
        sigma = cfg.getfloat("LineDetection", "trksig")
        trkrmin = cfg.getfloat("LineDetection", "trkrmin")
        ntrkmin = cfg.getfloat("LineDetection", "ntrkmin")
        
        # Find significant pixels (TODO: store in function?)
        c = self.zsig > sigma
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        z = np.ravel(self.znum[c]).astype("int")
        sig = np.ravel(self.zsig[c])
        t = np.array([self.dt[i] for i in z])

        # Skip if not enough points
        if len(t) < ntrkmin:
            return []

        # Save points to temporary file
        (fd, tmpfile_path) = tempfile.mkstemp(prefix="hough_tmp", suffix=".dat")

        try:
            with os.fdopen(fd, "w") as f:
                for i in range(len(t)):
                    f.write(f"{x[i]:f},{y[i]:f},{z[i]:f}\n")

            # Run 3D Hough line-finding algorithm
            command = f"{HOUGH3DLINES} -dx {trkrmin} -minvotes {ntrkmin} -raw {tmpfile_path}"
            
            try:
                output = subprocess.check_output(command,
                                                 shell=True,
                                                 stderr=subprocess.STDOUT)
            except Exception:
                return []
        finally:
            os.remove(tmpfile_path)

        # Decode output
        lines = []
        for line in output.decode("utf-8").splitlines()[2:]:
            lines.append(ThreeDLine(line, self.nx, self.ny, self.nz))

        return lines
    
    def __repr__(self):
        return "%s %dx%dx%d %s %.3f %d %s" % (self.fname, self.nx, self.ny,
                                              self.nz, self.nfd, self.texp,
                                              self.site_id, self.observer)
