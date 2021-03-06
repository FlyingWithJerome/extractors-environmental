# Dockerfile for the TerraRef meteorological dat parser extractor
FROM ubuntu
MAINTAINER Max Burnette <mburnet2@illinois.edu>

# Install any programs needed
RUN useradd -u 47852 extractor \
    && apt-get -y update \
    && apt-get install -y -q build-essential git python python-dev python-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install requests pika enum pyyaml urllib3 python-dateutil \
    && mkdir /home/extractor \
    && chown -R extractor /home/extractor \
    && cd /home/extractor \
    && git clone https://opensource.ncsa.illinois.edu/bitbucket/scm/cats/pyclowder2.git \
    && cd pyclowder2 \
    && python setup.py install

# command to run when starting docker
COPY entrypoint.sh extractor_info.json *.py /home/extractor/

USER extractor
ENTRYPOINT ["/home/extractor/entrypoint.sh"]
CMD ["extractor"]

# Setup environment variables. These are passed into the container. You can change
# these to your setup. If RABBITMQ_URI is not set, it will try and use the rabbitmq
# server that is linked into the container. MAIN_SCRIPT is set to the script to be
# executed by entrypoint.sh
ENV RABBITMQ_EXCHANGE="terra" \
    RABBITMQ_VHOST="%2F" \
    RABBITMQ_QUEUE="terra.environmental.weather_datparser" \
    MAIN_SCRIPT="terra_weather_datparser.py"
