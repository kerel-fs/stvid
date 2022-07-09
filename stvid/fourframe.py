#!/usr/bin/env python3
import os

import tempfile
import subprocess

import numpy as np

from astropy import wcs
from astropy.time import Time
from astropy.io import fits
from astropy.io import ascii
from astropy.coordinates import SkyCoord

class Prediction:
    """Prediction class"""

    def __init__(self, satno, mjd, ra, dec, x, y, rx, ry, state, tlefile, age):
        self.satno = satno
        self.age = age
        self.mjd = mjd
        self.t = 86400 * (self.mjd - self.mjd[0])
        self.texp = self.t[-1] - self.t[0]
        self.ra = ra
        self.dec = dec
        self.x = x
        self.y = y
        self.rx = rx
        self.ry = ry
        self.state = state
        self.tlefile = tlefile

    def position_and_velocity(self, t, dt):
        # Skip if predicted track is too short to fit a 3rd order polynomial
        if len(self.t) < 3:
            return np.nan, np.nan, np.nan, np.nan, np.nan

        # Create polynomials
        px = np.polyfit(self.t, self.rx, 2)
        py = np.polyfit(self.t, self.ry, 2)

        # Derivatives
        dpx = np.polyder(px)
        dpy = np.polyder(py)
        
        # Evaluate
        rx0, ry0 = np.polyval(px, t), np.polyval(py, t)
        drxdt, drydt = np.polyval(dpx, t), np.polyval(dpy, t)
        drdt = np.sqrt(drxdt**2 + drydt**2)
        pa = np.mod(np.arctan2(-drxdt, drydt), 2 * np.pi)
        dr = drdt * dt
        
        return rx0, ry0, drdt, pa, dr

    def predicted_track(self, tmin, tmid, tmax, ax, color):
        # Skip if predicted track is too short to fit a 3rd order polynomial
        if len(self.t) < 3:
            return np.nan, np.nan, np.nan, np.nan

        # Create polynomials
        px = np.polyfit(self.t, self.x, 2)
        py = np.polyfit(self.t, self.y, 2)

        # Derivatives
        dpx = np.polyder(px)
        dpy = np.polyder(py)
        
        # Evaluate
        x0, y0 = np.polyval(px, tmid), np.polyval(py, tmid)
        dxdt, dydt = np.polyval(dpx, tmid), np.polyval(dpy, tmid)

        # Extrema
        xmin = x0 + dxdt * (tmin - tmid)
        xmax = x0 + dxdt * (tmax - tmid)
        ymin = y0 + dydt * (tmin - tmid)
        ymax = y0 + dydt * (tmax - tmid)        

        ax.plot([xmin, xmax], [ymin, ymax], color=color, linestyle="-")
        ax.plot(x0, y0, color=color, marker="o", markerfacecolor="none")

    def residual(self, t0, rx0, ry0):
        # Skip if predicted track is too short to fit a 3rd order polynomial
        if len(self.t) < 3:
            return np.nan, np.nan

        # Create polynomials
        px = np.polyfit(self.t, self.rx, 2)
        py = np.polyfit(self.t, self.ry, 2)

        # Derivatives
        dpx = np.polyder(px)
        dpy = np.polyder(py)
        
        # Evaluate
        rx, ry = np.polyval(px, t0), np.polyval(py, t0)
        drxdt, drydt = np.polyval(dpx, t0), np.polyval(dpy, t0)
        drdt = np.sqrt(drxdt**2 + drydt**2)
        pa = np.arctan2(-drxdt, drydt)

        # Compute cross-track, in-track residual
        drx, dry = rx0 - rx, ry0 - ry
        ca, sa = np.cos(pa), np.sin(pa)
        rm = ca * drx - sa * dry
        wm = sa * drx + ca * dry
        dtm = rm / drdt
        
        return dtm, wm
        
