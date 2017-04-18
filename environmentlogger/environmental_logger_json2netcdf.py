#!/usr/bin/env python

'''
environmental_logger_json2netcdf.py

----------------------------------------------------------------------------------------
This module will read data generated by Environmental Sensor and convert to netCDF file
----------------------------------------------------------------------------------------
Prerequisite:
1. Python (2.7+ recommended)
2. netCDF4 module for Python (and its dependencies)
3. numpy (For array calculations, make sure the numpy has the same Python verison as other modules)
----------------------------------------------------------------------------------------

Usage: Give full path to environmental_logger_json2netcdf.py, or place it in PYTHONPATH, then:

python environmental_logger_json2netcdf.py drc_in drc_out # Process all files in drc_in
python environmental_logger_json2netcdf.py  fl_in drc_out # Process only fl_in
where drc_in is input directory, drc_out is output directory, fl_in is input file
Input  filenames must have '.json' extension
Output filenames are replace '.json' with '.nc'

UCI test:
python ${HOME}/terraref/extractors-environmental/environmentlogger/environmental_logger_json2netcdf.py ${DATA}/terraref/environmentlogger_test.json ${DATA}/terraref

UCI production:
python ${HOME}/terraref/extractors-environmental/environmentlogger/environmental_logger_json2netcdf.py ${DATA}/terraref/EnvironmentLogger/2016-04-07/2016-04-07_12-00-07_enviromentlogger.json ~/rgr

Roger production:
module add gdal-stack-2.7.10
python ${HOME}/terraref/extractors-environmental/environmentlogger/environmental_logger_json2netcdf.py /projects/arpae/terraref/sites/ua-mac/raw_data/EnvironmentLogger/2016-10-06/2016-10-06_03-17-29_environmentlogger.json ~/rgr
python ${HOME}/terraref/extractors-environmental/environmentlogger/environmental_logger_json2netcdf.py /projects/arpae/terraref/sites/ua-mac/raw_data/EnvironmentLogger/2016-11-18/2016-11-18_08-37-34_environmentlogger.json ~/rgr

environmental_logger_json2netcdf.py takes the first argument as the input folder (containing JSON files,
but it can also be one single file) and the second argument as the output folder (output netCDF files go here).
If the output folder does not exist, environmental_logger_json2netcdf.py creates it.

----------------------------------------------------------------------------------------
20160429: Output JSON file is now completely composed by variables
          2D spectrometer variables (wavelength and spectrum) are available in the exported file
20160503: Add chunksizes parameters for time, which significantly reduces the processing time (and the file size)
          Add timestamps and commandLine the user used for each exported file
          Remind the user currently the script is dealing with which file
20160508: 1. "timestamp" array are double-precison, with unit of days offset from UNIX base time (Gregorian Calender)
          2. Remove unnecessary I/O (in wavelength, because we only need the wavelengths in the first set of readings)
20160509: 1. Retrieve the adjustment Professor Zender made in version a38ca7d, May 4th
          2. Rename wavelength variable and dimension as "wvl_lgr" to avoid name collision with Hyperspectral wavelengths
20160511: Add variables and calculations from hyperspectral_calibration.nco, including wvl_dlt and flx_sns
          Add new array flx_spc_dwn (downwelling spectral flux) to the netCDF file
20160512: Recalculate downwellingSpectralFlux, save Flux sensitivity in SI
20160517: Implement variable wavelength
20160518: 1. Add numpy module, now the array calculation will be done by numpy to improve efficiency
          2. Add Downwelling Flux (the previous one is recognized and renamed as Downwelling spectral flux)
20160519: 1. Recalculate and double check the method used for calculating downwelling spectral flux
          2. Reinstate the integration time and sensor area (based on the discussion about the dimension of the flux sensitivity)
          3. Clean up based on Professor Zender's adjustment
20160526: All units are now in SI

----------------------------------------------------------------------------------------
Note:
If you need a different base time, it is named "_UNIX_BASETIME" and located at the
beginning of the script as a global variable. You could simply change the parameters
as they are named.

----------------------------------------------------------------------------------------
Thanks for the advice from Professor Zender and testing data from Mr. Maloney
----------------------------------------------------------------------------------------
'''
import numpy as np
import argparse
import json
import time
import sys
import os
from datetime import date, datetime
from netCDF4 import Dataset
from environmental_logger_calculation import *


