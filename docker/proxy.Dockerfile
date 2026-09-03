# DPI bypass proxy'si (byedpi/ciadpi) - SOCKS5, 1080.
#
# Kaynak vendor/byedpi altinda GOMULU. Onceki surum derleme sirasinda
# GitHub'dan klonluyordu; GitHub'a erisilemeyen aglarda imaj derlenemiyordu.
# Artik yalnizca Alpine paket deposuna ihtiyac var.
FROM docker.io/library/alpine:3.20 AS build
RUN apk add --no-cache build-base linux-headers
WORKDIR /src
COPY vendor/byedpi/ ./
RUN make

FROM docker.io/library/alpine:3.20
COPY --from=build /src/ciadpi /usr/local/bin/ciadpi
COPY vendor/byedpi/LICENSE /usr/share/licenses/byedpi/LICENSE
EXPOSE 1080
# -r 1+s : TLS kaydini SNI konumundan boler (byedpi --tlsrec).
# Bu ag icin dogrulanan strateji buydu; tutmazsa -o 1+s veya -q 1+s deneyin.
ENV CIADPI_ARGS="-r 1+s"
CMD ["sh", "-c", "exec ciadpi -i 0.0.0.0 -p 1080 $CIADPI_ARGS"]
