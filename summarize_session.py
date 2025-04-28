#!/usr/bin/env python3
"""
Summarize a STVID observation session.

Features:
- Generate "overview_stars.png"

Example usage:
    $ ./summarize_session.py $OBS_PATH/20250118_0/235514
    Start:      2025-01-18T23:55:15.393
    End:        2025-01-19T00:07:06.732
    Duration:   711.33900024 hours
    Number of images: 71
    Session overview (visible sources) written to /satnogs_data/satnogs_data/optical/kerel/20250118_0/235514/overview_stars.png
"""
import glob
import os
import sys
from astropy.time import Time
from astropy.io import fits
from tqdm import tqdm
from pathlib import Path
from stvid.calibration import generate_star_catalog, StarCatalog
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import astropy.units as u
import matplotlib.units as munits
import pandas as pd
from fastparquet import write
import json

converter = mdates.ConciseDateConverter()
munits.registry[np.datetime64] = converter


def generate_session_summary(file_dir: Path):
    """
    This method generates the following files:
        - summary.parquet
        - summary.json
    """
    filename_parquet = file_dir / 'summary.parquet'
    filename_metadata = file_dir / 'summary.json'

    if filename_parquet.exists() and filename_metadata.exists():
        return

    date_str = file_dir.parent.name
    time_str = file_dir.name
    session_name = f'{date_str}/{time_str}'

    fitsfnames = sorted(glob.glob(str(file_dir / "2*.fits")))
    froots = [os.path.splitext(fitsname)[0] for fitsname in fitsfnames]

    times = []
    nstars = []
    for froot in tqdm(froots):
        fname_cat = Path(f"{froot}_stars.cat")
        fname_fits = f"{froot}.fits"
        if not fname_cat.exists():
            # Generate star catalog
            scat = generate_star_catalog(fname_fits)
        else:
            # Collect existing star catalog
            scat = StarCatalog(fname_cat)

        # Store number of sources from star catalog
        nstars.append(scat.nstars)

        # Read timestamp from FITS header
        hdu = fits.open(fname_fits)
        header = hdu[0].header
        hdu.close()

        t = header["MJD-OBS"]
        times.append(t)

    times = Time(times, format="mjd", scale="utc")

    df = pd.DataFrame({'times': times.datetime64, 'nstars': nstars})
    df.set_index('times', inplace=True)

    # Calculate session statistics
    time_start = np.min(times).datetime64
    time_end = np.max(times).datetime64
    duration = time_end - time_start
    n_images = len(froots)

    metadata = {
        'session_name': session_name,
        'start': np.datetime_as_string(time_start, unit="ms"),
        'end': np.datetime_as_string(time_end, unit="ms"),
        'duration': duration / np.timedelta64(1, 's'),
        'n_images': n_images,
    }

    write(filename_parquet, df)
    with open(filename_metadata, 'w') as fp:
        json.dump(metadata, fp, indent=2)


def show_summary(file_dir: Path):
    df = pd.read_parquet(file_dir / 'summary.parquet')
    with open(file_dir / 'summary.json') as fp:
        metadata = json.load(fp)

    # Generate "overview_stars.png"
    plot_filename = Path(file_dir) / 'overview_stars.png'
    fig, ax = plt.subplots(figsize=(8,6))
    ax.grid(True)
    ax.plot(df.index, df.nstars)
    ax.set_xlabel('Time (UTC)')
    ax.set_ylabel('Number of extracted sources (stars)')
    ax.set_title(f'Session overview: visible sources - {metadata["session_name"]}')
    plt.savefig(plot_filename, dpi=150)

    print(
        f'Start:      {metadata["start"]}\n'
        f'End:        {metadata["end"]}\n'
        f'Duration:   {metadata["duration"]} hours\n'
        f'Number of images: {metadata["n_images"]}'
    )
    print(f'Session overview (visible sources) written to {plot_filename}')


if __name__ == "__main__":
    file_dir = Path(sys.argv[1])
    generate_session_summary(file_dir)
    show_summary(file_dir)