_UNIT_DICTIONARY = {u'm': {"original":"meter", "SI":"meter", "power":1}, 
                    u"hPa": {"original":"hectopascal", "SI":"pascal", "power":1e2},
                    u"DegCelsius": {"original":"celsius", "SI":"celsius", "power":1},
                    u's': {"original":"second", "SI":"second", "power":1}, 
                    u'm/s': {"original":"meter second-1", "SI":"meter second-1", "power":1}, 
                    u"mm/h": {"original":"millimeter hour-1", "SI":"meter second-1", "power":2.78e-7},
                    u"relHumPerCent": {"original":"percent", "SI":"percent", "power":1}, 
                    u"?mol/(m^2*s)": {"original":"micromole meter-2 second-1", "SI":"mole second-1", "power":1e-6}, 
                    u"umol/(m^2*s)": {"original":"micromole meter-2 second-1", "SI":"mole second-1", "power":1e-6},
                    u'kilo Lux': {"original":"kiloLux", "SI":"lux", "power":1e3}, 
                    u'degrees': {"original":"degree", "SI":"degree", "power":1}, 
                    u'?s': {"original":"microsecond", "SI":"second", "power":1e-6}, 
                    u'us': {"original":"microsecond", "SI":"second", "power":1e-6},
                    u'ppm': {"original":"part per million", "SI":"mol mol-1", "power":1e-6}, 
                    '': ''}

_CF_STANDARDS    = {u'precipitation' : "precipitation_flux",
                    u'airPressure'   : "atmospheric_air_pressure",
                    u'relHumidity'   : "relative_humidity",
                    u"windDirection" : "wind_from_direction",
                    u"sensor_co2"    : "mole_fraction_of_carbon_dioxide_in_air"}

_NAMES = {'sensor par'   : 'Photosynthetically Active Radiation',
          'sunDirection' : 'Solar zenith (or elevation) angle (under discussion right now)',
          'temperature'  : 'Atmosperic Temperature',
          'relHumidity'  : 'Relative Humidity',
          'precipitation': 'Precipation Rate',
          'windDirection': 'Wind Direction',
          'windVelocity' : 'Wind Speed'}

_UNIX_BASETIME = date(year=1970, month=1, day=1)

def JSONHandler(fileLocation):
    '''
    Main JSON handler, write JSON file to a Python list with standard JSON module
    '''
    with open(fileLocation, 'r') as fileHandler:
        return json.loads(fileHandler.read())


def renameTheValue(name):
    '''
    Rename the value so they are legal in netCDF
    '''
    if name in _UNIT_DICTIONARY:
        name = _UNIT_DICTIONARY[name]
    elif name in _NAMES:
        name = _NAMES[name]
    elif name in ("sensor co2" or "sensor par"):
        name = "atmospherical CO2 concentration" if name.endswith("co2") else "photosynthetically active radiation"

    return name.replace(" ", "_")


def getSpectrometerInformation(arrayOfJSON):
    '''
    Collect information from spectrometer with special care
    these information contain:
    1. max fixed intensity
    2. integration time
    '''
    maxFixedIntensity = [int(intensityMembers["spectrometer"]["maxFixedIntensity"])\
                         for intensityMembers in arrayOfJSON]
    integrationTime   = [int(integrateMembers["spectrometer"]["integration time in ?s"])\
                         for integrateMembers in arrayOfJSON]

    return maxFixedIntensity, integrationTime


def getListOfWeatherStationValue(arrayOfJSON, dataName):
    '''
    Collect data from weather station objects which have "value" member
    these data are:
    1. values
    2. units
    3. raw values
    '''
    converting_to = _UNIT_DICTIONARY[arrayOfJSON[0]["weather_station"][dataName]['unit']]
    
    return np.array([float(valueMembers["weather_station"][dataName]['value'])\
            for valueMembers in arrayOfJSON])*converting_to["power"],\
           [converting_to["SI"]\
            for valueMembers in arrayOfJSON],\
           [float(valueMembers["weather_station"][dataName]['rawValue'])\
            for valueMembers in arrayOfJSON] 


