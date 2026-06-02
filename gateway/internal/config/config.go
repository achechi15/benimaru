package config

import (
	"benimaru/gateway/internal/upstream"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
)

type Config struct {
	HTTPAddr       string
	APIKey         string
	AllowedOrigins []string
	DefaultTimeout time.Duration
	Upstreams      []upstream.Upstream
}

func Load() (Config, error) {
	cfg := Config{
		HTTPAddr:       envOr("GATEWAY_ADDR", ":8080"),
		APIKey:         os.Getenv("GATEWAY_API_KEY"),
		DefaultTimeout: envDurationOr("GATEWAY_PROXY_TIMEOUT", 10*time.Second),
	}

	if raw := os.Getenv("GATEWAY_ALLOWED_ORIGINS"); raw != "" {
		cfg.AllowedOrigins = strings.Split(raw, ",")
	}

	ups, err := loadUpstreams()
	if err != nil {
		return cfg, err
	}
	cfg.Upstreams = ups

	if err := cfg.Validate(); err != nil {
		return cfg, err
	}

	return cfg, nil
}

func loadUpstreams() ([]upstream.Upstream, error) {
	var raw []byte
	switch {
	case os.Getenv("GATEWAY_UPSTREAMS_FILE") != "":
		b, err := os.ReadFile(os.Getenv("GATEWAY_UPSTREAMS_FILE"))
		if err != nil {
			return nil, fmt.Errorf("leyendo GATEWAY_UPSTREAMS_FILE: %w", err)
		}
		raw = b
	case os.Getenv("GATEWAY_UPSTREAMS") != "":
		raw = []byte(os.Getenv("GATEWAY_UPSTREAMS"))
	default:
		return nil, fmt.Errorf("define GATEWAY_UPSTREAMS_FILE o GATEWAY_UPSTREAMS")
	}

	var ups []upstream.Upstream
	if err := json.Unmarshal(raw, &ups); err != nil {
		return nil, fmt.Errorf("parseando upstreams JSON: %w", err)
	}
	return ups, nil
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envDurationOr(k string, def time.Duration) time.Duration {
	if v := os.Getenv(k); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}

func (c Config) Validate() error {
	if c.HTTPAddr == "" {
		return fmt.Errorf("GATEWAY_ADDR vacío")
	}
	if len(c.Upstreams) == 0 {
		return fmt.Errorf("no hay upstreams definidos")
	}
	seen := make(map[string]bool, len(c.Upstreams))
	for i, u := range c.Upstreams {
		if err := u.Validate(); err != nil {
			return fmt.Errorf("upstream[%d] %q: %w", i, u.Name, err)
		}
		if seen[u.Prefix] {
			return fmt.Errorf("prefijo duplicado: %s", u.Prefix)
		}
		seen[u.Prefix] = true
	}
	return nil
}
