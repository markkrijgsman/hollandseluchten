# One-shot image that puts the data into the shared volume: the hackathon repository (reference measurements) and the
# sensor data from Zenodo. Build context: the repository root.
FROM alpine:3.20
RUN apk add --no-cache git curl
COPY scripts/fetch-sensors.sh docker/data-init.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/fetch-sensors.sh /usr/local/bin/data-init.sh
ENTRYPOINT ["data-init.sh"]
