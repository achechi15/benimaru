package flowmetapod

import (
	metapodv1 "benimaru/gateway/internal/gen/metapod/v1"
	"benimaru/gateway/internal/upstream"
	"context"
	"encoding/json"
	"net/http"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type analyzeReq struct {
	Prompt string `json:"prompt"`
}

// Builder expone una variante síncrona de metapod en /flow/metapod, sin auth:
//   POST /flow/metapod/analyze -> genera con el LLM y devuelve la respuesta
//   GET  /flow/metapod/status  -> 200 si el servicio responde
func Builder(u upstream.Upstream, _ time.Duration) (http.Handler, error) {
	conn, err := grpc.NewClient(u.Target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	client := metapodv1.NewMetapodServiceClient(conn)

	mux := http.NewServeMux()

	mux.HandleFunc("POST "+u.Prefix+"/analyze", func(w http.ResponseWriter, r *http.Request) {
		var in analyzeReq
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return
		}

		resp, err := client.Analyze(r.Context(), &metapodv1.AnalyzeRequest{Prompt: in.Prompt})
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"flow": resp.GetBody()})
	})

	mux.HandleFunc("GET "+u.Prefix+"/status", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		if _, err := client.Status(ctx, &metapodv1.StatusRequest{}); err != nil {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	return mux, nil
}
