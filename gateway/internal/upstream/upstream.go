package upstream

import (
	"fmt"
	"strings"
	"time"
)

type Upstream struct {
	Name        string `json:"name"`
	Prefix      string `json:"prefix"`
	Target      string `json:"target"`
	Protocol    string `json:"protocol"`
	StripPrefix bool   `json:"stripPrefix"`
	Stream      bool   `json:"stream"`
	Timeout     string `json:"timeout"`
}

func (u Upstream) Validate() error {
	if u.Name == "" {
		return fmt.Errorf("name vacío")
	}
	if !strings.HasPrefix(u.Prefix, "/") {
		return fmt.Errorf("prefix debe comenzar por '/'")
	}
	if u.Target == "" {
		return fmt.Errorf("target vacío")
	}
	switch u.Protocol {
	case "", "http", "grpc":
	default:
		return fmt.Errorf("protocol invalido: %q (usa http o grpc)", u.Protocol)
	}
	if u.Timeout != "" {
		if _, err := time.ParseDuration(u.Timeout); err != nil {
			return fmt.Errorf("timeout invalido %q: %w", u.Timeout, err)
		}
	}
	return nil
}

func (u Upstream) IsGRPC() bool {
	return u.Protocol == "grpc"
}

func (u Upstream) ResolveTimeout(def time.Duration) time.Duration {
	if u.Timeout == "" {
		return def
	}
	if d, err := time.ParseDuration(u.Timeout); err == nil {
		return d
	}
	return def
}