def handleSpectrometer(JSONArray):
    '''
    This function will return the wavelength (1D array), spectrum (2D array) and maxFixedIntensity (1D array) in spectrometer readings
    '''

    wvl_lgr           = JSONArray[0]["spectrometer"]["wavelength"]
    spectrum          = [valueMembers["spectrometer"]["spectrum"]\
                         for valueMembers in JSONArray]
    maxFixedIntensity = [float(valueMembers["spectrometer"]["maxFixedIntensity"])\
                         for valueMembers in JSONArray]

    return wvl_lgr, spectrum, maxFixedIntensity


def sensorVariables(JSONArray, sensors):
    '''
    return the variables start with "sensor"
    these are:
    1. values
    2. units
    3. raw values
    '''
    converting_to = _UNIT_DICTIONARY[JSONArray[0][sensors]['unit']]

    return np.array([float(valueMembers[sensors]['value'])
            for valueMembers in JSONArray])*converting_to["power"],\
           [converting_to["SI"]
            for valueMembers in JSONArray],\
           [float(valueMembers[sensors]['rawValue'])
            for valueMembers in JSONArray]


def translateTime(timeString):
    '''
    Translate the time the metadata included as the days offset to the basetime.
    '''
    timeUnpack = datetime.strptime(timeString, "%Y.%m.%d-%H:%M:%S").timetuple()
    timeSplit  = date(year=timeUnpack.tm_year, month=timeUnpack.tm_mon, day=timeUnpack.tm_mday) - _UNIX_BASETIME

    return (timeSplit.total_seconds() + timeUnpack.tm_hour * 3600.0 + timeUnpack.tm_min * 60.0 + timeUnpack.tm_sec) / (3600.0 * 24.0)


