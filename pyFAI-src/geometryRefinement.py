#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Project: Azimuthal integration
#             https://forge.epn-campus.eu/projects/azimuthal
#
#    File: "$Id$"
#
#    Copyright (C) European Synchrotron Radiation Facility, Grenoble, France
#
#    Principal author:       Jérôme Kieffer (Jerome.Kieffer@ESRF.eu)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

__author__ = "Jerome Kieffer"
__contact__ = "Jerome.Kieffer@ESRF.eu"
__license__ = "GPLv3+"
__copyright__ = "European Synchrotron Radiation Facility, Grenoble, France"
__date__ = "23/12/2011"
__status__ = "development"

import os
import tempfile
import subprocess
import logging
import numpy
import types
from math import pi
from pyFAI.azimuthalIntegrator import AzimuthalIntegrator
from scipy.optimize import fmin, leastsq, fmin_slsqp, anneal

if os.name != "nt":
    WindowsError = RuntimeError

logger = logging.getLogger("pyFAI.geometryRefinement")
# logger.setLevel(logging.DEBUG)
ROCA = "/opt/saxs/roca"

####################
# GeometryRefinement
####################


class GeometryRefinement(AzimuthalIntegrator):
    def __init__(self, data, dist=1, poni1=None, poni2=None,
                 rot1=0, rot2=0, rot3=0,
                 pixel1=None, pixel2=None, splineFile=None, detector=None,
                 wavelength=None, dSpacing=None):
        """
        @param data: ndarray float64 shape = n, 3
            col0: pos in dim0 (in pixels)
            col1: pos in dim1 (in pixels)
            col2: associated tth value (in rad)

        @param detector: name of the detector or Detector instance.
        """
        self.data = numpy.array(data, dtype="float64")
        AzimuthalIntegrator.__init__(self, dist, 0, 0,
                                     rot1, rot2, rot3,
                                     pixel1, pixel2, splineFile, detector, wavelength=wavelength)

        if (poni1 is None) or (poni2 is None):
            self.guess_poni()
        else:
            self.poni1 = float(poni1)
            self.poni2 = float(poni2)
        self._dist_min = 0
        self._dist_max = 10
        self._poni1_min = -10000 * self.pixel1
        self._poni1_max = 15000 * self.pixel1
        self._poni2_min = -10000 * self.pixel2
        self._poni2_max = 15000 * self.pixel2
        self._rot1_min = -pi
        self._rot1_max = pi
        self._rot2_min = -pi
        self._rot2_max = pi
        self._rot3_min = -pi
        self._rot3_max = pi
        self._wavelength_min = 1e-15
        self._wavelength_max = 100.e-10
        if dSpacing is not None:
            if type(dSpacing) in types.StringTypes:
                self.dSpacing = numpy.loadtxt(dSpacing)
            else:
                self.dSpacing = numpy.array(dSpacing, dtype=numpy.float64)
        else:
            self.dSpacing = numpy.array([])


    def guess_poni(self):
        """
        Poni can be guessed by the centroid of the ring with lowest 2Theta
        """
        tth = self.data[:, 2]
        asrt = tth.argsort()
        tth = tth[asrt]
        srtdata = self.data[asrt]
        smallRing = srtdata[tth < (tth.min() + 1e-6)]
        smallRing1 = smallRing[:, 0]
        smallRing2 = smallRing[:, 1]
        smallRing_in_m = self.detector.calc_cartesian_positions(smallRing1,
                                                                smallRing2)
        l = len(smallRing)
        self.poni1 = smallRing_in_m[0].sum() / l
        self.poni2 = smallRing_in_m[1].sum() / l

    def set_tolerance(self, value=10):
        """

        @param value: Tolerance as a percentage

        """
        low = 1.0 - value / 100.
        hi = 1.0 + value / 100.
        self.dist_min = low * self.dist
        self.dist_max = hi * self.dist
        if abs(self.poni1) > (value / 100.) ** 2:
            self.poni1_min = min(low * self.poni1, hi * self.poni1)
            self.poni1_max = max(low * self.poni1, hi * self.poni1)
        else:
            self.poni1_min = -(value / 100.) ** 2
            self.poni1_max = (value / 100.) ** 2
        if abs(self.poni2) > (value / 100.) ** 2:
            self.poni2_min = min(low * self.poni2, hi * self.poni2)
            self.poni2_max = max(low * self.poni2, hi * self.poni2)
        else:
            self.poni2_min = -(value / 100.) ** 2
            self.poni2_max = (value / 100.) ** 2
        if abs(self.rot1) > (value / 100.) ** 2:
            self.rot1_min = min(low * self.rot1, hi * self.rot1)
            self.rot1_max = max(low * self.rot1, hi * self.rot1)
        else:
            self.rot1_min = -(value / 100.) ** 2
            self.rot1_max = (value / 100.) ** 2
        if abs(self.rot2) > (value / 100.) ** 2:
            self.rot2_min = min(low * self.rot2, hi * self.rot2)
            self.rot2_max = max(low * self.rot2, hi * self.rot2)
        else:
            self.rot2_min = -(value / 100.) ** 2
            self.rot2_max = (value / 100.) ** 2
        if abs(self.rot3) > (value / 100.) ** 2:
            self.rot3_min = min(low * self.rot3, hi * self.rot3)
            self.rot3_max = max(low * self.rot3, hi * self.rot3)
        else:
            self.rot3_min = -(value / 100.) ** 2
            self.rot3_max = (value / 100.) ** 2
        self.wavelength_min = low * self.wavelength
        self.wavelength_max = hi * self.wavelength


    def calc_2th(self, rings, wavelength):
        """
        @param rings: indices of the rings. starts at 0 and self.dSpacing should be long enough !!!
        @param wavelength: wavelength in meter
        """
        rings = numpy.ascontiguousarray(rings, dtype=numpy.int32)
        return 2.0 * numpy.arcsin(wavelength / (2.0e-10 * self.dSpacing[rings]))

    def residu1(self, param, d1, d2, rings):
        return self.tth(d1, d2, param) - self.calc_2th(rings, self.wavelength)


    def residu1_wavelength(self, param, d1, d2, rings):
        return self.tth(d1, d2, param) - self.calc_2th(rings, param[6] * 1e-10)


    def residu2(self, param, d1, d2, rings):
        return (self.residu1(param, d1, d2, rings) ** 2).sum()

    def residu2_weighted(self, param, d1, d2, rings, weight):
        return (weight * self.residu1(param, d1, d2, rings) ** 2).sum()

    def residu2_wavelength(self, param, d1, d2, rings):
        return (self.residu1_wavelength(param, d1, d2, rings) ** 2).sum()

    def residu2_wavelength_weighted(self, param, d1, d2, rings, weight):
        return (weight * self.residu1_wavelength(param, d1, d2, rings) ** 2).sum()


    def refine1(self):
        self.param = numpy.array([self._dist, self._poni1, self._poni2,
                                  self._rot1, self._rot2, self._rot3],
                                 dtype="float64")
        newParam, rc = leastsq(self.residu1, self.param,
                               args=(self.data[:, 0],
                                     self.data[:, 1],
                                     self.data[:, 2]))
        oldDeltaSq = self.chi2(tuple(self.param))
        newDeltaSq = self.chi2(tuple(newParam))
        logger.info("Least square retcode=%s %s --> %s",
                    rc, oldDeltaSq, newDeltaSq)
        if newDeltaSq < oldDeltaSq:
            i = abs(self.param - newParam).argmax()
            d = ["dist", "poni1", "poni2", "rot1", "rot2", "rot3"]
            logger.info("maxdelta on %s: %s --> %s ",
                        d[i], self.param[i], newParam[i])
            self.param = newParam
            self.dist, self.poni1, self.poni2, \
                self.rot1, self.rot2, self.rot3 = tuple(newParam)
            return newDeltaSq
        else:
            return oldDeltaSq

    def refine2(self, maxiter=1000000, fix=["wavelength"]):
        d = ["dist", "poni1", "poni2", "rot1", "rot2", "rot3"]
        param = []
        bounds = []
        for i in d:
            param.append(getattr(self, i))
            if i in fix:
                val = getattr(self, i)
                bounds.append((val, val))
            else:
                bounds.append((getattr(self, "_%s_min" % i), getattr(self, "_%s_max" % i)))
        self.param = numpy.array(param)
        if self.data.shape[-1] == 3:
           pos0 = self.data[:, 0]
           pos1 = self.data[:, 1]
           ring = self.data[:, 2].astype(numpy.int32)
           weight = None
           newParam = fmin_slsqp(self.residu2, self.param, iter=maxiter,
                              args=(pos0, pos1, ring),
                              bounds=bounds,
                              acc=1.0e-12,
                              iprint=(logger.getEffectiveLevel() <= logging.INFO))

        elif self.data.shape[-1] == 4:
           pos0 = self.data[:, 0]
           pos1 = self.data[:, 1]
           ring = self.data[:, 2].astype(numpy.int32)
           weight = self.data[:, 3]
           newParam = fmin_slsqp(self.residu2_weighted, self.param, iter=maxiter,
                              args=(pos0, pos1, ring, weight),
                              bounds=bounds,
                              acc=1.0e-12,
                              iprint=(logger.getEffectiveLevel() <= logging.INFO))
        oldDeltaSq = self.chi2()
        newDeltaSq = self.chi2(newParam)
        logger.info("Constrained Least square %s --> %s",
                    oldDeltaSq, newDeltaSq)
        if newDeltaSq < oldDeltaSq:
            i = abs(self.param - newParam).argmax()

            logger.info("maxdelta on %s: %s --> %s ",
                        d[i], self.param[i], newParam[i])
            self.param = newParam
            self.dist, self.poni1, self.poni2, \
                self.rot1, self.rot2, self.rot3 = tuple(newParam)
            return newDeltaSq
        else:
            return oldDeltaSq

    def refine2_wavelength(self, maxiter=1000000, fix=["wavelength"]):
        d = ["dist", "poni1", "poni2", "rot1", "rot2", "rot3", "wavelength"]

        self.param = numpy.array([self.dist, self.poni1, self.poni2,
                                  self.rot1, self.rot2, self.rot3, self.wavelength],
                                 dtype="float64")
        param = []
        bounds = []
        for i in d:
            param.append(getattr(self, i))
            if i in fix:
                val = getattr(self, i)
                bounds.append((val, val))
            else:
                bounds.append((getattr(self, "_%s_min" % i), getattr(self, "_%s_max" % i)))
        # wavelength is multiplied to 10^10 to have values in the range 0.1-10: better numerical differentiation
        bounds[-1] = (bounds[-1][0] * 1e10, bounds[-1][1] * 1e10)
        param[-1] = 1e10 * param[-1]
        self.param = numpy.array(param)
        if self.data.shape[-1] == 3:
           pos0 = self.data[:, 0]
           pos1 = self.data[:, 1]
           ring = self.data[:, 2].astype(numpy.int32)
           weight = None
           newParam = fmin_slsqp(self.residu2_wavelength,
                                 self.param, iter=maxiter,
                                 args=(pos0, pos1, ring),
                                 bounds=bounds,
                                 acc=1.0e-12,
                                 iprint=(logger.getEffectiveLevel() <= logging.INFO))

        elif self.data.shape[-1] == 4:
           pos0 = self.data[:, 0]
           pos1 = self.data[:, 1]
           ring = self.data[:, 2].astype(numpy.int32)
           weight = self.data[:, 3]
           newParam = fmin_slsqp(self.residu2_wavelength_weighted,
                                 self.param, iter=maxiter,
                                 args=(pos0, pos1, ring, weight),
                                 bounds=bounds,
                                 acc=1.0e-12,
                                 iprint=(logger.getEffectiveLevel() <= logging.INFO))
        oldDeltaSq = self.chi2_wavelength()
        newDeltaSq = self.chi2_wavelength(newParam)
        logger.info("Constrained Least square %s --> %s",
                    oldDeltaSq, newDeltaSq)
        if newDeltaSq < oldDeltaSq:
            i = abs(self.param - newParam).argmax()
            logger.info("maxdelta on %s: %s --> %s ",
                        d[i], self.param[i], newParam[i])
            self.param = newParam
            self.dist, self.poni1, self.poni2, self.rot1, self.rot2, self.rot3 = tuple(newParam[:-1])
            self.wavelength = 1e-10 * newParam[-1]
            return newDeltaSq
        else:
            return oldDeltaSq


    def simplex(self, maxiter=1000000):
        self.param = numpy.array([self.dist, self.poni1, self.poni2,
                                  self.rot1, self.rot2, self.rot3],
                                 dtype="float64")
        newParam = fmin(self.residu2, self.param,
                        args=(self.data[:, 0],
                              self.data[:, 1],
                              self.data[:, 2]),
                        maxiter=maxiter,
                        xtol=1.0e-12)
        oldDeltaSq = self.chi2(tuple(self.param))
        newDeltaSq = self.chi2(tuple(newParam))
        logger.info("Simplex %s --> %s", oldDeltaSq, newDeltaSq)
        if newDeltaSq < oldDeltaSq:
            i = abs(self.param - newParam).argmax()
            d = ["dist", "poni1", "poni2", "rot1", "rot2", "rot3"]
            logger.info("maxdelta on %s : %s --> %s ",
                        d[i], self.param[i], newParam[i])
            self.param = newParam
            self.dist, self.poni1, self.poni2, \
                self.rot1, self.rot2, self.rot3 = tuple(newParam)
            return newDeltaSq
        else:
            return oldDeltaSq

    def anneal(self, maxiter=1000000):
        self.param = [self.dist, self.poni1, self.poni2,
                      self.rot1, self.rot2, self.rot3]
        result = anneal(self.residu2, self.param,
                        args=(self.data[:, 0],
                              self.data[:, 1],
                              self.data[:, 2]),
                        lower=[self._dist_min,
                               self._poni1_min,
                               self._poni2_min,
                               self._rot1_min,
                               self._rot2_min,
                               self._rot3_min],
                        upper=[self._dist_max,
                               self._poni1_max,
                               self._poni2_max,
                               self._rot1_max,
                               self._rot2_max,
                               self._rot3_max],
                        maxiter=maxiter)
        newParam = result[0]
        oldDeltaSq = self.chi2()
        newDeltaSq = self.chi2(newParam)
        logger.info("Anneal  %s --> %s", oldDeltaSq, newDeltaSq)
        if newDeltaSq < oldDeltaSq:
            i = abs(self.param - newParam).argmax()
            d = ["dist", "poni1", "poni2", "rot1", "rot2", "rot3"]
            logger.info("maxdelta on %s : %s --> %s ",
                        d[i], self.param[i], newParam[i])
            self.param = newParam
            self.dist, self.poni1, self.poni2, \
                self.rot1, self.rot2, self.rot3 = tuple(newParam)
            return newDeltaSq
        else:
            return oldDeltaSq

    def chi2(self, param=None):
        if param is None:
            param = self.param[:]
        return self.residu2(param,
                            self.data[:, 0], self.data[:, 1], self.data[:, 2])

    def chi2_wavelength(self, param=None):
        if param is None:
            param = self.param
            if len(param) == 6:
                param.append(1e10 * self.wavelength)
        return self.residu2_wavelength(param,
                            self.data[:, 0], self.data[:, 1], self.data[:, 2].astype(numpy.int32))


    def roca(self):
        """
        run roca to optimise the parameter set
        """
        tmpf = tempfile.NamedTemporaryFile()
        for line in self.data:
            tmpf.write("%s %s %s %s" % (line[2], line[0], line[1], os.linesep))
        tmpf.flush()
        roca = subprocess.Popen(
            [ROCA, "debug=8", "maxdev=1", "input=" + tmpf.name,
             str(self.pixel1), str(self.pixel2),
             str(self.poni1 / self.pixel1), str(self.poni2 / self.pixel2),
             str(self.dist), str(self.rot1), str(self.rot2), str(self.rot3)],
            stdout=subprocess.PIPE)
        newParam = [self.dist, self.poni1, self.poni2,
                    self.rot1, self.rot2, self.rot3]
        for line in roca.stdout:
            word = line.split()
            if len(word) == 3:
                if word[0] == "cen1":
                    newParam[1] = float(word[1]) * self.pixel1
                if word[0] == "cen2":
                    newParam[2] = float(word[1]) * self.pixel2
                if word[0] == "dis":
                    newParam[0] = float(word[1])
                if word[0] == "rot1":
                    newParam[3] = float(word[1])
                if word[0] == "rot2":
                    newParam[4] = float(word[1])
                if word[0] == "rot3":
                    newParam[5] = float(word[1])
        print "Roca", self.chi2(), "--> ", self.chi2(newParam)
        if self.chi2(tuple(newParam)) < self.chi2(tuple(self.param)):
            self.param = newParam
            self.dist, self.poni1, self.poni2, \
                self.rot1, self.rot2, self.rot3 = tuple(newParam)

        tmpf.close()

    def set_dist_max(self, value):
        if isinstance(value, float):
            self._dist_max = value
        else:
            self._dist_max = float(value)
    def get_dist_max(self):
        return self._dist_max
    dist_max = property(get_dist_max, set_dist_max)
    def set_dist_min(self, value):
        if isinstance(value, float):
            self._dist_min = value
        else:
            self._dist_min = float(value)
    def get_dist_min(self):
        return self._dist_min
    dist_min = property(get_dist_min, set_dist_min)


    def set_poni1_min(self, value):
        if isinstance(value, float):
            self._poni1_min = value
        else:
            self._poni1_min = float(value)
    def get_poni1_min(self):
        return self._poni1_min
    poni1_min = property(get_poni1_min, set_poni1_min)
    def set_poni1_max(self, value):
        if isinstance(value, float):
            self._poni1_max = value
        else:
            self._poni1_max = float(value)
    def get_poni1_max(self):
        return self._poni1_max
    poni1_max = property(get_poni1_max, set_poni1_max)

    def set_poni2_min(self, value):
        if isinstance(value, float):
            self._poni2_min = value
        else:
            self._poni2_min = float(value)
    def get_poni2_min(self):
        return self._poni2_min
    poni2_min = property(get_poni2_min, set_poni2_min)
    def set_poni2_max(self, value):
        if isinstance(value, float):
            self._poni2_max = value
        else:
            self._poni2_max = float(value)
    def get_poni2_max(self):
        return self._poni2_max
    poni2_max = property(get_poni2_max, set_poni2_max)

    def set_rot1_min(self, value):
        if isinstance(value, float):
            self._rot1_min = value
        else:
            self._rot1_min = float(value)
    def get_rot1_min(self):
        return self._rot1_min
    rot1_min = property(get_rot1_min, set_rot1_min)
    def set_rot1_max(self, value):
        if isinstance(value, float):
            self._rot1_max = value
        else:
            self._rot1_max = float(value)
    def get_rot1_max(self):
        return self._rot1_max
    rot1_max = property(get_rot1_max, set_rot1_max)

    def set_rot2_min(self, value):
        if isinstance(value, float):
            self._rot2_min = value
        else:
            self._rot2_min = float(value)
    def get_rot2_min(self):
        return self._rot2_min
    rot2_min = property(get_rot2_min, set_rot2_min)
    def set_rot2_max(self, value):
        if isinstance(value, float):
            self._rot2_max = value
        else:
            self._rot2_max = float(value)
    def get_rot2_max(self):
        return self._rot2_max
    rot2_max = property(get_rot2_max, set_rot2_max)

    def set_rot3_min(self, value):
        if isinstance(value, float):
            self._rot3_min = value
        else:
            self._rot3_min = float(value)
    def get_rot3_min(self):
        return self._rot3_min
    rot3_min = property(get_rot3_min, set_rot3_min)
    def set_rot3_max(self, value):
        if isinstance(value, float):
            self._rot3_max = value
        else:
            self._rot3_max = float(value)
    def get_rot3_max(self):
        return self._rot3_max
    rot3_max = property(get_rot3_max, set_rot3_max)

    def set_wavelength_min(self, value):
        if isinstance(value, float):
            self._wavelength_min = value
        else:
            self._wavelength_min = float(value)
    def get_wavelength_min(self):
        return self._wavelength_min
    wavelength_min = property(get_wavelength_min, set_wavelength_min)
    def set_wavelength_max(self, value):
        if isinstance(value, float):
            self._wavelength_max = value
        else:
            self._wavelength_max = float(value)
    def get_wavelength_max(self):
        return self._wavelength_max
    wavelength_max = property(get_wavelength_max, set_wavelength_max)