class Track:
    """Track class"""

    def __init__(self, t, x, y, z, ra, dec, rx, ry):
        self.x = x
        self.y = y
        self.t = t
        self.z = z
        self.ra = ra
        self.dec = dec
        self.rx = rx
        self.ry = ry
        self.n = len(x)
        self.satno = None
        self.cospar = None

        # Compute mean position
        self.tmin, self.tmax = np.min(self.t), np.max(self.t)
        self.tmid = 0.5 * (self.tmax + self.tmin)

        # Position and velocity on the sky
        px = np.polyfit(self.t - self.tmid, self.rx, 1)
        py = np.polyfit(self.t - self.tmid, self.ry, 1)
        self.rx0 = px[-1]
        self.ry0 = py[-1]
        self.drxdt = px[-2]
        self.drydt = py[-2]
        self.rxmin = self.rx0 + self.drxdt * (self.tmin - self.tmid)
        self.rxmax = self.rx0 + self.drxdt * (self.tmax - self.tmid)
        self.rymin = self.ry0 + self.drydt * (self.tmin - self.tmid)
        self.rymax = self.ry0 + self.drydt * (self.tmax - self.tmid)
        self.drdt = np.sqrt(self.drxdt**2 + self.drydt**2)
        self.pa = np.mod(np.arctan2(-self.drxdt, self.drydt), 2 * np.pi)
        self.dr = self.drdt * (self.tmax - self.tmin)
        
        # Position and velocity on the image
        self.px = np.polyfit(self.t - self.tmid, self.x, 2)
        self.py = np.polyfit(self.t - self.tmid, self.y, 2)
        self.x0 = self.px[-1]
        self.y0 = self.py[-1]
        self.dxdt = self.px[-2]
        self.dydt = self.py[-2]
        self.xp = np.polyval(self.px, self.t - self.tmid)
        self.yp = np.polyval(self.py, self.t - self.tmid)
        self.xmin = self.x0 + self.dxdt * (self.tmin - self.tmid)
        self.xmax = self.x0 + self.dxdt * (self.tmax - self.tmid)
        self.ymin = self.y0 + self.dydt * (self.tmin - self.tmid)
        self.ymax = self.y0 + self.dydt * (self.tmax - self.tmid)
        self.r = np.sqrt((self.xmax - self.xmin)**2 + (self.ymax - self.ymin)**2)
        
    def match_to_prediction(self, p, dt, w):
        # Return if predicted track is too short to fit a 3rd order polynomial
        if len(p.t) < 3:
            return False
        
        # Create polynomials
        px = np.polyfit(p.t, p.x, 2)
        py = np.polyfit(p.t, p.y, 2)

        # Compute extrema
        xmin = np.polyval(px, self.tmin)
        xmax = np.polyval(px, self.tmax)
        ymin = np.polyval(py, self.tmin)
        ymax = np.polyval(py, self.tmax)

        
        # Check if observed track endpoints match with prediction
        pmin = inside_selection_area(self.tmin, self.tmax, self.x0, self.y0, self.dxdt, self.dydt, xmin, ymin, dt, w)
        pmax = inside_selection_area(self.tmin, self.tmax, self.x0, self.y0, self.dxdt, self.dydt, xmax, ymax, dt, w)        

        return pmin & pmax

