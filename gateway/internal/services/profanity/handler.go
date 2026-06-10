package profanity

import (
	profanityv1 "benimaru/gateway/internal/gen/profanity/v1"
	"benimaru/gateway/internal/upstream"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"time"

	"github.com/valkey-io/valkey-go"
	"golang.org/x/sync/singleflight"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type incomingReq struct {
	Type    string `json:"type"`
	Body    string `json:"body,omitempty"`
	Caption string `json:"caption,omitempty"`
}

const cacheTTL = 24 * time.Hour

func Builder(u upstream.Upstream, _ time.Duration) (http.Handler, error) {
	conn, err := grpc.NewClient(u.Target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	client := profanityv1.NewProfanityServiceClient(conn)

	// Caché opcional: si no hay VALKEY_SERVER_URL, el handler funciona sin caché.
	var cache valkey.Client
	if addr := os.Getenv("VALKEY_SERVER_URL"); addr != "" {
		cache, err = valkey.NewClient(valkey.ClientOption{InitAddress: []string{addr}})
		if err != nil {
			return nil, err
		}
	}

	var group singleflight.Group

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var in incomingReq
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return
		}
		text, err := extractText(in)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		// singleflight: textos idénticos concurrentes = una sola resolución.
		v, err, _ := group.Do(text, func() (any, error) {
			return analyze(r.Context(), client, cache, text)
		})
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(v.([]byte))
	}), nil
}

func extractText(in incomingReq) (string, error) {
	switch in.Type {
	case "TEXT":
		return in.Body, nil
	case "IMAGE", "VIDEO":
		return in.Caption, nil
	default:
		return "", errors.New("tipo no soportado: " + in.Type)
	}
}

func analyze(ctx context.Context, client profanityv1.ProfanityServiceClient, cache valkey.Client, text string) ([]byte, error) {
	if cache != nil {
		if val, err := cache.Do(ctx, cache.B().Get().Key(text).Build()).ToString(); err == nil {
			return []byte(val), nil // hit
		}
	}

	resp, err := client.Analyze(ctx, &profanityv1.AnalyzeRequest{Text: text})
	if err != nil {
		return nil, err
	}
	out, err := json.Marshal(resp.GetProbas())
	if err != nil {
		return nil, err
	}

	if cache != nil {
		_ = cache.Do(ctx, cache.B().Set().Key(text).Value(string(out)).Ex(cacheTTL).Build()).Error()
	}
	return out, nil
}
