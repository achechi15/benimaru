package profanity

import (
	profanityv1 "benimaru/gateway/internal/gen/profanity/v1"
	"benimaru/gateway/internal/upstream"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/valkey-io/valkey-go"
	"golang.org/x/sync/singleflight"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type incomingReq struct {
	Text string `json:"text,omitempty"`
	URL  string `json:"url,omitempty"`
}

const cacheTTL = 24 * time.Hour
const imageBlockReason = "sensible conversation capture"

type imageResponse struct {
	Blocked bool   `json:"blocked"`
	Reason  string `json:"reason,omitempty"`
}

func Builder(u upstream.Upstream, _ time.Duration) (http.Handler, error) {
	conn, err := grpc.NewClient(u.Target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	client := profanityv1.NewProfanityServiceClient(conn)

	// Caché best-effort: si no hay VALKEY_SERVER_URL o Valkey no está disponible,
	// el handler funciona igual sin caché (no debe tumbar el arranque del gateway).
	var cache valkey.Client
	if addr := os.Getenv("VALKEY_SERVER_URL"); addr != "" {
		c, cerr := valkey.NewClient(valkey.ClientOption{InitAddress: []string{addr}})
		if cerr != nil {
			slog.Warn("valkey no disponible, profanity arranca sin caché", "err", cerr, "addr", addr)
		} else {
			cache = c
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

		hasText := in.Text != ""
		hasURL := in.URL != ""
		if !hasText && !hasURL {
			http.Error(w, "falta 'text' o 'url'", http.StatusBadRequest)
			return
		}

		// singleflight: peticiones idénticas concurrentes = una sola resolución.
		runText := func() ([]byte, error) {
			v, err, _ := group.Do(in.Text, func() (any, error) {
				return analyze(r.Context(), client, cache, in.Text)
			})
			if err != nil {
				return nil, err
			}
			return v.([]byte), nil
		}
		runImage := func() ([]byte, error) {
			v, err, _ := group.Do("img:"+in.URL, func() (any, error) {
				return analyzeImage(r.Context(), client, cache, in.URL)
			})
			if err != nil {
				return nil, err
			}
			return v.([]byte), nil
		}

		// Texto y/o imagen. Si vienen los dos, se resuelven en paralelo.
		var (
			textOut, imgOut []byte
			textErr, imgErr error
		)
		switch {
		case hasText && hasURL:
			var wg sync.WaitGroup
			wg.Add(2)
			go func() { defer wg.Done(); textOut, textErr = runText() }()
			go func() { defer wg.Done(); imgOut, imgErr = runImage() }()
			wg.Wait()
		case hasText:
			textOut, textErr = runText()
		default:
			imgOut, imgErr = runImage()
		}
		if textErr != nil {
			http.Error(w, textErr.Error(), http.StatusBadGateway)
			return
		}
		if imgErr != nil {
			http.Error(w, imgErr.Error(), http.StatusBadGateway)
			return
		}

		// Respuesta siempre envuelta: {"text": {...}} y/o {"image": {"blocked": bool, "reason": "..."}}.
		out := make(map[string]json.RawMessage, 2)
		if hasText {
			out["text"] = textOut
		}
		if hasURL {
			out["image"] = imgOut
		}
		resp, err := json.Marshal(out)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(resp)
	}), nil
}

func analyze(ctx context.Context, client profanityv1.ProfanityServiceClient, cache valkey.Client, text string) ([]byte, error) {
	if cache != nil {
		if val, err := cache.Do(ctx, cache.B().Get().Key(text).Build()).ToString(); err == nil {
			return []byte(val), nil // hit
		}
	}

	resp, err := client.AnalyzeText(ctx, &profanityv1.AnalyzeTextRequest{Text: text})
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

func analyzeImage(ctx context.Context, client profanityv1.ProfanityServiceClient, cache valkey.Client, url string) ([]byte, error) {
	cacheKey := "img:blocked:" + url
	if cache != nil {
		if val, err := cache.Do(ctx, cache.B().Get().Key(cacheKey).Build()).ToString(); err == nil {
			return []byte(val), nil // hit
		}
	}

	resp, err := client.AnalyzeImage(ctx, &profanityv1.AnalyzeImageRequest{Url: url})
	if err != nil {
		return nil, err
	}
	out, err := json.Marshal(buildImageResponse(resp.GetProfanityCheck()))
	if err != nil {
		return nil, err
	}

	if cache != nil {
		_ = cache.Do(ctx, cache.B().Set().Key(cacheKey).Value(string(out)).Ex(cacheTTL).Build()).Error()
	}
	return out, nil
}

func buildImageResponse(blocked bool) imageResponse {
	img := imageResponse{Blocked: blocked}
	if blocked {
		img.Reason = imageBlockReason
	}
	return img
}