class Observation:
    """Satellite observation"""

    def __init__(self, ff, t, x, y, site_id, norad, cospar):
        self.t = t
        self.mjd = ff.mjd + self.t / 86400
        self.nfd = Time(self.mjd, format="mjd", scale="utc").isot
        self.x = x
        self.y = y
        self.site_id = site_id
        self.norad = norad
        self.cospar = cospar
        
        p = SkyCoord.from_pixel(self.x, self.y, ff.w, 0)
        self.ra = p.ra.degree
        self.dec = p.dec.degree

    def to_iod_line(self):
        pstr = format_position(self.ra, self.dec)
        tstr = self.nfd.replace("-", "") \
                       .replace("T", "") \
                       .replace(":", "") \
                      .replace(".", "")
        iod_line = "%05d %-9s %04d G %s 17 25 %s 37 S" % (self.norad, self.cospar, self.site_id, tstr,
                                                          pstr)
        return iod_line

    
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
            self.ra0 = None
            self.dec0 = None
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
            self.ra0 = self.crval[0]
            self.dec0 = self.crval[1]
            
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
        self.zstdmin = np.mean(self.zstd) - 2.0 * np.std(self.zstd)
        self.zstdmax = np.mean(self.zstd) + 6.0 * np.std(self.zstd)
        self.znummin = 0
        self.znummax = self.nz
        self.zsigmin = 0
        self.zsigmax = 10
        
        # Setup WCS
        self.w = wcs.WCS(naxis=2)
        self.w.wcs.crpix = self.crpix
        self.w.wcs.crval = self.crval
        self.w.wcs.cd = self.cd
        self.w.wcs.ctype = self.ctype
        self.w.wcs.set_pv([(2, 1, 45.0)])

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
            command = f"satpredict -t {nfd} -l {texp} -n {nmjd} -L {lon} -B {lat} -H {height} -o {outfname} -R {ra0} -D {de0} -r {radius}"
            for key, value in cfg.items("Elements"):
                if "tlefile" in key:
                    command += f" -c {value}"
            print(command)
            # Run command
            output = subprocess.check_output(command,
                                             shell=True,
                                             stderr=subprocess.STDOUT)

        # Read results
        d = ascii.read(outfname, format="csv")

        # Compute frame coordinates
        p = SkyCoord(ra=d["ra"], dec=d["dec"], unit="deg", frame="icrs")
        x, y = p.to_pixel(self.w, 0)

        # Compute angular offsets
        rx, ry = deproject(self.ra0, self.dec0, p.ra.degree, p.dec.degree)
        
        # Loop over satnos
        satnos = np.unique(d["satno"])
        predictions = []
        for satno in satnos:
            c = d["satno"] == satno
            tlefile = np.unique(d["tlefile"][c])[0]
            age = np.unique(np.asarray(d["age"])[c])[0]
            p = Prediction(satno, np.asarray(d["mjd"])[c], np.asarray(d["ra"])[c], np.asarray(d["dec"])[c], x[c], y[c], rx[c], ry[c], np.array(d["state"])[c], tlefile, age)
            predictions.append(p)
        
        return predictions


    def in_frame(self, x, y):
        if (x >= 0) & (x <= self.nx) & (y >= 0) & (y <= self.ny):
            return True
        else:
            return False


    def find_tracks_by_hough3d(self, cfg):
        # Config settings
        sigma = cfg.getfloat("LineDetection", "trksig")
        trkrmin = cfg.getfloat("LineDetection", "trkrmin")
        ntrkmin = cfg.getfloat("LineDetection", "ntrkmin")
        
        # Find significant pixels (TODO: store in function?)
        c = self.zsig > sigma
        xm, ym = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        x, y = np.ravel(xm[c]), np.ravel(ym[c])
        znum = np.ravel(self.znum[c]).astype("int")
        zmax = np.ravel(self.zmax[c])
        sig = np.ravel(self.zsig[c])
        t = np.array([self.dt[i] for i in znum])

        # Compute ra/dec
        p = SkyCoord.from_pixel(x, y, self.w, 0)
        ra, dec = p.ra.degree, p.dec.degree

        # Compute angular offsets
        rx, ry = deproject(self.ra0, self.dec0, ra, dec)
        
        # Skip if not enough points
        if len(t) < ntrkmin:
            return []

        # Save points to temporary file
        (fd, tmpfile_path) = tempfile.mkstemp(prefix="hough_tmp", suffix=".dat")

        try:
            with os.fdopen(fd, "w") as f:
                for i in range(len(t)):
                    f.write(f"{x[i]:f},{y[i]:f},{znum[i]:f}\n")

            # Run 3D Hough line-finding algorithm
            command = f"hough3dlines -dx {trkrmin} -minvotes {ntrkmin} -raw {tmpfile_path}"
            
            try:
                output = subprocess.check_output(command,
                                                 shell=True,
                                                 stderr=subprocess.STDOUT)
            except Exception:
                return []
        finally:
            os.remove(tmpfile_path)

        # Decode output
        tracks = []
        for line in output.decode("utf-8").splitlines()[2:]:
            #lines.append(ThreeDLine(line, self.nx, self.ny, self.nz))
            ax, ay, az, bx, by, bz, n = decode_line(line)

            # Select points
            f = (znum - az) / bz
            xr = ax + f * bx
            yr = ay + f * by
            r = np.sqrt((x - xr)**2 + (y - yr)**2)
            c = r < trkrmin
            if np.sum(c) > 0:
                tracks.append(Track(t[c], x[c], y[c], zmax[c], ra[c], dec[c], rx[c], ry[c]))
            
        return tracks


