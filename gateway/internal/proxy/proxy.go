package proxy

import (
	"benimaru/gateway/internal/upstream"
	"context"
	"crypto/tls"
	"log/slog"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"golang.org/x/net/http2"
)

func New(u upstream.Upstream, defaultTimeout time.Duration) (http.Handler, error) {
	target, err := url.Parse(u.Target)
	if err != nil {
		return nil, err
	}

	rp := httputil.NewSingleHostReverseProxy(target)

	if u.IsGRPC() {
		rp.Transport = &http2.Transport{
			AllowHTTP: true,
			DialTLSContext: func(ctx context.Context, network, addr string, _ *tls.Config) (net.Conn, error) {
				var d net.Dialer
				return d.DialContext(ctx, network, addr)
			},
		}
	} else {
		rp.Transport = &http.Transport{
			Proxy:                 http.ProxyFromEnvironment,
			ResponseHeaderTimeout: u.ResolveTimeout(defaultTimeout),
			IdleConnTimeout:       90 * time.Second,
		}
	}

	if u.Stream {
		rp.FlushInterval = -1
	}

	rp.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		slog.Error("upstream error", "err", err, "upstream", u.Name, "host", target.Host, "path", r.URL.Path)
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
	}

	var handler http.Handler = rp

	if u.StripPrefix {
		handler = http.StripPrefix(u.Prefix, handler)
	}
	return handler, nil

}
