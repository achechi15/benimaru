package routes

import (
	"benimaru/gateway/internal/middleware"
	"benimaru/gateway/internal/proxy"
	"benimaru/gateway/internal/upstream"
	"fmt"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
)

type Builder func(u upstream.Upstream, defaultTimeout time.Duration) (http.Handler, error)

type Registry struct {
	overrides  map[string]Builder
	perService map[string][]middleware.Middleware
	global     []middleware.Middleware
}

func NewRegistry() *Registry {
	return &Registry{
		overrides:  map[string]Builder{},
		perService: map[string][]middleware.Middleware{},
	}
}
func (r *Registry) Use(mws ...middleware.Middleware) *Registry {
	r.global = append(r.global, mws...)
	return r
}

func (r *Registry) For(name string, mws ...middleware.Middleware) *Registry {
	r.perService[name] = append(r.perService[name], mws...)
	return r
}

func (r *Registry) Override(name string, b Builder) *Registry {
	r.overrides[name] = b
	return r
}

func (r *Registry) Build(ups []upstream.Upstream, defaultTimeout time.Duration) (http.Handler, error) {
	router := chi.NewRouter()

	router.Use(chimw.RequestID, chimw.RealIP, chimw.Recoverer)

	router.Get("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	for _, u := range ups {
		build := r.overrides[u.Name]
		if build == nil {
			build = defaultBuilder
		}
		h, err := build(u, defaultTimeout)
		if err != nil {
			return nil, fmt.Errorf("build %q: %w", u.Name, err)
		}

		mws := append(append([]middleware.Middleware{}, r.global...), r.perService[u.Name]...)
		h = middleware.Chain(h, mws...)

		router.Mount(u.Prefix, h)

	}
	return router, nil
}

func defaultBuilder(u upstream.Upstream, defaultTimeout time.Duration) (http.Handler, error) {
	return proxy.New(u, defaultTimeout)
}