def decode_line(line):
    p = line.split(" ")
    ax = float(p[0])
    ay = float(p[1])
    az = float(p[2])
    bx = float(p[3])
    by = float(p[4])
    bz = float(p[5])
    n = int(p[6])

    return ax, ay, az, bx, by, bz, n


# IOD position format 2: RA/DEC = HHMMmmm+DDMMmm MX   (MX in minutes of arc)
def format_position(ra, de):
    ram = 60.0 * ra / 15.0
    rah = int(np.floor(ram / 60.0))
    ram -= 60.0 * rah

    des = np.sign(de)
    dem = 60.0 * np.abs(de)
    ded = int(np.floor(dem / 60.0))
    dem -= 60.0 * ded

    if des == -1:
        sign = "-"
    else:
        sign = "+"

    return ("%02d%06.3f%c%02d%05.2f" % (rah, ram, sign, ded, dem)).replace(
        ".", "")

# Inside selection
def inside_selection_area(tmin, tmax, x0, y0, dxdt, dydt, x, y, dt=2.0, w=10.0):
    dx, dy = x - x0, y - y0
    ang = -np.arctan2(dy, dx)
    r = np.sqrt(dx**2 + dy**2)
    drdt = r / (tmax - tmin)
    sa, ca = np.sin(ang), np.cos(ang)
    tmid = 0.5 * (tmin + tmax)
    
    xmid = x0 + dxdt * tmid
    ymid = y0 + dydt * tmid

    dx, dy = x0 - xmid, y0 - ymid
    rm = ca * dx - sa * dy
    wm = sa * dx + ca * dy
    dtm = rm / drdt

    print(">> ", wm, dtm)
    
    if (np.abs(wm) < w) & (np.abs(dtm) < dt):
        return True
    else:
        return False
    
# Angular offsets from spherical angles                
def deproject(l0, b0, l, b):
    lt = l * np.pi / 180
    bt = b * np.pi / 180
    l0t = l0 * np.pi / 180
    b0t = b0 * np.pi / 180
    
    # To vector
    r = np.array([np.cos(lt) * np.cos(bt),
                  np.sin(lt) * np.cos(bt),
                  np.sin(bt)])

    # Rotation matrices
    cl, sl = np.cos(l0t), np.sin(l0t)
    Rl = np.array([[cl, sl, 0],
                    [-sl, cl, 0],
                    [0, 0, 1]])
    cb, sb = np.cos(b0t), np.sin(b0t)
    Rb = np.array([[cb, 0, sb],
                     [0, 1, 0],
                     [-sb, 0, cb]])    

    # Apply rotations
    r = Rl.dot(r)
    r = Rb.dot(r)

    # Back to angles
    radius = np.arccos(r[0])
    position_angle = np.arctan2(r[1], r[2]) 

    # To offsets
    dl, db = radius * np.sin(position_angle), radius * np.cos(position_angle)

    return dl * 180 / np.pi, db * 180 / np.pi
