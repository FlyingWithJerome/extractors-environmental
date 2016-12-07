#!/usr/bin/env python

"""
This extractor triggers when a JSON file is added to Clowder.

It calls processing methods in environmental_logger_json2netcdf.py to
convert the JSON file to .nc netCDF format.
"""

import os
import logging
import requests

from pyclowder.extractors import Extractor
from pyclowder.utils import CheckMessage
import pyclowder.files

import environmental_logger_json2netcdf as ela


class EnvironmentLoggerJSON2NetCDF(Extractor):
    def __init__(self):
        Extractor.__init__(self)

        # add any additional arguments to parser
        # self.parser.add_argument('--max', '-m', type=int, nargs='?', default=-1,
        #                          help='maximum number (default=-1)')
        self.parser.add_argument('--output', '-o', dest="output_dir", type=str, nargs='?',
                                 default="/home/extractor/sites/ua-mac/Level_1/EnvironmentLogger",
                                 help="root directory where timestamp & output directories will be created")
        self.parser.add_argument('--overwrite', dest="force_overwrite", type=bool, nargs='?', default=False,
                                 help="whether to overwrite output file if it already exists in output directory")

        # parse command line and load default logging configuration
        self.setup()

        # setup logging for the exctractor
        logging.getLogger('pyclowder').setLevel(logging.DEBUG)
        logging.getLogger('__main__').setLevel(logging.DEBUG)

        # assign other arguments
        self.output_dir = self.args.output_dir
        self.force_overwrite = self.args.force_overwrite

    def check_message(self, connector, host, secret_key, resource, parameters):
        # Only trigger extraction if the newly added file is a relevant JSON file
        if not resource['name'].endswith("_environmentlogger.json"):
            return CheckMessage.ignore

        return CheckMessage.download

    def process_message(self, connector, host, secret_key, resource, parameters):
        # path to input JSON file
        in_envlog = resource['local_paths'][0]

        if in_envlog:
            # Prepare output directory path - "output_dir/YYYY-MM-DD/filename.nc"
            timestamp = resource['name'].split("_")[0]
            out_netcdf = os.path.join(self.output_dir, timestamp, resource['name'][:-5]+".nc")
            if not os.path.exists(os.path.join(self.output_dir, timestamp)):
                os.makedirs(os.path.join(self.output_dir, timestamp))

            # Create netCDF if it doesn't exist
            if not os.path.isfile(out_netcdf) or self.force_overwrite:
                logging.info("converting JSON to: %s" % out_netcdf)
                ela.mainProgramTrigger(in_envlog, out_netcdf)

                # Fetch dataset ID by dataset name if not provided
                if resource['parent_dataset_id'] == '':
                    ds_name = 'EnvironmentLogger - ' + resource['name'].split('_')[0]
                    url = '%s/api/datasets?key=%s&title=%s' % (host, secret_key, ds_name)
                    r = requests.get(url, headers={'Content-Type': 'application/json'})
                    if r.status_code == 200:
                        resource['parent_dataset_id'] = r.json()[0]['id']

                if 'parent_dataset_id' in resource and resource['parent_dataset_id'] != '':
                    logging.info("uploading netCDF file to Clowder")
                    pyclowder.files.upload_to_dataset(connector, host, secret_key,
                                                      resource['parent_dataset_id'], out_netcdf)
                else:
                    logging.error('no parent dataset ID found; unable to upload to Clowder')
                    raise Exception('no parent dataset ID found')
            else:
                logging.info("%s already exists; skipping" % out_netcdf)

if __name__ == "__main__":
    extractor = EnvironmentLoggerJSON2NetCDF()
    extractor.start()
