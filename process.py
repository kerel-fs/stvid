#!/usr/bin/env python3
from __future__ import print_function
import glob
import numpy as np
from stvid.stio import fourframe
from stvid.stars import generate_star_catalog
from stvid.astrometry import calibrate_from_reference
from stvid.satellite import generate_satellite_predictions
from stvid.satellite import find_hough3d_lines
from stvid.extract import extract_tracks
import astropy.units as u
from astropy.utils.exceptions import AstropyWarning
from astropy.coordinates import EarthLocation
import warnings
import configparser
import argparse
import os
from termcolor import colored
import time
import shutil

if __name__ == "__main__":
    # Read commandline options
    conf_parser = argparse.ArgumentParser(description='Process captured' +
                                                      ' video frames.')
    conf_parser.add_argument("-c", "--conf_file",
                             help="Specify configuration file. If no file" +
                             " is specified 'configuration.ini' is used.",
                             metavar="FILE")
    conf_parser.add_argument("-d", "--directory",
                             help="Specify directory of observations. If no" +
                             " directory is specified parent will be used.",
                             metavar='DIR', dest='file_dir', default=".")

    args = conf_parser.parse_args()

    # Process commandline options and parse configuration
    cfg = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    if args.conf_file:
        cfg.read([args.conf_file])
    else:
        cfg.read('configuration.ini')

    # Set warnings
    warnings.filterwarnings("ignore", category=UserWarning, append=True)
    warnings.simplefilter("ignore", AstropyWarning)

    # Set location
    loc = EarthLocation(lat=cfg.getfloat('Common', 'observer_lat')*u.deg,
                        lon=cfg.getfloat('Common', 'observer_lon')*u.deg,
                        height=cfg.getfloat('Common', 'observer_el')*u.m)

    # Extract settings
    # Minimum predicted velocity (pixels/s)
    drdtmin = 10.0

    # Track selection region around prediction (pixels)
    trkrmin = 10.0

    # Track selection sigma
    trksig = 5.0

    # Minimum track points
    ntrkmin = 10

    # Move to processing directory
    os.chdir(args.file_dir)
    
    # Statistics file
    fstat = open("imgstat.csv", "w")
    fstat.write("fname,mjd,ra,de,rmsx,rmsy,mean,std,nstars,nused\n")
    
    # Create output dirs
    path = args.file_dir
    if not os.path.exists(os.path.join(path, "classfd")):
        os.makedirs(os.path.join(path, "classfd"))
    if not os.path.exists(os.path.join(path, "catalog")):
        os.makedirs(os.path.join(path, "catalog"))
    if not os.path.exists(os.path.join(path, "unid")):
        os.makedirs(os.path.join(path, "unid"))
    if not os.path.exists(os.path.join(path, "processed")):
        os.makedirs(os.path.join(path, "processed"))

    # Forever loop
    while True:
        # Get files
        fnames = sorted(glob.glob("2*.fits"))
        
        # Loop over files
        for fname in fnames:
            # Generate star catalog
            pix_catalog = generate_star_catalog(fname)

            # Calibrate astrometry
            calibrate_from_reference(fname, "test.fits",
                                     pix_catalog)

            # Generate satellite predictions
            generate_satellite_predictions(fname)
            
            # Detect lines with 3D Hough transform
            ids = find_hough3d_lines(fname)

            # Extract tracks
            extract_tracks(fname, trkrmin, drdtmin, trksig, ntrkmin, path)
        
            # Stars available and used
            nused = np.sum(pix_catalog.flag == 1)
            nstars = pix_catalog.nstars
        
            # Get properties
            ff = fourframe(fname)

            # Write output
            output = "%s %10.6f %10.6f %4d/%4d %5.1f %5.1f %6.2f +- %6.2f"%(ff.fname, ff.crval[0], ff.crval[1], nused, nstars, 3600.0*ff.crres[0], 3600.0*ff.crres[1], np.mean(ff.zavg), np.std(ff.zavg))
            print(colored(output, "yellow"))
            fstat.write(("%s,%.8lf,%.6f,%.6f,%.3f,%.3f,%.3f," +
                         "%.3f,%d,%d\n") % (ff.fname, ff.mjd, ff.crval[0],
                                            ff.crval[1], 3600*ff.crres[0],
                                            3600*ff.crres[1], np.mean(ff.zavg),
                                            np.std(ff.zavg), nstars, nused))

            # Move processed files
            shutil.move(fname, "processed")
            shutil.move(fname + ".png", "processed")
            shutil.move(fname + ".id", "processed")
            shutil.move(fname + ".cat", "processed")
            
        # Sleep
        time.sleep(10)
            
    # Close files
    fstat.close()

