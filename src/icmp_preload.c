/*
 * LD_PRELOAD shim: redirect SOCK_RAW ICMP to unprivileged SOCK_DGRAM ICMP.
 *
 * Flatpak blocks SOCK_RAW (requires CAP_NET_RAW), but SOCK_DGRAM with
 * IPPROTO_ICMP works when net.ipv4.ping_group_range is permissive (default
 * on SteamOS).  This lets Boosteroid's Net::Pinger measure latency to
 * data center gateways without any binary modification.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>

typedef int (*real_socket_t)(int, int, int);

int socket(int domain, int type, int protocol) {
    real_socket_t real_socket = (real_socket_t)dlsym(RTLD_NEXT, "socket");

    /* Only intercept: AF_INET + SOCK_RAW + ICMP */
    if (domain == AF_INET && type == SOCK_RAW && protocol == IPPROTO_ICMP) {
        int fd = real_socket(domain, SOCK_DGRAM, protocol);
        if (fd >= 0)
            return fd;
        /* Fall through to original call if SOCK_DGRAM also fails */
    }

    return real_socket(domain, type, protocol);
}
