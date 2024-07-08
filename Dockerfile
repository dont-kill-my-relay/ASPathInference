FROM python:2.7.18-alpine3.11 as build
ARG BGP_DATE="YYYY-MM-DD-HHMM"
RUN pip install dnspython
RUN mkdir -p /app/bin /app/script/tmp

COPY Makefile /app/Makefile
COPY log /app/log
COPY script /app/script
COPY src /app/src

RUN apk add perl make libstdc++6 libstdc++ g++ zlib-dev perl-dev
RUN cpan LWP::Simple

WORKDIR /app/src
RUN make PYTHONLIB

WORKDIR /app
RUN make
RUN make $BGP_DATE.run


FROM python:2.7.18-alpine3.11

COPY --from=build /app/data /app/data
COPY --from=build /app/script/*.py /app/script/
COPY --from=build /app/script/bgp.so /app/script/
COPY --from=build /app/bin/Get* /app/bin/

RUN apk add libstdc++6 libstdc++
RUN pip install dnspython
RUN mkdir -p /app/log/
LABEL org.opencontainers.image.source=https://github.com/dont-kill-my-relay/as-path-inference
EXPOSE 61002
CMD /app/script/inferPath.py --db-path /app/data/oixdb --as-relationship /app/data/oix_relation_degree --link-preference /app/data/oix_preference --prefix-list /app/data/oix_prefixlist --pid /app/log/pid