def main(JSONArray, outputFileType, outputFileName, wavelength=None, spectrum=None, downwellingSpectralFlux=None, commandLine=None):
    '''
    Main netCDF handler, write data to the netCDF file indicated.
    '''
    with Dataset(outputFileName, 'w', format=outputFileType) as netCDFHandler:
        loggerFixedInfos = JSONArray["environment_sensor_fixed_infos"]
        loggerReadings   = JSONArray["environment_sensor_readings"]

        # for infos, atttributes in loggerFixedInfos.items():
        #     # infosGroup = netCDFHandler.createGroup(infos)
        #     for subInfos in atttributes:
        #         setattr(infosGroup, renameTheValue("".join((infos, subInfos))), loggerFixedInfos[infos][subInfos])

        netCDFHandler.createDimension("time", None)

        ### Create "Sensor" Variables ###
        sensor_par_var      = netCDFHandler.createVariable("sensor_par", 'i2')
        sensor_co2_var      = netCDFHandler.createVariable("sensor_co2", "i2")
        sensor_spectrum_var = netCDFHandler.createVariable("sensor_spectrum", "i2")
        sensor_weather_var  = netCDFHandler.createVariable("sensor_weather_station", "i2")

        weather_station_attr = {"id"         :"5873a9724f0cad7d8131b4d3",
                                "name"       :"Thies CLIMA",
                                "description":"This dataset contains documentation, datasheets, and metadata about the Theis CLIMA sensor.",
                                "created"    :"Mon Jan 09 09:17:06 CST 2017",
                                "thumbnail"  :"5873a97f4f0cad7d8131b56d",
                                "authorId"   :"578f76948e7e1aecb7cad4c5",
                                "spaces"     :[]}

        spectro_attr = {"id"         :"5873a9174f0cad7d8131b09a",
                        "name"       :"Skye PRI",
                        "description":"This dataset contains documentation, datasheets, and metadata about the Skye PRI sensor.",
                        "created"    :"Mon Jan 09 09:15:35 CST 2017",
                        "thumbnail"  :"None",
                        "authorId"   :"578f76948e7e1aecb7cad4c5",
                        "spaces"     :[]}

        sensor_co2_attr = {"id"         :"5873a9924f0cad7d8131b648",
                           "name"       :"Vaisala CO2",
                           "description":"This dataset contains documentation, datasheets, and metadata about the Viasala CO2 sensor.",
                           "created"    :"Mon Jan 09 09:17:38 CST 2017",
                           "thumbnail"  :"5873a99e4f0cad7d8131b6dc",
                           "authorId"   :"578f76948e7e1aecb7cad4c5",
                           "spaces"     :[]}

        sensor_par_attr = {"id"         :"5873a8ce4f0cad7d8131ad86",
                           "name"       :"Quantum PAR",
                           "description":"This dataset contains documentation, datasheets, and metadata about the Quantum PAR sensor.",
                           "created"    :"Mon Jan 09 09:14:22 CST 2017",
                           "thumbnail"  :"None",
                           "authorId"   :"578f76948e7e1aecb7cad4c5",
                           "spaces"     :[]}

        for key, value in weather_station_attr.items():
            setattr(sensor_weather_var, "sensor_weather_station_"+key, value)

        for key, value in spectro_attr.items():
            setattr(sensor_spectrum_var, "sensor_spectrum_"+key, value)

        for key, value in sensor_co2_attr.items():
            setattr(sensor_co2_var, "sensor_co2_"+key, value)

        for key, value in sensor_par_attr.items():
            setattr(sensor_par_var, "sensor_par_"+key, value)


        for data in loggerReadings[0]["weather_station"]: #writing the data from weather station
            value, unit, rawValue           = getListOfWeatherStationValue(loggerReadings, data)
            valueVariable, rawValueVariable = netCDFHandler.createVariable(data, "f4", ("time", )),\
                                              netCDFHandler.createVariable("".join(("raw_",data)), "f4", ("time", ))
                
            valueVariable[:]    = value
            rawValueVariable[:] = rawValue
            setattr(valueVariable, "units", unit[0])

            setattr(valueVariable, "sensor_weather_station", 'refer to variable "sensor weather station"')
            if data in _CF_STANDARDS:
                setattr(valueVariable, "standard_name", _CF_STANDARDS[data])
            if data in _NAMES:
                setattr(valueVariable, "long_name", _NAMES[data])
            if data == "relHumidity":
                setattr(valueVariable, "description", "Ratio of partial pressure of water vapor to equilibrium vapor pressure at measured temperature")

        wvl_lgr, spectrum, maxFixedIntensity = handleSpectrometer(loggerReadings) #writing the data from spectrometer

        netCDFHandler.createDimension("wvl_lgr", len(wvl_lgr))
        wavelengthVariable = netCDFHandler.createVariable("wvl_lgr", "f4", ("wvl_lgr",))

        setattr(wavelengthVariable, "sensor_spectrum", 'refer to variable "sensor spectrum object"')
        spectrumVariable   = netCDFHandler.createVariable("spectrum", "f4", ("time", "wvl_lgr"))
        setattr(spectrumVariable, "sensor_spectrum", 'refer to variable "sensor spectrum object"')
        intensityVariable  = netCDFHandler.createVariable("maxFixedIntensity", "f4", ("time",))
        setattr(intensityVariable, "sensor_spectrum", 'refer to variable "sensor spectrum object"')


        #TODO
        #TODO add stanard names into the environmental loggers
        wavelengthVariable[:] = wvl_lgr
        setattr(wavelengthVariable, "units", "meter")
        setattr(wavelengthVariable, "long_name", "wavelengths")
        setattr(wavelengthVariable, "standard_name", "radiation_wavelength")
        setattr(wavelengthVariable, "notes", "these wavelengths are all the same in different collections from the environmental logger. Ranging from 337.7 to 824 nm.")
        spectrumVariable[:,:] = spectrum
        setattr(spectrumVariable, "units", "meter")
        setattr(spectrumVariable, "long_name", "spectrum from hyperspectral camera spectrometer")
        setattr(spectrumVariable, "notes", "1024*<time> number of discrete wavelengths collected by the spectrometer")
        intensityVariable[:]  = maxFixedIntensity
        setattr(intensityVariable, "units", "placeholder")
        setattr(intensityVariable, "long_name", "max_fixed_intensity")
        setattr(intensityVariable, "notes", "maximum_fix_intensity (always equals to 2^14-1=16383)")

        timeVariable = netCDFHandler.createVariable("time", 'f8', ('time',))
        timeVariable[:] = [translateTime(data["timestamp"]) for data in loggerReadings]
        setattr(timeVariable, "units",    "days since 1970-01-01 00:00:00")
        setattr(timeVariable, "calender", "gregorian")

        for data in loggerReadings[0]:
            if data.startswith("sensor"): # par sensor or co2 sensor

                sensorValue, sensorUnit, sensorRaw = sensorVariables(loggerReadings, data)
                sensorValueVariable                = netCDFHandler.createVariable(renameTheValue(data),                    "f4", ("time", ))
                sensorRawValueVariable             = netCDFHandler.createVariable("".join(("raw_", renameTheValue(data))), "f4", ("time", ))

                sensorValueVariable[:]    = sensorValue
                sensorRawValueVariable[:] = sensorRaw
                setattr(sensorValueVariable, "units", sensorUnit[0])
                if data.endswith("co2"):
                    setattr(sensorValueVariable, "sensor_co2", 'refer to "sensor co2 object"')
                else:
                    setattr(sensorValueVariable, "sensor_par", 'refer to "sensor par object"')

                if renameTheValue(data) in _CF_STANDARDS:
                    setattr(sensorValueVariable, "standard_name", _CF_STANDARDS[renameTheValue(data)])

        wvl_ntf  = [np.average([wvl_lgr[i], wvl_lgr[i+1]]) for i in range(len(wvl_lgr)-1)]
        delta    = [wvl_ntf[i+1] - wvl_ntf[i] for i in range(len(wvl_ntf) - 1)]
        delta.insert(0, 2*(wvl_ntf[0] - wvl_lgr[0]))
        delta.insert(-1, 2*(wvl_lgr[-1] - wvl_ntf[-1]))

        # Downwelling Flux = summation of (delta lambda(_wvl_dlt) * downwellingSpectralFlux)
        # Details in CalculationWorks.py
        downwellingSpectralFlux, downwellingFlux = calculateDownwellingSpectralFlux(wvl_lgr, spectrum, delta)

        # Add data from hyperspectral_calibration.nco
        netCDFHandler.createVariable("wvl_dlt", 'f8', ("wvl_lgr",))[:] = delta
        setattr(netCDFHandler.variables['wvl_dlt'], 'units', 'meter')
        setattr(netCDFHandler.variables['wvl_dlt'], 'notes',"Bandwidth, also called dispersion, is between 0.455-0.495 nm across all channels. Values computed as differences between midpoints of adjacent band-centers.")
        setattr(netCDFHandler.variables['wvl_dlt'], 'long_name', "Bandwidth of environmental sensor")

        netCDFHandler.createVariable("flx_sns", "f4", ("wvl_lgr",))[:] = np.array(FLX_SNS) * 1e-6
        setattr(netCDFHandler.variables['flx_sns'],'units', 'watt meter-2 count-1')
        setattr(netCDFHandler.variables['flx_sns'],'long_name','Flux sensitivity of each band (irradiance per count)')
        setattr(netCDFHandler.variables['flx_sns'], 'provenance', "EnvironmentalLogger calibration information from file S05673_08062015.IrradCal provided by TinoDornbusch and discussed here: https://github.com/terraref/reference-data/issues/30#issuecomment-217518434")

        netCDFHandler.createVariable("flx_spc_dwn", 'f4', ('time','wvl_lgr'))[:,:] = downwellingSpectralFlux
        setattr(netCDFHandler.variables['flx_spc_dwn'],'units', 'watt meter-2 meter-1')
        setattr(netCDFHandler.variables['flx_spc_dwn'], 'long_name', 'Downwelling Spectral Irradiance')
        setattr(netCDFHandler.variables['flx_spc_dwn'], 'standard_name', 'downwelling_spectral_spherical_irradiance_in_air')

        # Downwelling Flux = summation of (delta lambda(_wvl_dlt) * downwellingSpectralFlux)
        netCDFHandler.createVariable("flx_dwn", 'f4')[...] = downwellingFlux
        setattr(netCDFHandler.variables["flx_dwn"], "units", "watt meter-2")
        setattr(netCDFHandler.variables['flx_dwn'], 'long_name', 'Downwelling Irradiance')
        setattr(netCDFHandler.variables['flx_dwn'], 'standard_name', 'downwelling_spherical_irradiance_in_air')

        # #Other Constants used in calculation
        # #Integration Time
        netCDFHandler.createVariable("time_integration", 'f4')[...] = float(loggerReadings[0]["spectrometer"]["integration time in us"]) / 1.0e-6
        setattr(netCDFHandler.variables["time_integration"], "units", "second")
        setattr(netCDFHandler.variables['time_integration'], 'long_name', 'Spectrometer integration time')

        # #Spectrometer area
        netCDFHandler.createVariable("area_sensor", "f4")[...] = AREA
        setattr(netCDFHandler.variables["area_sensor"], "units", "meter2")
        setattr(netCDFHandler.variables['area_sensor'], 'long_name', 'Spectrometer Area')

        netCDFHandler.history = " ".join((time.strftime("%a %b %d %H:%M:%S %Y",  time.localtime(int(time.time()))), ': python', commandLine))


