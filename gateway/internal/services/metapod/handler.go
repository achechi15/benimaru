package metapod

import (
	metapodv1 "benimaru/gateway/internal/gen/metapod/v1"
	"benimaru/gateway/internal/upstream"
	"encoding/json"

	"net/http"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type createReq struct {
	Brand   string `json:"brand"`
	Channel string `json:"channel"`
	ID      string `json:"id"`
	Prompt  string `json:"prompt"`
}

func Builder(u upstream.Upstream, _ time.Duration) (http.Handler, error) {
	conn, err := grpc.NewClient(u.Target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	client := metapodv1.NewMetapodServiceClient(conn)

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var in createReq
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return
		}

		resp, err := client.Create(r.Context(), &metapodv1.CreateRequest{
			Brand: in.Brand, Channel: in.Channel, Id: in.ID, Prompt: in.Prompt,
		})

		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status": resp.GetStatus(), "id": resp.GetId(),
		})
	}), nil
}
