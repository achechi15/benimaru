package main

import (
	config "benimaru/gateway/internal/config"
	"benimaru/gateway/internal/middleware"
	"benimaru/gateway/internal/routes"
	"benimaru/gateway/internal/services/flowmetapod"
	"benimaru/gateway/internal/services/metapod"
	"benimaru/gateway/internal/services/profanity"
	"log/slog"
	"net/http"
	"os"

	"github.com/joho/godotenv"
)

func main() {
	_ = godotenv.Load()
	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "err", err)
		os.Exit(1)
	}

	reg := routes.NewRegistry().Use(middleware.Logging(), middleware.CORS(cfg.AllowedOrigins))

	if cfg.APIKey != "" {
		reg.For("metapod", middleware.APIKey(cfg.APIKey))
		reg.For("profanity", middleware.APIKey(cfg.APIKey))
	}

	reg.Override("metapod", metapod.Builder)
	reg.Override("profanity", profanity.Builder)

	// flowmetapod: variante síncrona de metapod, deliberadamente sin auth.
	reg.Override("flowmetapod", flowmetapod.Builder)

	// reg.Override("foo", func(u upstream.Upstream, d time.Duration) (http.Handler, error) {
	//     mux := http.NewServeMux()
	//     mux.HandleFunc("/foo/special", miHandlerEspecial)
	//     return mux, nil
	// })

	router, err := reg.Build(cfg.Upstreams, cfg.DefaultTimeout)
	if err != nil {
		slog.Error("router", "err", err)
		os.Exit(1)
	}

	for _, u := range cfg.Upstreams {
		slog.Info("upstream montado", "name", u.Name, "prefix", u.Prefix, "protocol", u.Protocol)
	}

	slog.Info("gateway escuchando", "addr", cfg.HTTPAddr)

	if err := http.ListenAndServe(cfg.HTTPAddr, router); err != nil {
		slog.Error("serve", "err", err)
		os.Exit(1)
	}
}