def mainProgramTrigger(fileInputLocation, fileOutputLocation, fileType="NETCDF4"):
    '''
    This function will trigger the whole script
    '''
    print fileType
    startPoint = time.clock()
    if not os.path.exists(fileOutputLocation) and not fileOutputLocation.endswith('.nc'):
        os.mkdir(fileOutputLocation)  # Create folder

    if not os.path.isdir(fileInputLocation) or fileOutputLocation.endswith('.nc'):
        print "\nProcessing", "".join((fileInputLocation, '....')),"\n", "-" * (len(fileInputLocation) + 15)
        tempJSONMasterList = JSONHandler(fileInputLocation)
        if not os.path.isdir(fileOutputLocation):
            main(tempJSONMasterList, fileType, fileOutputLocation, commandLine=" ".join(sys.argv))
        else:
            outputFileName = os.path.split(fileInputLocation)[-1]
            print "Exported to", fileOutputLocation, "\n", "-" * (len(fileInputLocation) + 15)
            main(tempJSONMasterList, fileType, os.path.join(fileOutputLocation,  "".join((outputFileName.strip('.json'), '.nc'))),commandLine=" ".join(sys.argv))
    else:    
        for filePath, fileDirectory, fileName in os.walk(fileInputLocation):
            for members in fileName:
                if os.path.join(filePath, members).endswith('.json'):
                    print "\nProcessing", "".join((members, '....')),"\n","-" * (len(members) + 15)
                    outputFileName = "".join((members.strip('.json'), '.nc'))
                    tempJSONMasterList = JSONHandler(os.path.join(filePath, members))
                    print "Exported to", str(os.path.join(fileOutputLocation, outputFileName)), "\n", "-" * (len(fileInputLocation) + 15)
                    main(tempJSONMasterList, fileType, os.path.join(fileOutputLocation, outputFileName), commandLine=" ".join(sys.argv))
    
    endPoint = time.clock()
    print "Done. Execution time: {:.3f} seconds\n".format(endPoint-startPoint)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('input_file_path', type=str, nargs=1,
                             help='The path to the raw environmental logger records (JSON format)')
    parser.add_argument('netCDF_format', type=str, nargs='?', default="NETCDF4",
                             help='The format of the output netCDF file (can be NETCDF3_64BIT_DATA or NETCDF4)')
    parser.add_argument('output_file_path', type=str, nargs=1, default=".",
                             help='The path to the environmental logger final outputs you want (netCDF format, Level 1 Data)')
    args = parser.parse_args()

    mainProgramTrigger(args.input_file_path[0], args.output_file_path[0], args.netCDF_format)
