"""
Methods to create polar plots with astropy and matplotlib.
"""
import matplotlib.pyplot as plt
import numpy as np

from astropy.coordinates import AltAz
import astropy.units as u


def _get_altaz(coord, loc):
    if not coord.obstime:
        print('Error, missing coord.obstime.')
        raise ValueError

    frame_altaz = AltAz(obstime=coord.obstime,
                  location=loc)
    p = coord.transform_to(frame_altaz)
    if p.alt < 0 * u.deg:
        # print(f'Object not visible, {p.alt.degree:.1f}° below the horizon.')
        return None

    return p


class PolarPlotter:
    def __init__(self, ax=None):
        self._ax = ax
        if not self._ax:
            _, self._ax = plt.subplots(subplot_kw={'projection': 'polar'})

    def plot_skycoord(self, coord, loc, axes_kw={'color': 'C0', 'marker': '.'}):
        """
        Create a polar plot, show the object coord as seen from the given location
        in the Altitude-Azimuth system
        """
        p = _get_altaz(coord, loc)
        if not p:
            return
        return self.plot_altaz(alt=p.alt.degree,
                               az=p.az.degree,
                               axes_kw=axes_kw)

    def plot_altaz(self, alt, az, axes_kw={'color': 'C0', 'marker': '.'}):
        """
        Create a polar plot

        alt: Altitude in degree
        az: Azimuth in degree
        """
        self._ax.plot(az * (2*np.pi) / 360, 90 - alt, **axes_kw)
        self.set_axis()

    def set_axis(self):
        # Radial axis (Alt)
        self._ax.set_rlabel_position(0)
        self._ax.set_rmax(90)
        rticks = [0, 30, 60, 90]
        self._ax.set_rticks(rticks)
        self._ax.set_yticklabels(reversed(rticks))

        # Angular axis (Az)
        self._ax.set_theta_zero_location('N')
        self._ax.set_theta_direction(-1)
        self._ax.set_xticks([0, 0.5 * np.pi, np.pi, 1.5 * np.pi])
        self._ax.set_xticklabels(['N', 'E', 'S', 'W'])

        self._ax.grid(True, linestyle='dotted')
